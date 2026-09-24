"""Separate LIBERO and RoboCasa constructors, shared calibrated sensor capture.

Only fixed-impedance delta OSC controllers are accepted. Incompatible joint,
whole-body IK, and absolute-action controllers fail explicitly at reset.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import numpy as np
from PIL import Image

from ..geometry import DepthCache, mujoco_camera
from ..protocol import CameraFrame, Observation


class RobosuiteEnvironment:
    def __init__(self, directory, size=256):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.size = size
        self.env = None
        self.depth = DepthCache()

    def _reset(self, seed):
        self.seed = seed
        self.tick = self.frame = 0
        self.episode = uuid.uuid4().hex
        self.done = False
        self.env.reset()
        if getattr(self, "initial_state", None) is not None:
            self.env.set_init_state(self.initial_state)
            # Standard evaluation settling; no demonstration actions are replayed.
            for _ in range(10):
                self.env.step(np.array([0, 0, 0, 0, 0, 0, -1]))
        self.robot = self.env.robots[0]
        if hasattr(self.robot, "part_controllers"):
            self.arm_key = self.robot.arms[0]
            self.controller = self.robot.part_controllers[self.arm_key]
        else:
            self.arm_key = None
            self.controller = self.robot.controller
        c = self.controller
        delta = getattr(c, "input_type", None) == "delta" or getattr(c, "use_delta", False)
        if (
            type(c).__name__ != "OperationalSpaceController"
            or not delta
            or c.impedance_mode != "fixed"
        ):
            raise ValueError(
                "This adapter requires fixed-impedance delta OSC_POSE; configure the robot factory"
            )
        if self.arm_key and self.arm_key + "_gripper" not in self.robot._action_split_indexes:
            raise ValueError("Missing named gripper action channel")
        return self.observe()

    @property
    def raw(self):
        return self.env.env if hasattr(self.env, "env") else self.env

    def observe(self):
        self.frame += 1
        oid = f"{self.episode}:{self.frame}"
        self.depth.begin(oid, self.tick)
        sim = self.env.sim
        near = sim.model.vis.map.znear * sim.model.stat.extent
        far = sim.model.vis.map.zfar * sim.model.stat.extent
        frames = []
        for camera in self.capabilities["cameras"]:
            rgb, raw_depth = sim.render(
                width=self.size, height=self.size, camera_name=camera, depth=True
            )
            rgb = np.ascontiguousarray(rgb[::-1])
            depth = near / (1 - raw_depth[::-1] * (1 - near / far))
            K, T = mujoco_camera(sim.model, sim.data, camera, self.size, self.size)
            self.depth.cameras[camera] = (depth, K, T)
            path = self.directory / f"{self.episode}_{self.frame}_{camera}.png"
            Image.fromarray(rgb).save(path)
            frames.append(
                CameraFrame(camera, self.size, self.size, str(path.resolve()), float(sim.data.time))
            )
        return Observation(
            oid,
            self.episode,
            float(sim.data.time),
            frames,
            {
                "eef_position_m": self.ee_position(),
                "joint_position_rad": np.asarray(self.robot._joint_positions).tolist(),
            },
            {},
        )

    def ee_position(self, arm="arm"):
        if arm != "arm":
            raise ValueError("Unknown arm")
        self.controller.update(force=True)
        # robosuite 1.4 uses ee_pos; 1.5+ renamed this world-space sensor ref_pos.
        position = getattr(self.controller, "ref_pos", None)
        if position is None:
            position = self.controller.ee_pos
        return np.asarray(position).tolist()

    def surface_point(self, observation_id, camera, pixel):
        return self.depth.project(observation_id, self.tick, camera, pixel)

    def servo(self, target, gripper, arm="arm"):
        if self.done:
            raise RuntimeError("Environment terminated")
        c = self.controller
        displacement = np.clip(np.asarray(target) - self.ee_position(arm), -0.01, 0.01)
        if getattr(c, "input_ref_frame", "world") == "base":
            # RoboCasa's mobile Panda accepts base-frame deltas. The target and
            # measured TCP remain world-frame; rotate vectors, never positions.
            displacement = np.asarray(c.origin_ori).T @ displacement
        elif getattr(c, "input_ref_frame", "world") != "world":
            raise ValueError("Unsupported OSC input reference frame")
        # Invert OSC's actual configured input/output scaling instead of assuming 5cm.
        low, high = np.asarray(c.output_min)[:3], np.asarray(c.output_max)[:3]
        in_low, in_high = np.asarray(c.input_min)[:3], np.asarray(c.input_max)[:3]
        xyz = (displacement - low) / (high - low) * (in_high - in_low) + in_low
        pose_action = np.r_[np.clip(xyz, in_low, in_high), np.zeros(3)]
        grip = 1 if gripper == "closed" else -1
        if self.arm_key is None:
            action = np.r_[pose_action, grip]
        else:
            action = self.robot.create_action_vector(
                {self.arm_key: pose_action, self.arm_key + "_gripper": [grip]}
            )
        previous_time = float(self.env.sim.data.time)
        _, _, done, _ = self.env.step(action)
        if float(self.env.sim.data.time) < previous_time:
            raise RuntimeError("simulation_clock_reset: MuJoCo reset an unstable simulation")
        if (
            not np.isfinite(self.env.sim.data.qpos).all()
            or not np.isfinite(self.env.sim.data.qvel).all()
        ):
            raise RuntimeError("nonfinite_physics_state: stop this episode")
        self.tick += 1
        self.done = bool(done)

    def stop(self):
        pass  # Synchronous simulation does not advance outside servo().

    def success(self):
        if self.env is None:
            return None
        return bool(
            self.env.check_success()
            if hasattr(self.env, "check_success")
            else self.env._check_success()
        )

    def close(self):
        if self.env is not None:
            self.env.close()
            self.env = None


class LiberoEnvironment(RobosuiteEnvironment):
    name = "libero"

    def terminal_success(self):
        # BDDLBaseDomain.step explicitly replaces done with _check_success().
        # Retain that native terminal event: rendering calls sim.forward(), so
        # a later contact predicate query need not reproduce the step's event.
        return bool(getattr(self, "done", False))

    def __init__(
        self, directory, suite="libero_spatial", task_id=0, size=256, init_state_index=None
    ):
        super().__init__(directory, size)
        self.suite, self.task_id = suite, task_id
        self.init_state_index = init_state_index
        self.initial_state = None
        self.capabilities = {
            "arms": ["arm"],
            "cameras": ["agentview", "robot0_eye_in_hand"],
            "cartesian_servo": True,
            "surface_projection": True,
            "collision_planning": False,
            "control_frame": "world",
            "orientation": "preserve_current",
            "observation_source": "rendered_rgbd_and_proprioception",
        }

    def reset(self, seed):
        from libero.libero import benchmark, get_libero_path
        from libero.libero.envs import OffScreenRenderEnv

        self.close()
        tasks = benchmark.get_benchmark_dict()[self.suite]()
        task = tasks.get_task(self.task_id)
        if self.init_state_index is not None:
            states = tasks.get_task_init_states(self.task_id)
            if not 0 <= self.init_state_index < len(states):
                raise ValueError("init_state_index outside the official task initial states")
            self.initial_state = states[self.init_state_index]
        self.task_instruction = task.language
        bddl = Path(get_libero_path("bddl_files")) / task.problem_folder / task.bddl_file
        self.env = OffScreenRenderEnv(
            bddl_file_name=str(bddl),
            camera_heights=self.size,
            camera_widths=self.size,
            camera_depths=True,
            ignore_done=True,
        )
        self.env.seed(seed)
        # Optional official evaluation initial state; never demonstration action replay.
        return self._reset(seed)


class RoboCasaEnvironment(RobosuiteEnvironment):
    name = "robocasa"

    def __init__(self, directory, task="PickPlaceCounterToCabinet", size=256, factory=None):
        super().__init__(directory, size)
        self.task, self.factory = task, factory
        self.capabilities = {
            "arms": ["arm"],
            "cameras": ["robot0_agentview_left", "robot0_eye_in_hand"],
            "cartesian_servo": True,
            "surface_projection": True,
            "collision_planning": False,
            "control_frame": "world",
            "orientation": "preserve_current",
            "observation_source": "rendered_rgbd_and_proprioception",
        }

    def reset(self, seed):
        self.close()
        if self.factory:
            from . import load_factory

            self.env = load_factory(self.factory)(seed=seed, task=self.task, size=self.size)
        else:
            from robocasa.utils.env_utils import create_env

            self.env = create_env(
                env_name=self.task,
                camera_names=self.capabilities["cameras"],
                camera_widths=self.size,
                camera_heights=self.size,
                camera_depths=True,
                seed=seed,
            )
        return self._reset(seed)
