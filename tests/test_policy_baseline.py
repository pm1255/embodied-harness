from embodied_harness.runner import run_episode
from embodied_harness.adapters.toy import ToyEnvironment
from embodied_harness.cli import DemoPlanner
from embodied_harness.trace import Trace


def test_native_evaluator_can_end_without_requesting_another_model_decision(tmp_path):
    env = ToyEnvironment(tmp_path / "camera")
    # Isolate the evaluator boundary: a trusted test evaluator says the executed
    # action completed the goal; the planner's observation remains sensor-only.
    env.success = lambda: True
    planner = DemoPlanner()
    result = run_episode(
        env, planner, Trace(tmp_path / "trace"), "test", stop_on_native_success=True
    )
    assert result["status"] == "native_success"
    assert result["decisions"] == 1
    assert result["success"]


def test_native_success_does_not_override_cancellation(tmp_path, monkeypatch):
    from embodied_harness import runner

    class CancelledExecutor:
        ticks = 0

        def __init__(self, *args, **kwargs):
            pass

        def execute(self, plan):
            return {"status": "cancelled", "steps": []}

    monkeypatch.setattr(runner, "Executor", CancelledExecutor)
    env = ToyEnvironment(tmp_path / "camera")
    env.success = lambda: True
    result = run_episode(
        env, DemoPlanner(), Trace(tmp_path / "trace"), "test", stop_on_native_success=True
    )
    assert result["status"] == "cancelled" and not result["success"]


def test_libero_policy_yields_terminal_action_then_stops_before_next_action():
    import numpy as np
    from types import SimpleNamespace
    from embodied_harness.runtime import Registry
    from embodied_harness.vla import register_policy

    calls = []

    class Native:
        sim = SimpleNamespace(data=SimpleNamespace(time=0.0, qpos=np.zeros(7)))

        def step(self, action):
            calls.append(action)
            self.sim.data.time += 0.05
            return None, 1.0, True, {}

    env = SimpleNamespace(name="libero", env=Native(), done=False, tick=0)
    endpoint = SimpleNamespace(
        metadata={"contract": "libero_franka_osc7_v1"}, timeout=1, infer=lambda *_: np.zeros((5, 7))
    )
    registry = Registry()
    register_policy(env, registry, endpoint)
    context = SimpleNamespace(
        trace=SimpleNamespace(emit=lambda *a, **k: None), observe=lambda: None
    )
    generator = registry.tools["run_vla"].handler({"instruction": "task", "chunks": 8}, context)
    next(generator)
    try:
        next(generator)
        assert False, "No action may follow the native terminal state"
    except StopIteration as stop:
        assert stop.value.status == "succeeded"
    assert len(calls) == 1 and env.tick == 1


def test_native_terminal_event_survives_later_contact_query_and_stops_batch(tmp_path):
    from embodied_harness.runtime import Registry, Tool
    from embodied_harness.protocol import ToolResult

    env = ToyEnvironment(tmp_path / "camera")
    env.done = False
    env.success = lambda: False  # A later render/contact query does not repeat the event.
    env.terminal_success = lambda: env.done
    calls = []

    def action(args, ctx):
        calls.append("action")
        env.done = True
        yield {"native_tick": 1}
        calls.append("after terminal yield")  # Must not run, even inside a composed skill.
        return ToolResult("succeeded")

    registry = Registry()
    registry.add(
        Tool(
            "segment",
            "Native task segment",
            {"type": "object", "properties": {}, "additionalProperties": False},
            action,
        )
    )

    class Planner:
        def decide(self, *args):
            return {
                "kind": "plan",
                "plan": {
                    "steps": [
                        {"id": str(i), "tool": "segment", "arguments": {}, "require_fact": None}
                        for i in range(2)
                    ]
                },
            }

    result = run_episode(
        env,
        Planner(),
        Trace(tmp_path / "trace"),
        "test",
        registry=registry,
        stop_on_native_success=True,
    )
    assert calls == ["action"]
    assert result["status"] == "native_success"
    assert result["native_terminal_success"] is True
    assert result["success"] and result["final_state_success"] is False


def test_later_true_predicate_cannot_replace_a_missing_native_terminal_event(tmp_path):
    env = ToyEnvironment(tmp_path / "camera")
    env.success = lambda: True
    env.terminal_success = lambda: False

    class Finish:
        def decide(self, *args):
            return {
                "kind": "finish",
                "outcome": "completed",
                "summary": "visually appears complete",
            }

    result = run_episode(
        env, Finish(), Trace(tmp_path / "trace"), "test", stop_on_native_success=True
    )
    assert result["final_state_success"] is True
    assert result["native_terminal_success"] is False
    assert result["success"] is False
