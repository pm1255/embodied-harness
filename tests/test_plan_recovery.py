import json
from types import SimpleNamespace

import pytest
from jsonschema import ValidationError

from embodied_harness.adapters.toy import ToyEnvironment
from embodied_harness.broker import DirectoryPlanner
from embodied_harness.protocol import ToolResult
from embodied_harness.runner import run_episode
from embodied_harness.runtime import Registry, Tool
from embodied_harness.trace import Trace


@pytest.mark.parametrize("budget,enabled,expected", [
    (2, True, "native_success"),
    (1, True, "decision_budget_exhausted"),
    (2, False, "infrastructure_error"),
])
@pytest.mark.parametrize("planner_validates", [True, False])
def test_rejected_511_character_plan_cannot_move_or_escape_budget(
    tmp_path, budget, enabled, expected, planner_validates
):
    env = ToyEnvironment(tmp_path / "camera")
    env.done = False
    env.terminal_success = lambda: env.done
    motions = []
    registry = Registry()

    def act(args, context):
        motions.append(args["instruction"])
        env.done = True
        yield {"native_tick": 1}
        return ToolResult("succeeded")

    registry.add(Tool("act", "Test action", {
        "type": "object", "properties": {"instruction": {"type": "string", "maxLength": 500}},
        "required": ["instruction"], "additionalProperties": False,
    }, act))

    class Planner:
        calls = 0

        def decide(self, task, observation, tools, history, trace):
            self.calls += 1
            if self.calls == 2:
                assert history[-1]["report"]["motion_executed"] is False
                assert "maxLength=500" in history[-1]["report"]["message"]
                assert motions == []
            plan = {"steps": [{"id": "a", "tool": "act", "require_fact": None,
                               "arguments": {"instruction": "x" * 511 if self.calls == 1 else "goal"}}]}
            if planner_validates:
                tools.validate(plan)
            return {"kind": "plan", "plan": plan}

    summary = run_episode(env, Planner(), Trace(tmp_path / "trace"), "goal", registry=registry,
                          max_decisions=budget, stop_on_native_success=True,
                          recover_invalid_plans=enabled)
    assert summary["status"] == expected
    assert summary["api_calls"] == (2 if expected == "native_success" else 1)
    assert motions == (["goal"] if expected == "native_success" else [])
    assert summary["control_ticks"] == len(motions)


def test_transport_error_is_not_retried_by_schema_recovery(tmp_path):
    class Planner:
        calls = 0

        def decide(self, *args):
            self.calls += 1
            raise TimeoutError("provider unavailable")

    summary = run_episode(ToyEnvironment(tmp_path / "camera"), Planner(),
                          Trace(tmp_path / "trace"), "goal", recover_invalid_plans=True)
    assert summary["status"] == "infrastructure_error"
    assert summary["api_calls"] == 1 and summary["control_ticks"] == 0


def test_broker_preserves_schema_error_type_and_cost(tmp_path, monkeypatch):
    from embodied_harness import broker

    monkeypatch.setattr(broker.uuid, "uuid4", lambda: SimpleNamespace(hex="known"))
    planner = DirectoryPlanner(tmp_path / "broker", "test")
    (planner.root / "known.response.json").write_text(json.dumps({
        "nonce": "known", "events": [], "calls": 1, "input_tokens": 20, "output_tokens": 10,
        "error": "full validation diagnostic", "error_kind": "ValidationError",
        "validation_message": "instruction exceeds maxLength=500", "decision": None,
    }))
    env = ToyEnvironment(tmp_path / "camera")
    trace = Trace(tmp_path / "trace")
    with pytest.raises(ValidationError, match="maxLength=500"):
        planner.decide("goal", env.reset(0), Registry(), [], trace)
    assert planner.calls == 1 and planner.input_tokens == 20 and planner.output_tokens == 10
    assert env.tick == 0
    env.close()
    trace.file.close()
