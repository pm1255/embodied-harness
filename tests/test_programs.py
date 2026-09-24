"""Admission and execution contracts for model-written robot tool programs."""

import pytest

from embodied_harness.protocol import ToolResult
from embodied_harness.rsi.programs import compile_program, install_program, bounded_json
from embodied_harness.runtime import Registry, Tool

SOURCE = """def run(args, api):
    for segment in range(4):
        result = yield from api.call("run_vla", {"instruction": args["instruction"], "chunks": 8})
        if result["status"] != "succeeded":
            return result
    return {"status": "succeeded", "data": {"segments": 4}}
"""


def test_program_returns_real_failure_before_next_primitive():
    registry = Registry()
    calls = []

    def primitive(args, ctx):
        calls.append(args)
        yield {"motion": len(calls)}
        return ToolResult("failed", {"cause": "observed_failure"}, "motion_stalled")

    registry.add(
        Tool(
            "run_vla",
            "bounded policy",
            {
                "type": "object",
                "properties": {"instruction": {"type": "string"}, "chunks": {"type": "integer"}},
                "required": ["instruction", "chunks"],
            },
            primitive,
        )
    )
    proposal = {
        "name": "program_task",
        "description": "Development candidate",
        "source": SOURCE,
        "parameters": {
            "type": "object",
            "properties": {"instruction": {"type": "string", "maxLength": 500}},
            "required": ["instruction"],
            "additionalProperties": False,
        },
    }
    install_program(registry, proposal)
    from types import SimpleNamespace

    ctx = SimpleNamespace(trace=SimpleNamespace(emit=lambda *args, **kwargs: None))
    run = registry.tools["program_task"].handler({"instruction": "pick"}, ctx)
    assert next(run) == {"motion": 1}
    with pytest.raises(StopIteration) as end:
        next(run)
    assert end.value.value.error_code == "motion_stalled"
    assert len(calls) == 1


@pytest.mark.parametrize(
    "source",
    [
        "import os\n" + SOURCE,
        SOURCE.replace("range(4)", "range(1000000)"),
        SOURCE.replace("result = yield from", "api = args\n        result = yield from"),
        SOURCE.replace("return result", "return api.call"),
        SOURCE.replace("return result", "return api.__dict__"),
        SOURCE.replace("return result", 'return open("/etc/passwd")'),
        SOURCE.replace("return result", 'return args[args["instruction"]]'),
        SOURCE.replace('result["status"] != "succeeded"', "args == result"),
        SOURCE.replace("return result", 'return {args["instruction"]: result}'),
    ],
)
def test_host_escape_and_unbounded_work_are_rejected(source):
    with pytest.raises((ValueError, SyntaxError)):
        compile_program(source)


def test_shared_json_expansion_is_bounded_before_serialization():
    data = {"leaf": True}
    for _ in range(20):
        data = {"left": data, "right": data}
    with pytest.raises(ValueError):
        bounded_json(data)


def test_program_schema_cannot_reference_external_resources():
    proposal = {
        "name": "program_bad",
        "description": "bad",
        "source": SOURCE,
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
            "$ref": "https://untrusted.invalid/schema",
        },
    }
    with pytest.raises(ValueError, match="External references"):
        install_program(Registry(), proposal)
