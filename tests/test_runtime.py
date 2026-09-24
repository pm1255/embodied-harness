import time

import pytest

from embodied_harness.adapters.toy import ToyEnvironment
from embodied_harness.cli import DemoPlanner, aggregate, step
from embodied_harness.runner import run_episode
from embodied_harness.runtime import Executor, Tool
from embodied_harness.tools import make_registry, object_schema
from embodied_harness.trace import Trace


@pytest.fixture
def stack(tmp_path):
    env = ToyEnvironment(tmp_path / "capture")
    env.reset(0)
    registry = make_registry(env)
    trace = Trace(tmp_path / "run")
    executor = Executor(env, registry, trace)
    yield env, registry, trace, executor
    if not trace.file.closed:
        trace.file.close()


def move(identifier="a"):
    return step(identifier, "move_relative", {"arm": "arm", "direction": "up", "distance": "large"})


def test_entire_plan_validated_before_motion(stack):
    env, _, _, executor = stack
    bad = step("b", "nonexistent", {})
    with pytest.raises(Exception):
        executor.execute({"steps": [move(), bad]})
    assert env.tick == 0


@pytest.mark.parametrize("steps", [[], [move()] * 2, [move(str(i)) for i in range(9)]])
def test_plan_limits(stack, steps):
    with pytest.raises(ValueError):
        stack[-1].execute({"steps": steps})
    assert stack[0].tick == 0


def test_unknown_fact_requires_new_decision(stack):
    action = move()
    action["require_fact"] = "object_grasped"
    result = stack[-1].execute({"steps": [action]})
    assert result["status"] == "needs_decision"
    assert stack[0].tick == 0


def test_failure_stops_remaining_plan(stack):
    env, _, _, executor = stack
    env.fault_after = 2
    result = executor.execute(
        {"steps": [move(), step("b", "set_gripper", {"arm": "arm", "state": "closed"})]}
    )
    assert result["status"] == "needs_decision"
    assert len(result["steps"]) == 1
    assert env.gripper == "open"
    assert env.stops >= 1


def test_cancelled_before_execution(stack):
    stack[-1].cancel()
    assert stack[-1].execute({"steps": [move()]})["status"] == "cancelled"
    assert stack[0].tick == 0


def test_cancel_during_motion_no_background_worker(stack):
    env, _, _, executor = stack
    original = env.servo

    def cancelling(*args):
        original(*args)
        if env.tick == 2:
            executor.cancel()

    env.servo = cancelling
    report = executor.execute({"steps": [move()]})
    assert report["status"] == "cancelled"
    assert env.tick == 2


def test_tick_budget_is_global_across_plans(stack):
    env, _, _, executor = stack
    executor.max_control_ticks = 3
    assert executor.execute({"steps": [move()]})["status"] == "needs_decision"
    executor.execute({"steps": [move("b")]})
    assert env.tick == 3


def test_timeout_stops_cooperative_tool(stack):
    _, registry, _, executor = stack

    def slow(args, ctx):
        while True:
            time.sleep(0.002)
            yield {"progress": "waiting"}

    registry.add(Tool("slow", "test", object_schema({}), slow, timeout_s=0.001))
    report = executor.execute({"steps": [step("a", "slow", {})]})
    assert report["steps"][0]["status"] == "timed_out"


def test_single_owner_lock(stack):
    env, _, _, executor = stack
    executor.lock.acquire()
    try:
        with pytest.raises(RuntimeError, match="already owns"):
            executor.execute({"steps": [move()]})
        assert env.tick == 0
    finally:
        executor.lock.release()


def test_gripper_result_does_not_claim_grasp(stack):
    report = stack[-1].execute(
        {"steps": [step("g", "set_gripper", {"arm": "arm", "state": "closed"})]}
    )
    assert report["steps"][0]["data"]["grasp_verified"] is False


def test_batching_reduces_fixture_decisions_without_changing_motion(tmp_path):
    runs = []
    for per_tool in (False, True):
        directory = tmp_path / str(per_tool)
        env = ToyEnvironment(directory / "capture")
        trace = Trace(directory)
        summary = run_episode(env, DemoPlanner(per_tool), trace, "fixture")
        assert env.closed
        assert summary["success"]
        assert summary["api_calls"] == 0
        runs.append((summary, env.position))
        assert (directory / "index.html").exists()
    assert runs[0][0]["decisions"] == 2
    assert runs[1][0]["decisions"] == 4
    assert runs[0][1] == runs[1][1]
    assert aggregate(tmp_path)[0]["episodes"] == 2


def test_trace_does_not_merge_runs_or_inject_html(tmp_path):
    trace = Trace(tmp_path)
    trace.emit("untrusted", text="</script><script>alert(1)</script>")
    trace.finish({"status": "test"})
    html = (tmp_path / "index.html").read_text()
    assert "</script><script>alert" not in html
    with pytest.raises(FileExistsError):
        Trace(tmp_path)


def test_environment_success_is_not_sent_to_planner(tmp_path):
    class Spy(DemoPlanner):
        def decide(self, task, observation, registry, history, trace):
            assert "success" not in observation.to_dict()
            assert "goal" not in observation.proprioception
            return super().decide(task, observation, registry, history, trace)

    summary = run_episode(
        ToyEnvironment(tmp_path / "capture"), Spy(), Trace(tmp_path / "run"), "test"
    )
    assert summary["success"]


def test_backend_exception_not_reported_as_task_failure(tmp_path):
    class Broken(ToyEnvironment):
        def reset(self, seed):
            raise OSError("renderer unavailable")

        def success(self):
            return None

    summary = run_episode(
        Broken(tmp_path / "capture"), DemoPlanner(), Trace(tmp_path / "run"), "test"
    )
    assert summary["status"] == "infrastructure_error"
    assert summary["environment_success"] is None


def test_allowlist_not_just_hidden_from_prompt(stack):
    assert "move_to_pixel" not in stack[1].tools
    with pytest.raises(Exception):
        stack[-1].execute({"steps": [step("a", "move_to_pixel", {})]})
