"""Dependency-free kinematic demonstration. NOT a physics or GPT benchmark."""

from __future__ import annotations

import math
import random
import uuid
from pathlib import Path

from ..protocol import CameraFrame, Observation, ToolFailure


class ToyEnvironment:
    name = "toy"
    capabilities = {
        "arms": ["arm"],
        "cameras": ["front", "side"],
        "cartesian_servo": True,
        "surface_projection": False,
        "collision_planning": False,
        "workspace_m": [[-0.5, -0.5, 0.0], [0.5, 0.5, 0.8]],
        "observation_source": "synthetic_kinematic_demo",
        "control_frame": "world",
    }

    def __init__(self, directory, fault_after: int | None = None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.fault_after = fault_after
        self.stops = 0
        self.closed = False

    def reset(self, seed):
        self.episode = uuid.uuid4().hex
        self.tick = self.frame = 0
        self.position = [random.Random(seed).uniform(-0.01, 0.01), 0, 0.2]
        self.start = list(self.position)
        self.gripper = "open"
        return self.observe()

    def observe(self):
        self.frame += 1
        frames = []
        for name, axis in [("front", 0), ("side", 1)]:
            x, y = 240 + self.position[axis] * 350, 270 - self.position[2] * 300
            svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="480" height="320" viewBox="0 0 480 320">
<rect width="480" height="320" fill="#122430"/><path d="M20 270H460" stroke="#52727c"/>
<path d="M240 270L200 170L{x} {y}" fill="none" stroke="#a4bfc9" stroke-width="16"/>
<circle cx="{x}" cy="{y}" r="10" fill="#58e0b7"/>
<text x="20" y="30" fill="white" font-family="sans-serif" font-size="16">{name} · OFFLINE KINEMATIC DEMO</text>
<text x="20" y="300" fill="#a4bfc9" font-family="monospace" font-size="13">tick {self.tick} / gripper {self.gripper}</text></svg>'''
            path = self.directory / f"{self.episode}_{self.frame}_{name}.svg"
            path.write_text(svg, encoding="utf-8")
            frames.append(CameraFrame(name, 480, 320, str(path.resolve()), self.tick / 20))
        return Observation(
            f"{self.episode}:{self.frame}",
            self.episode,
            self.tick / 20,
            frames,
            {"eef_position_m": self.position[:], "gripper_command": self.gripper},
            {},
        )

    def ee_position(self, arm="arm"):
        return self.position[:]

    def servo(self, target, gripper, arm="arm"):
        self.tick += 1
        if self.fault_after is not None and self.tick >= self.fault_after:
            raise ToolFailure("Injected actuator failure (offline demonstration)")
        delta = [b - a for a, b in zip(self.position, target)]
        norm = math.sqrt(sum(v * v for v in delta))
        scale = min(1.0, 0.01 / max(norm, 1e-12))
        self.position = [a + d * scale for a, d in zip(self.position, delta)]
        self.gripper = gripper

    def surface_point(self, *args):
        raise NotImplementedError("The toy fixture has no RGB-D sensor")

    def stop(self):
        self.stops += 1

    def success(self):
        return self.position[2] >= self.start[2] + 0.075 and self.gripper == "closed"

    def close(self):
        self.closed = True
