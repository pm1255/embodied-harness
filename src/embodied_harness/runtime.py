"""Bounded plans execute locally until completion or a decision event.

Handlers are cooperative generators: one bounded controller tick per yield.
Cancellation never abandons a worker thread that could keep moving the robot.
Blocking native drivers must enforce their own I/O deadlines; this Python
runtime is not a hardware emergency stop or hard real-time controller.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from threading import Event, Lock
from typing import Callable, Iterator

from jsonschema import Draft202012Validator

from .protocol import ToolFailure, ToolResult


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    handler: Callable[[dict, "Context"], Iterator[dict]]
    timeout_s: float = 20.0
    max_ticks: int = 160


class Context:
    def __init__(self, env, trace, cancelled: Event):
        self.env, self.trace, self.cancelled = env, trace, cancelled

    def observe(self):
        obs = self.env.observe()
        self.trace.observation(obs)
        return obs


class Registry:
    def __init__(self):
        self.tools: dict[str, Tool] = {}

    def add(self, tool: Tool):
        if tool.name in self.tools:
            raise ValueError(f"Duplicate tool: {tool.name}")
        Draft202012Validator.check_schema(tool.parameters)
        self.tools[tool.name] = tool

    def schema(self) -> dict:
        # A discriminated union preserves each tool's actual arguments in GPT's schema.
        variants = []
        for tool in self.tools.values():
            variants.append(
                {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "id": {"type": "string"},
                        "tool": {"type": "string", "enum": [tool.name]},
                        "arguments": tool.parameters,
                        "require_fact": {"type": ["string", "null"]},
                    },
                    "required": ["id", "tool", "arguments", "require_fact"],
                }
            )
        if not variants:
            raise ValueError("No available tools")
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {"steps": {"type": "array", "items": {"anyOf": variants}}},
            "required": ["steps"],
        }

    def validate(self, plan: dict) -> None:
        # Reject NaN/Infinity even though Python's JSON decoder accepts them.
        json.dumps(plan, allow_nan=False)
        Draft202012Validator(self.schema()).validate(plan)
        if not 1 <= len(plan["steps"]) <= 8:
            raise ValueError("A plan must have 1..8 steps")
        ids = [step["id"] for step in plan["steps"]]
        if len(set(ids)) != len(ids) or any(not x or len(x) > 80 for x in ids):
            raise ValueError("Step IDs must be unique nonempty strings of at most 80 characters")

    def descriptions(self) -> list[dict]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
                "max_ticks": t.max_ticks,
                "timeout_s": t.timeout_s,
            }
            for t in self.tools.values()
        ]


class Executor:
    def __init__(
        self, env, registry: Registry, trace, max_control_ticks: int = 2000, terminal_condition=None
    ):
        self.env, self.registry, self.trace = env, registry, trace
        self.cancelled = Event()
        self.lock = Lock()
        self.ticks = 0
        self.max_control_ticks = max_control_ticks
        self.terminal_condition = terminal_condition

    def cancel(self):
        # Driver stop is called by the execution thread at its next tick boundary.
        self.cancelled.set()

    def execute(self, plan: dict) -> dict:
        # Validate the ENTIRE plan before allowing its first side effect.
        self.registry.validate(plan)
        if not self.lock.acquire(blocking=False):
            raise RuntimeError("An execution already owns this robot")
        try:
            self.trace.emit("plan", plan=plan)
            results = []
            ctx = Context(self.env, self.trace, self.cancelled)
            for step in plan["steps"]:
                if self.cancelled.is_set():
                    self.env.stop()
                    return {"status": "cancelled", "steps": results}
                condition = step["require_fact"]
                if condition is not None:
                    obs = ctx.observe()
                    if obs.facts.get(condition) is not True:
                        self.env.stop()
                        self.trace.emit(
                            "decision_required",
                            reason="precondition_unconfirmed",
                            step_id=step["id"],
                            fact=condition,
                        )
                        return {
                            "status": "needs_decision",
                            "reason": "precondition_unconfirmed",
                            "steps": results,
                        }
                result = self._run(step, ctx)
                results.append({"id": step["id"], **result.to_dict()})
                ctx.observe()
                if self.cancelled.is_set():
                    return {"status": "cancelled", "steps": results}
                if self.terminal_condition and self.terminal_condition() is True:
                    return {"status": "environment_terminated", "steps": results}
                if result.status != "succeeded":
                    self.trace.emit(
                        "decision_required", reason=result.error_code, step_id=step["id"]
                    )
                    return {
                        "status": "cancelled" if result.status == "cancelled" else "needs_decision",
                        "steps": results,
                    }
            return {"status": "completed", "steps": results}
        finally:
            self.lock.release()

    def _run(self, step: dict, ctx: Context) -> ToolResult:
        tool = self.registry.tools[step["tool"]]
        self.trace.emit("tool_start", step=step)
        started = time.monotonic()
        generator = None
        result = ToolResult("failed", error_code="missing_result")
        ticks = 0
        fatal = None
        try:
            generator = iter(tool.handler(step["arguments"], ctx))
            while True:
                if self.cancelled.is_set():
                    result = ToolResult("cancelled", error_code="cancelled")
                    break
                if time.monotonic() - started > tool.timeout_s:
                    result = ToolResult("timed_out", error_code="tool_timeout")
                    break
                if ticks >= tool.max_ticks or self.ticks >= self.max_control_ticks:
                    result = ToolResult("failed", error_code="tick_budget_exhausted")
                    break
                try:
                    event = next(generator)
                except StopIteration as stop:
                    result = stop.value if isinstance(stop.value, ToolResult) else result
                    break
                ticks += 1
                self.ticks += 1
                self.trace.emit("control_tick", step_id=step["id"], tick=ticks, **event)
                if self.terminal_condition and self.terminal_condition() is True:
                    self.trace.emit(
                        "environment_terminal",
                        condition_met=True,
                        source="adapter_terminal_condition",
                        control_tick=self.ticks,
                    )
                    result = ToolResult("succeeded", {"environment_terminated": True})
                    break
        except (ToolFailure, ValueError) as exc:
            result = ToolResult("failed", {"message": str(exc)}, type(exc).__name__)
        except Exception as exc:
            result = ToolResult("failed", {"message": str(exc)}, "infrastructure_error")
            fatal = exc
        finally:
            if generator is not None and hasattr(generator, "close"):
                generator.close()
            # Successful tools also stop streaming their setpoints at this boundary.
            self.env.stop()
        self.trace.emit(
            "tool_end",
            step_id=step["id"],
            duration_s=time.monotonic() - started,
            ticks=ticks,
            **result.to_dict(),
        )
        if fatal is not None:
            raise fatal
        return result
