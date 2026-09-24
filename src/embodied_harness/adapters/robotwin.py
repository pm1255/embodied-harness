"""RoboTwin 2 bridge to a user-configured task factory.

The official task setup depends on task config, embodiment assets and evaluator
initialization. The factory must return a fresh, evaluation-ready TASK_ENV.
This bridge uses get_obs()/take_action(action_type='ee') and never grasp_actor,
object poses, contact-point annotations or demonstration trajectories.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import numpy as np
from PIL import Image

from ..protocol import CameraFrame, Observation
from . import load_factory


class RoboTwinEnvironment:
    name = "robotwin"

    def __init__(self, directory, factory, task, size=256):
        self.factory, self.task, self.size = factory, task, size
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.env = None
        # No guessed depth units/extrinsics. Projection remains unavailable until
        # a deployment supplies a tested calibrated sensor implementation.
        self.capabilities = {
            "arms": ["left", "right"],
            "cameras": [],
            "cartesian_servo": True,
            "surface_projection": False,
            "collision_planning": False,
            "control_frame": "world",
            "orientation": "preserve_current",
            "observation_source": "rgb_and_proprioception",
            "execution_note": "native take_action may perform multiple internal physics steps",
        }

    def reset(self, seed):
        self.close()
        self.seed = seed
        self.env = load_factory(self.factory)(seed=seed, task=self.task, size=self.size)
        self.episode = uuid.uuid4().hex
        self.frame = self.tick = 0
        for name in ("get_obs", "take_action", "close_env"):
            if not callable(getattr(self.env, name, None)):
                raise TypeError(f"RoboTwin factory returned an incompatible task: missing {name}")
        return self.observe()

    def observe(self):
        self.raw_obs = self.env.get_obs()
        self.raw_obs_tick = self.tick
        self.frame += 1
        frames = []
        for camera, data in self.raw_obs["observation"].items():
            if "rgb" not in data:
                continue
            image = np.asarray(data["rgb"])
            if image.dtype != np.uint8:
                raise ValueError("RoboTwin RGB frames must be uint8")
            path = self.directory / f"{self.episode}_{self.frame}_{camera}.png"
            Image.fromarray(image).save(path)
            frames.append(
                CameraFrame(
                    camera, image.shape[1], image.shape[0], str(path.resolve()), float(self.tick)
                )
            )
        if not frames:
            raise ValueError("Enable rgb in RoboTwin task data_type")
        poses = self.raw_obs["endpose"]
        if any(f"{arm}_endpose" not in poses for arm in ("left", "right")):
            raise ValueError("Enable endpose in RoboTwin task data_type")
        self.capabilities["cameras"] = [f.name for f in frames]
        return Observation(
            f"{self.episode}:{self.frame}",
            self.episode,
            float(self.tick),
            frames,
            {"endpose": {k: np.asarray(v).tolist() for k, v in poses.items()}},
            {},
        )

    def ee_position(self, arm="left"):
        if arm not in ("left", "right"):
            raise ValueError("Unknown arm")
        return np.asarray(self.env.get_arm_pose(arm))[:3].tolist()

    def servo(self, target, gripper, arm="left"):
        action = []
        for side in ("left", "right"):
            pose = np.asarray(self.env.get_arm_pose(side)).copy()
            grip = getattr(self.env.robot, f"get_{side}_gripper_val")()
            if side == arm:
                pose[:3] += np.clip(np.asarray(target) - pose[:3], -0.01, 0.01)
                grip = 0.0 if gripper == "closed" else 1.0
            # Preserve RoboTwin's native quaternion ordering unchanged.
            action.extend(pose.tolist() + [float(grip)])
        self.env.take_action(np.asarray(action), action_type="ee")
        self.tick += 1

    def surface_point(self, *args):
        raise NotImplementedError("Calibrated RoboTwin projection is not registered")

    def stop(self):
        pass  # Actions are synchronous; no new action is issued after cancellation.

    def success(self):
        if self.env is None:
            return None
        return bool(self.env.eval_success)

    def close(self):
        if self.env is not None:
            self.env.close_env()
            self.env = None
