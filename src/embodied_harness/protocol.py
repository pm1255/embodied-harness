"""Versioned, simulator-independent observations and tool contracts.

No simulator task state or success predicate is included in a model observation.
The evaluator accesses success separately. Positions are meters in a documented
robot frame. Pixels are integer, top-left-origin coordinates in the named frame.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


class ToolFailure(RuntimeError):
    """An expected execution failure that can be presented for replanning."""


@dataclass
class CameraFrame:
    name: str
    width: int
    height: int
    image_path: str
    timestamp_s: float


@dataclass
class Observation:
    id: str
    episode_id: str
    timestamp_s: float
    frames: list[CameraFrame]
    proprioception: dict[str, Any]
    facts: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ToolResult:
    status: str  # succeeded / failed / cancelled / timed_out
    data: dict = field(default_factory=dict)
    error_code: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class Environment(Protocol):
    """A driver, not a task solver. Only the evaluator calls success()."""

    name: str
    capabilities: dict

    def reset(self, seed: int) -> Observation: ...
    def observe(self) -> Observation: ...
    def ee_position(self, arm: str = "arm") -> list[float]: ...
    def surface_point(self, observation_id: str, camera: str, pixel: list[int]) -> list[float]: ...
    def servo(self, target: list[float], gripper: str, arm: str = "arm") -> None: ...
    def stop(self) -> None: ...
    def success(self) -> bool | None: ...
    def close(self) -> None: ...
