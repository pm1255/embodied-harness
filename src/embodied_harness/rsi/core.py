"""Small, inspectable RSI state: no generated Python execution or hidden training."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

from jsonschema import validate

from ..protocol import ToolResult
from ..runtime import Tool
from ..tools import object_schema


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def seal(path, value):
    """Create once; a restart may verify but cannot silently alter frozen content."""
    path = Path(path)
    document = {"sha256": digest(value), "content": value}
    if path.exists():
        if json.loads(path.read_text()) != document:
            raise ValueError(f"Frozen artifact changed: {path.name}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as f:
            json.dump(document, f, indent=2, ensure_ascii=False, allow_nan=False)
    return document


def resolve(value, parameters):
    if isinstance(value, dict):
        if set(value) == {"$arg"}:
            if value["$arg"] not in parameters:
                raise ValueError("Unknown skill argument")
            return copy.deepcopy(parameters[value["$arg"]])
        return {k: resolve(v, parameters) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, parameters) for v in value]
    return value


def validate_skill(skill, registry):
    """Programs compose existing tools; neither imports, loops nor nested skills exist."""
    if not re.fullmatch(r"skill_[a-z][a-z0-9_]{0,45}", skill["name"]):
        raise ValueError("Invalid skill name")
    if not 1 <= len(skill["steps"]) <= 4:
        raise ValueError("Skills require 1..4 bounded primitive steps")
    allowed = {"move_relative", "move_to_pixel", "set_gripper", "run_vla"}
    properties = {}
    # Infer the public schema from each primitive's real schema, never trust a model's schema.
    for index, step in enumerate(skill["steps"]):
        if set(step) != {"tool", "arguments"} or step["tool"] not in allowed:
            raise ValueError("Only registered primitive composition is allowed")
        tool = registry.tools[step["tool"]]
        if step["tool"] == "move_to_pixel" and index != 0:
            raise ValueError("Pixel projection must be the first skill step")
        if set(step["arguments"]) != set(tool.parameters["properties"]):
            raise ValueError("Primitive arguments do not match its schema")
        for key, value in step["arguments"].items():
            schema = tool.parameters["properties"][key]
            if isinstance(value, dict) and set(value) == {"$arg"}:
                name = value["$arg"]
                if not re.fullmatch(r"[a-z][a-z0-9_]{0,40}", name):
                    raise ValueError("Invalid parameter name")
                if name in properties and properties[name] != schema:
                    raise ValueError("Inconsistent parameter type")
                properties[name] = schema
            else:
                validate(value, schema)
        # Pixels and frame IDs must be selected afresh, never memorized from demonstrations.
        if step["tool"] == "move_to_pixel":
            for key in ("pixel", "observation_id"):
                if not isinstance(step["arguments"][key], dict):
                    raise ValueError("Pixel and observation ID must be caller parameters")
    return object_schema(properties)


def install_skills(registry, skills, trace=None):
    for skill in skills:
        schema = validate_skill(skill, registry)
        primitives = [(registry.tools[s["tool"]], s["arguments"]) for s in skill["steps"]]

        def handler(args, ctx, recipe=primitives, name=skill["name"]):
            expanded = []
            for index, (primitive, template) in enumerate(recipe):
                arguments = resolve(template, args)
                validate(arguments, primitive.parameters)
                expanded.append((primitive, arguments))
            for index, (primitive, arguments) in enumerate(expanded):
                ctx.trace.emit("skill_step", skill=name, index=index,
                               tool=primitive.name, arguments=arguments)
                result = yield from primitive.handler(arguments, ctx)
                ctx.trace.emit("skill_step_end", skill=name, index=index, **result.to_dict())
                if result.status != "succeeded":
                    return result
            return ToolResult("succeeded", {"skill": name, "primitive_steps": len(recipe),
                                            "grasp_verified": False})

        registry.add(Tool(skill["name"], skill["description"], schema, handler,
                          timeout_s=sum(t.timeout_s for t, _ in primitives),
                          max_ticks=sum(t.max_ticks for t, _ in primitives)))
        if trace:
            trace.emit("skill_registered", name=skill["name"], revision=digest(skill),
                       primitive_count=len(primitives))


def render_memory(entries):
    lines = ["# Robot memory\n", "Evidence-bound observations and hypotheses, not hidden reasoning.\n"]
    for entry in entries:
        lines += [f"## {entry['title']}\n", f"Applies to: {', '.join(entry['tasks'])}\n",
                  entry["lesson"] + "\n", "Evidence: " + ", ".join(entry["evidence"]) + "\n"]
    return "\n".join(lines)


def memory_for(entries, task):
    return [entry for entry in entries if task in entry["tasks"] or "*" in entry["tasks"]]


def promotion_gate(baseline, candidate):
    """Paired dev-only gate. Held-out outcomes must never be inputs to this function."""
    if not baseline or set(baseline) != set(candidate):
        raise ValueError("Promotion requires complete paired development cases")
    if any(r.get("split") != "validation" for r in [*baseline.values(), *candidate.values()]):
        raise ValueError("Only validation evidence may select a skill bundle")
    failures = [k for k in baseline if baseline[k]["success"] and not candidate[k]["success"]]
    base_score = sum(r["success"] for r in baseline.values())
    new_score = sum(r["success"] for r in candidate.values())
    base_calls = sum(r["api_calls"] for r in baseline.values())
    new_calls = sum(r["api_calls"] for r in candidate.values())
    infrastructure = any(r["status"] == "infrastructure_error" for r in candidate.values())
    accepted = not failures and not infrastructure and (new_score > base_score or (
        new_score == base_score and new_score > 0 and new_calls < 0.9 * base_calls))
    return {"accepted": bool(accepted), "baseline_successes": base_score,
            "candidate_successes": new_score, "baseline_calls": base_calls,
            "candidate_calls": new_calls, "regressions": failures,
            "infrastructure_error": infrastructure,
            "meaning": "Small development gate, not a statistical generalization claim"}
