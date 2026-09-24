"""Episode lifecycle and evaluation separated from agent-visible observations."""

from __future__ import annotations

import time

from .runtime import Executor
from .tools import make_registry


def run_episode(
    env,
    planner,
    trace,
    task: str,
    seed=0,
    max_decisions=12,
    max_control_ticks=1200,
    registry=None,
    tools_factory=None,
    stop_on_native_success=False,
):
    started = time.monotonic()
    status = "decision_budget_exhausted"
    outcome = None
    history = []
    decisions = 0
    executor = None
    terminal_success = None
    terminal_check = getattr(env, "terminal_success", None) if stop_on_native_success else None
    trace.emit(
        "episode_start",
        task=task,
        seed=seed,
        environment=env.name,
        capabilities=env.capabilities,
        planner=type(planner).__name__,
        model=getattr(planner, "model", None),
        max_decisions=max_decisions,
        max_control_ticks=max_control_ticks,
        privileged_task_state_used=False,
        stop_on_native_success=stop_on_native_success,
    )
    try:
        observation = env.reset(seed)
        registry = registry or make_registry(env)
        if tools_factory:
            tools_factory(env, registry)
        executor = Executor(
            env, registry, trace, max_control_ticks, terminal_condition=terminal_check
        )
        trace.emit("tool_registry", tools=registry.descriptions())
        for _ in range(max_decisions):
            trace.observation(observation)
            decisions += 1
            decision = planner.decide(task, observation, registry, history, trace)
            if decision["kind"] == "finish":
                status = "agent_finished"
                outcome = decision["outcome"]
                trace.emit("agent_finish", outcome=decision["outcome"], summary=decision["summary"])
                break
            report = executor.execute(decision["plan"])
            history.append({"plan": decision["plan"], "report": report})
            if report["status"] == "cancelled":
                status = "cancelled"
                break
            if stop_on_native_success and (
                terminal_check() is True if terminal_check else env.success()
            ):
                terminal_success = True
                status = "native_success"
                trace.emit("evaluator_stop", reason="native_success", agent_feedback=False)
                break
            if executor.ticks >= max_control_ticks:
                status = "control_budget_exhausted"
                break
            observation = env.observe()
    except KeyboardInterrupt:
        if executor:
            executor.cancel()
        status = "cancelled"
    except Exception as exc:
        status = "infrastructure_error"
        trace.emit("error", error_type=type(exc).__name__, message=str(exc))
    finally:
        try:
            env.stop()
            success = env.success()
            if terminal_check:
                terminal_success = terminal_check() is True
        except Exception as exc:
            success = None
            trace.emit("evaluation_error", error_type=type(exc).__name__, message=str(exc))
            if status != "cancelled":
                status = "infrastructure_error"
        try:
            env.close()
        finally:
            final_state_success = success
            if terminal_success is not None:
                success = terminal_success
            summary = {
                "schema_version": 1,
                "environment": env.name,
                "task": task,
                "seed": seed,
                "status": status,
                "agent_outcome": outcome,
                "environment_success": success,
                "final_state_success": final_state_success,
                "native_terminal_success": terminal_success,
                "success": success is True and status not in ("infrastructure_error", "cancelled"),
                "decisions": decisions,
                "api_calls": getattr(planner, "calls", 0),
                "input_tokens": getattr(planner, "input_tokens", 0),
                "output_tokens": getattr(planner, "output_tokens", 0),
                "control_ticks": executor.ticks if executor else 0,
                "wall_seconds": round(time.monotonic() - started, 4),
                "protocol": "offline_toy" if env.name == "toy" else "sensor_observation",
                "model_tested": getattr(planner, "model", None),
                "provider": getattr(planner, "provider_host", None),
                "api_mode": getattr(planner, "api_mode", None),
                "stream": getattr(planner, "stream", None),
                "plan_mode": getattr(planner, "plan_mode", None),
                "stop_on_native_success": stop_on_native_success,
            }
            trace.finish(summary)
    return summary
