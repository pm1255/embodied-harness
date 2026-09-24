"""Model-authored, bounded Python tool programs over registered robot primitives.

This admits a deliberately small Python grammar, not arbitrary Python plugins.
No imports, object introspection, direct file/network access, recursion or while loops are
admitted. The external evaluator, archive and credentials are not part of the API.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math

from jsonschema import Draft202012Validator

from ..protocol import ToolFailure, ToolResult
from ..runtime import Tool

PRIMITIVES = frozenset({"run_vla", "move_relative", "move_to_pixel", "set_gripper"})
NODES = (
    ast.Module,
    ast.FunctionDef,
    ast.arguments,
    ast.arg,
    ast.For,
    ast.If,
    ast.Assign,
    ast.Return,
    ast.Expr,
    ast.YieldFrom,
    ast.Call,
    ast.Name,
    ast.Load,
    ast.Store,
    ast.Constant,
    ast.Dict,
    ast.List,
    ast.Tuple,
    ast.Subscript,
    ast.Attribute,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.In,
    ast.NotIn,
    ast.UnaryOp,
    ast.Not,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.Pass,
    ast.Break,
    ast.Continue,
)


def validate_program(source):
    if not isinstance(source, str) or len(source.encode()) > 8192:
        raise ValueError("Program must be at most 8 KiB of Python source")
    tree = ast.parse(source)
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise ValueError("Define only run(args, api)")
    fn = tree.body[0]
    if (
        fn.name != "run"
        or fn.decorator_list
        or fn.returns
        or fn.type_comment
        or [a.arg for a in fn.args.args] != ["args", "api"]
        or fn.args.posonlyargs
        or fn.args.kwonlyargs
        or fn.args.vararg
        or fn.args.kwarg
        or fn.args.defaults
        or fn.args.kw_defaults
        or any(a.annotation for a in fn.args.args)
    ):
        raise ValueError("Define only undecorated run(args, api) without annotations/defaults")
    nodes = list(ast.walk(tree))
    if len(nodes) > 300:
        raise ValueError("Program exceeds the syntax budget")
    reserved = {"args", "api", "range", "run"}
    locals_ = {"args", "api", "range"}
    primitive_calls = 0
    for node in nodes:
        if not isinstance(node, NODES):
            raise ValueError(f"Unsupported syntax: {type(node).__name__}")
        if isinstance(node, ast.FunctionDef) and node is not fn:
            raise ValueError("Nested functions are not allowed")
        if isinstance(node, ast.Name):
            if node.id.startswith("_"):
                raise ValueError("Private names are not allowed")
            if isinstance(node.ctx, ast.Store):
                if node.id in reserved:
                    raise ValueError("Cannot replace the bounded API")
                locals_.add(node.id)
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                raise ValueError("Only assignment to a local variable is allowed")
        if isinstance(node, ast.Dict) and any(
            not isinstance(key, ast.Constant) or type(key.value) is not str for key in node.keys
        ):
            raise ValueError("Dictionary keys must be literal strings")
        if isinstance(node, ast.Subscript) and not (
            isinstance(node.slice, ast.Constant) and type(node.slice.value) in (str, int)
        ):
            raise ValueError("Index only literal JSON keys or array positions")
        if isinstance(node, ast.Compare) and not (
            len(node.ops) == 1
            and isinstance(node.ops[0], (ast.Eq, ast.NotEq))
            and isinstance(node.left, ast.Subscript)
            and isinstance(node.left.slice, ast.Constant)
            and node.left.slice.value == "status"
            and len(node.comparators) == 1
            and isinstance(node.comparators[0], ast.Constant)
            and type(node.comparators[0].value) is str
        ):
            raise ValueError("Compare a returned status to a literal status string")
        if isinstance(node, ast.Constant):
            if type(node.value) not in (str, int, float, bool, type(None)):
                raise ValueError("Unsupported literal")
            if isinstance(node.value, str) and len(node.value) > 2000:
                raise ValueError("String literal too long")
        if isinstance(node, ast.Attribute):
            if not (
                isinstance(node.value, ast.Name)
                and node.value.id == "api"
                and node.attr in ("call", "observe")
            ):
                raise ValueError("Only api.call and api.observe may be accessed")
        if isinstance(node, ast.Call):
            if node.keywords:
                raise ValueError("Use positional API arguments")
            if isinstance(node.func, ast.Name) and node.func.id == "range":
                if (
                    len(node.args) != 1
                    or not isinstance(node.args[0], ast.Constant)
                    or type(node.args[0].value) is not int
                    or not 1 <= node.args[0].value <= 4
                ):
                    raise ValueError("Loops use a literal range from one to four")
            elif isinstance(node.func, ast.Attribute) and node.func.attr == "observe":
                if node.args:
                    raise ValueError("observe takes no arguments")
            elif isinstance(node.func, ast.Attribute) and node.func.attr == "call":
                if (
                    len(node.args) != 2
                    or not isinstance(node.args[0], ast.Constant)
                    or node.args[0].value not in PRIMITIVES
                ):
                    raise ValueError("Call only a named existing robot primitive")
                primitive_calls += 1
            else:
                raise ValueError("Only the bounded robot API may be called")
        if isinstance(node, ast.For):
            if (
                not isinstance(node.target, ast.Name)
                or not isinstance(node.iter, ast.Call)
                or not isinstance(node.iter.func, ast.Name)
                or node.iter.func.id != "range"
                or node.orelse
                or any(isinstance(n, ast.For) for stmt in node.body for n in ast.walk(stmt))
            ):
                raise ValueError("Only nonnested, bounded for loops are allowed")
        if isinstance(node, ast.YieldFrom):
            if not (
                isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute)
                and node.value.func.attr == "call"
            ):
                raise ValueError("Yield only native robot control through api.call")
    if not primitive_calls or primitive_calls > 4:
        raise ValueError("Program requires one to four primitive call sites")
    for node in nodes:
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id not in locals_:
            raise ValueError("Unknown variable or capability")
    # API objects may not be saved, returned, passed as data, or subscripted.
    parents = {child: parent for parent in nodes for child in ast.iter_child_nodes(parent)}
    for node in nodes:
        if isinstance(node, ast.Name) and node.id in ("api", "range"):
            parent = parents.get(node)
            if node.id == "api" and not (
                isinstance(parent, ast.Attribute) and parent.value is node
            ):
                raise ValueError("API object is opaque")
            if node.id == "range" and not (isinstance(parent, ast.Call) and parent.func is node):
                raise ValueError("range cannot be used as data")
        if isinstance(node, ast.Attribute):
            parent = parents.get(node)
            if not isinstance(parent, ast.Call) or parent.func is not node:
                raise ValueError("API methods cannot be used as data")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "call"
        ):
            if not isinstance(parents.get(node), ast.YieldFrom):
                raise ValueError("Every robot call must use yield from")
    return tree


def compile_program(source):
    tree = validate_program(source)
    namespace = {"__builtins__": {}, "range": range}
    exec(compile(tree, "<bounded-robot-tool>", "exec"), namespace)
    return namespace["run"]


def bounded_json(value):
    pending, visited = [(value, 0)], 0
    while pending:
        item, depth = pending.pop()
        visited += 1
        if depth > 8 or visited > 1024:
            raise ValueError("Program data exceeds the bounded JSON contract")
        if type(item) is dict:
            if len(item) > 64 or any(type(k) is not str or len(k) > 100 for k in item):
                raise ValueError("Invalid JSON object")
            pending.extend((v, depth + 1) for v in item.values())
        elif type(item) in (list, tuple):
            if len(item) > 128:
                raise ValueError("JSON array too large")
            pending.extend((v, depth + 1) for v in item)
        elif type(item) is str:
            if len(item) > 4000:
                raise ValueError("JSON text too long")
        elif type(item) is int:
            if item.bit_length() > 64:
                raise ValueError("Integer outside the data contract")
        elif type(item) is float:
            if not math.isfinite(item):
                raise ValueError("Nonfinite data")
        elif item is not None and type(item) is not bool:
            raise ValueError("Non-JSON program data")


def install_program(registry, proposal, *, trace=None, max_ticks=321, timeout_s=600):
    """Install a candidate for isolated development, never automatic promotion.

    The operator supplies budgets and the existing primitive registry. The model
    supplies a program and flat JSON parameter schema, not new host capabilities.
    """
    name = proposal["name"]
    if not 1 <= max_ticks <= 1200 or not 0 < timeout_s <= 600:
        raise ValueError("Operator budgets exceed the program contract")
    if not name.startswith("program_") or not name.replace("_", "").isalnum() or len(name) > 64:
        raise ValueError("Use a short program_ tool name")
    schema = proposal["parameters"]
    bounded_json(schema)
    if set(schema) - {"type", "properties", "required", "additionalProperties"}:
        raise ValueError("External references and extended schemas are not allowed")
    Draft202012Validator.check_schema(schema)
    if (
        schema.get("type") != "object"
        or schema.get("additionalProperties") is not False
        or len(schema.get("properties", {})) > 8
    ):
        raise ValueError("Use a closed, flat parameter object")
    if set(schema.get("required", [])) != set(schema["properties"]):
        raise ValueError("Declare every public parameter as required")
    for spec in schema["properties"].values():
        if set(spec) - {
            "type",
            "description",
            "enum",
            "minLength",
            "maxLength",
            "minimum",
            "maximum",
        }:
            raise ValueError("Only bounded flat scalar parameters are supported")
        if spec.get("type") not in ("string", "integer", "boolean"):
            raise ValueError("Parameters must be scalar")
        if spec["type"] == "string" and not 0 < spec.get("maxLength", 0) <= 500:
            raise ValueError("String parameters need an explicit size bound")
    function = compile_program(proposal["source"])
    primitives = {name: registry.tools[name] for name in PRIMITIVES if name in registry.tools}

    def handler(args, ctx):
        class API:
            calls = 0
            observations = 0

            def observe(self):
                self.observations += 1
                if self.observations > 16:
                    raise ValueError("Observation budget exhausted")
                return ctx.observe().to_dict()

            def call(self, tool_name, arguments):
                self.calls += 1
                if self.calls > 16 or tool_name not in primitives:
                    raise ValueError("Primitive call limit or unavailable capability")
                tool = primitives[tool_name]
                bounded_json(arguments)
                Draft202012Validator(tool.parameters).validate(arguments)
                ctx.trace.emit(
                    "program_step",
                    program=name,
                    primitive=tool_name,
                    arguments=arguments,
                    invocation=self.calls,
                )
                try:
                    result = yield from tool.handler(arguments, ctx)
                except (ToolFailure, ValueError) as exc:
                    result = ToolResult("failed", {"message": str(exc)}, type(exc).__name__)
                ctx.trace.emit(
                    "program_step_end", program=name, primitive=tool_name, **result.to_dict()
                )
                return result.to_dict()

        result = yield from function(args, API())
        bounded_json(result)
        json.dumps(result, allow_nan=False)
        if not isinstance(result, dict) or set(result) - {"status", "data", "error_code"}:
            raise ValueError("Program must return a ToolResult dictionary")
        if result.get("status") not in ("succeeded", "failed", "cancelled", "timed_out"):
            raise ValueError("Invalid program result status")
        if not isinstance(result.get("data", {}), dict):
            raise ValueError("Program result data must be an object")
        return ToolResult(**result)

    registry.add(
        Tool(
            name, proposal["description"], schema, handler, max_ticks=max_ticks, timeout_s=timeout_s
        )
    )
    if trace:
        trace.emit(
            "program_registered",
            name=name,
            source_sha256=hashlib.sha256(proposal["source"].encode()).hexdigest(),
            status="candidate_not_promoted",
            max_ticks=max_ticks,
            timeout_s=timeout_s,
        )
