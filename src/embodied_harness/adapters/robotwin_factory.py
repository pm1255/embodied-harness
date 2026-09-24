"""Native RoboTwin 2.0 runtime setup; no expert rollout or privileged grasp calls.

Requires rlinf-robotwin-runtime==0.1.1 and its separately downloaded assets.
This optional distribution is maintained by RLinf; it is not our contribution.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path
import re


def make_environment(*, seed, task, size=256):
    import yaml
    from robotwin.assets import validate_root
    from robotwin.config import load_task_config

    if not re.fullmatch(r"[a-z][a-z0-9_]*", task):
        raise ValueError("Invalid RoboTwin task module")
    root = os.environ.get("ROBOTWIN_ASSETS_ROOT")
    if not root:
        raise ValueError("Set ROBOTWIN_ASSETS_ROOT to the downloaded runtime asset root")
    root = Path(validate_root(root)["root"])
    os.environ["ASSETS_PATH"] = str(root)  # Native runtime compatibility alias.
    config = load_task_config("demo_clean")
    embodiment = root / "assets/embodiments/aloha-agilex"
    robot_config = yaml.safe_load((embodiment / "config.yml").read_text())
    config.update(
        task_name=task,
        eval_mode=True,
        eval_video_log=False,
        render_freq=0,
        save_data=False,
        collect_data=False,
        planner_backend="mplib",
        dual_arm_embodied=True,
        embodiment_name="aloha-agilex",
        head_camera_h=size,
        head_camera_w=size,
        left_robot_file=str(embodiment),
        right_robot_file=str(embodiment),
        left_embodiment_config=robot_config,
        right_embodiment_config=robot_config,
    )
    native = getattr(importlib.import_module("robotwin.envs." + task), task)()
    native.setup_demo(now_ep_num=0, seed=seed, is_test=True, **config)
    return native


def make_source_environment(*, seed, task, size=256):
    """Operator-selected upstream source checkout; each episode runs in a process.

    No expert trajectory or contact-point grasp action is invoked. Source/asset
    versions must be recorded by the operator; they differ from the wheel above.
    """
    import random
    import sys
    import yaml

    if not re.fullmatch(r"[a-z][a-z0-9_]*", task):
        raise ValueError("Invalid RoboTwin task module")
    root = Path(os.environ["ROBOTWIN_SOURCE_ROOT"]).resolve()
    if not (root / "envs/_base_task.py").is_file():
        raise ValueError("ROBOTWIN_SOURCE_ROOT must contain the native envs package")
    # Native upstream code resolves some files against its source root. The
    # benchmark runner isolates this cwd change to a simulator subprocess.
    os.chdir(root)
    sys.path.insert(0, str(root))
    config = yaml.safe_load((root / "task_config/demo_clean.yml").read_text())
    embodiment = root / "assets/embodiments/aloha-agilex"
    robot_config = yaml.safe_load((embodiment / "config.yml").read_text())
    config.update(
        task_name=task,
        task_config="demo_clean",
        eval_mode=True,
        eval_video_log=False,
        render_freq=0,
        save_data=False,
        collect_data=False,
        save_freq=None,
        dual_arm_embodied=True,
        head_camera_h=size,
        head_camera_w=size,
        left_robot_file=str(embodiment),
        right_robot_file=str(embodiment),
        left_embodiment_config=robot_config,
        right_embodiment_config=robot_config,
    )
    random.seed(seed)
    native = getattr(importlib.import_module("envs." + task), task)()
    native.setup_demo(now_ep_num=0, seed=seed, is_test=True, **config)
    return native
