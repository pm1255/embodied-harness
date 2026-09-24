"""MetaWorld 3.x Sawyer adapter using sensor images and robot proprioception."""

from __future__ import annotations

import uuid
from pathlib import Path

import numpy as np
from PIL import Image

from ..geometry import DepthCache, mujoco_camera, rotate_rgbd_180
from ..protocol import CameraFrame, Observation


class MetaWorldEnvironment:
    name = "metaworld"

    def __init__(self, directory, task="reach-v3", task_index=0, size=256, upright=True):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.task, self.task_index, self.size = task, task_index, size
        self.upright = upright
        self.env = self.renderer = None
        self.last_success = None
        self.depth = DepthCache()
        self.capabilities = {
            "arms": ["arm"],
            "cameras": ["corner", "corner2"],
            "cartesian_servo": True,
            "surface_projection": True,
            "collision_planning": False,
            "control_frame": "world",
            "orientation": "fixed_by_environment",
            "camera_raster_rotation_deg": 180 if upright else 0,
            "observation_source": "rendered_rgbd_and_proprioception",
        }

    def reset(self, seed):
        import metaworld
        import mujoco

        self.close()
        benchmark = metaworld.MT1(self.task, seed=seed)
        self.env = benchmark.train_classes[self.task](render_mode="rgb_array")
        tasks = [task for task in benchmark.train_tasks if task.env_name == self.task]
        self.env.set_task(tasks[self.task_index])
        self.env.reset(seed=seed)
        self.renderer = mujoco.Renderer(self.env.model, height=self.size, width=self.size)
        self.tick = self.frame = 0
        self.episode = uuid.uuid4().hex
        self.last_success = None
        self.terminated = False
        self.capabilities["workspace_m"] = [self.env.hand_low.tolist(), self.env.hand_high.tolist()]
        return self.observe()

    def observe(self):
        self.frame += 1
        oid = f"{self.episode}:{self.frame}"
        self.depth.begin(oid, self.tick)
        frames = []
        for camera in self.capabilities["cameras"]:
            self.renderer.disable_depth_rendering()
            self.renderer.update_scene(self.env.data, camera=camera)
            rgb = self.renderer.render().copy()
            self.renderer.enable_depth_rendering()
            depth = self.renderer.render().copy()  # modern MuJoCo renderer returns meters
            K, T = mujoco_camera(self.env.model, self.env.data, camera, self.size, self.size)
            if self.upright:
                rgb, depth, K, T = rotate_rgbd_180(rgb, depth, K, T)
            self.depth.cameras[camera] = (depth, K, T)
            path = self.directory / f"{self.episode}_{self.frame}_{camera}.png"
            Image.fromarray(rgb).save(path)
            frames.append(
                CameraFrame(
                    camera,
                    self.size,
                    self.size,
                    str(path.resolve()),
                    float(self.env.data.time),
                    raster_rotation_deg=180 if self.upright else 0,
                )
            )
        # Never forward _get_obs(): it includes privileged object and goal state.
        return Observation(
            oid,
            self.episode,
            float(self.env.data.time),
            frames,
            {
                "eef_position_m": self.ee_position(),
                "joint_position_rad": self.env.data.qpos[:7].tolist(),
            },
            {},
        )

    def ee_position(self, arm="arm"):
        if arm != "arm":
            raise ValueError("Unknown arm")
        return self.env.get_endeff_pos().tolist()

    def surface_point(self, observation_id, camera, pixel):
        return self.depth.project(observation_id, self.tick, camera, pixel)

    def servo(self, target, gripper, arm="arm"):
        if self.terminated:
            raise RuntimeError("Environment terminated; no more actions are allowed")
        # SawyerXYZEnv maps xyz action to a 1cm mocap displacement.
        delta = np.clip((np.asarray(target) - self.ee_position(arm)) / self.env.action_scale, -1, 1)
        _, _, terminated, truncated, info = self.env.step(
            np.r_[delta, 1 if gripper == "closed" else -1]
        )
        self.tick += 1
        self.last_success = bool(info["success"])
        self.terminated = bool(terminated or truncated)

    def stop(self):
        # Simulation is synchronous: it advances only inside servo().
        pass

    def success(self):
        return self.last_success

    def close(self):
        if self.renderer is not None:
            self.renderer.close()
            self.renderer = None
        if self.env is not None:
            self.env.close()
            self.env = None
