"""Small, honest primitives. Closing a gripper does NOT report a grasp."""

from __future__ import annotations

import math

from .protocol import ToolResult
from .runtime import Registry, Tool


def object_schema(properties: dict) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def choice(*values) -> dict:
    return {"type": "string", "enum": list(values)}


def distance(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def make_registry(env) -> Registry:
    registry = Registry()
    arms = env.capabilities.get("arms", ["arm"])
    grippers = {arm: "open" for arm in arms}

    def move_to(target, arm, ctx):
        if len(target) != 3 or not all(math.isfinite(x) for x in target):
            return ToolResult("failed", error_code="invalid_target")
        bounds = env.capabilities.get("workspace_m")
        if bounds and any(not bounds[0][i] <= target[i] <= bounds[1][i] for i in range(3)):
            return ToolResult("failed", error_code="outside_workspace")
        previous = distance(env.ee_position(arm), target)
        stalled = 0
        for _ in range(120):
            current = env.ee_position(arm)
            error = distance(current, target)
            if error < 0.012:
                return ToolResult(
                    "succeeded",
                    {
                        "target_m": target,
                        "error_m": error,
                        "meaning": "TCP reached target; object contact/grasp is not verified",
                    },
                )
            env.servo(target, grippers[arm], arm)
            actual = env.ee_position(arm)
            now = distance(actual, target)
            stalled = stalled + 1 if previous - now < 0.00005 else 0
            previous = now
            yield {"target_m": target, "actual_m": actual, "error_m": now, "arm": arm}
            if stalled >= 30:
                return ToolResult("failed", {"error_m": now}, "motion_stalled")
            if ctx.trace.count % 8 == 0:
                ctx.observe()
        return ToolResult("failed", {"error_m": previous}, "target_not_reached")

    def relative(args, ctx):
        axes = {
            "left": (1, 1),
            "right": (1, -1),
            "forward": (0, 1),
            "backward": (0, -1),
            "up": (2, 1),
            "down": (2, -1),
        }
        axis, sign = axes[args["direction"]]
        target = list(env.ee_position(args["arm"]))
        target[axis] += sign * {"small": 0.02, "medium": 0.05, "large": 0.10}[args["distance"]]
        return (yield from move_to(target, args["arm"], ctx))

    def pixel(args, ctx):
        target = list(env.surface_point(args["observation_id"], args["camera"], args["pixel"]))
        target[2] += 0.08 if args["approach"] == "above" else 0.0
        ctx.trace.emit(
            "geometry",
            source="current_rgbd_surface",
            pixel=args["pixel"],
            camera=args["camera"],
            observation_id=args["observation_id"],
            target_m=target,
            approach=args["approach"],
        )
        return (yield from move_to(target, args["arm"], ctx))

    def gripper(args, ctx):
        arm = args["arm"]
        grippers[arm] = args["state"]
        target = list(env.ee_position(arm))
        for _ in range(15):
            env.servo(target, args["state"], arm)
            yield {"arm": arm, "gripper_command": args["state"], "actual_m": env.ee_position(arm)}
        return ToolResult("succeeded", {"command": args["state"], "grasp_verified": False})

    if env.capabilities.get("cartesian_servo"):
        registry.add(
            Tool(
                "move_relative",
                "Move TCP in robot/world axes: forward +X, left +Y, up +Z. "
                "small=2cm, medium=5cm, large=10cm. Preserves orientation. "
                "Local servo only; no collision planning.",
                object_schema(
                    {
                        "arm": choice(*arms),
                        "direction": choice("left", "right", "forward", "backward", "up", "down"),
                        "distance": choice("small", "medium", "large"),
                    }
                ),
                relative,
            )
        )
        registry.add(
            Tool(
                "set_gripper",
                "Command gripper open/close while holding TCP position. Completion is not grasp success.",
                object_schema({"arm": choice(*arms), "state": choice("open", "closed")}),
                gripper,
            )
        )
    if env.capabilities.get("surface_projection") and env.capabilities.get("cartesian_servo"):
        registry.add(
            Tool(
                "move_to_pixel",
                "Reach a currently visible RGB-D surface pixel, or 8cm above it. "
                "Not a free-space waypoint or grasp-pose estimator. Preserves orientation; "
                "no collision avoidance. Use a fresh observation_id. Pixel [u,v], top-left origin.",
                object_schema(
                    {
                        "arm": choice(*arms),
                        "observation_id": {"type": "string"},
                        "camera": choice(*env.capabilities["cameras"]),
                        "pixel": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "minItems": 2,
                            "maxItems": 2,
                        },
                        "approach": choice("above", "surface"),
                    }
                ),
                pixel,
            )
        )
    return registry
