"""Run with --tools-factory examples.custom_tools:register from the repo root."""

from embodied_harness.protocol import ToolResult
from embodied_harness.runtime import Tool
from embodied_harness.tools import object_schema


def register(env, registry):
    def hold(args, ctx):
        target = env.ee_position()
        for _ in range(10):
            env.servo(target, "open")
            yield {"actual_m": env.ee_position(), "target_m": target}
        return ToolResult("succeeded", {"meaning": "hold command completed"})

    registry.add(
        Tool(
            "hold_open",
            "Hold TCP with open gripper for ten controller ticks.",
            object_schema({}),
            hold,
            max_ticks=11,
        )
    )
