"""Explicit, bounded VLA endpoint contract. A policy is a tool, not a success oracle."""
from __future__ import annotations

import base64
import json
import time
import urllib.request
import urllib.error
from urllib.parse import urlsplit

from .protocol import ToolResult
from .runtime import Tool
from .tools import object_schema


class PolicyEndpoint:
    """Operator-configured endpoint; the language model cannot choose URLs or checkpoints."""
    def __init__(self, url, expected_checkpoint, timeout_s=60):
        parsed = urlsplit(url)
        if parsed.scheme != "https" and not (
            parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost")
        ):
            raise ValueError("Use HTTPS or a loopback-only local policy server")
        if not 0 < timeout_s <= 120:
            raise ValueError("Policy I/O timeout must be bounded")
        self.url, self.timeout = url.rstrip("/"), timeout_s
        self.metadata = self.request("/metadata")
        if self.metadata.get("checkpoint_sha256") != expected_checkpoint:
            raise ValueError("VLA checkpoint identity mismatch")
        if self.metadata.get("contract") not in ("robotwin_aloha_qpos14_v1", "libero_franka_osc7_v1"):
            raise ValueError("Unsupported VLA action/embodiment contract")
        self.query = 0

    def request(self, route, data=None):
        payload = json.dumps(data, allow_nan=False).encode() if data is not None else None
        req = urllib.request.Request(self.url + route, payload, {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read(16 * 1024 * 1024 + 1)
        except urllib.error.HTTPError as exc:
            try:
                kind = json.loads(exc.read(1024)).get("error", "unknown")
            except (ValueError, OSError):
                kind = "unknown"
            raise RuntimeError(f"VLA server HTTP {exc.code}: {str(kind)[:100]}") from None
        if len(raw) > 16 * 1024 * 1024:
            raise ValueError("VLA response exceeds 16 MiB")
        return json.loads(raw)

    def infer(self, env, instruction):
        import numpy as np
        contract = self.metadata["contract"]
        if contract == "robotwin_aloha_qpos14_v1":
            raw = (env.raw_obs if getattr(env, "raw_obs_tick", None) == env.tick
                   else env.env.get_obs())
            cameras = {slot: raw["observation"][camera]["rgb"] for slot, camera in
                       (("0", "head_camera"), ("1", "left_camera"), ("2", "right_camera"))}
            state = np.asarray(raw["joint_action"]["vector"], dtype=float)
            state_dim, action_dim = 14, 14
        else:
            raw = env.raw._get_observations(force_update=True)
            # Official OpenPI LIBERO preprocessing uses a 180-degree rotation of
            # native sensor arrays. Never reuse a differently oriented UI render.
            cameras = {"0": raw["agentview_image"][::-1, ::-1],
                       "1": raw["robot0_eye_in_hand_image"][::-1, ::-1]}
            from robosuite.utils.transform_utils import quat2axisangle
            state = np.r_[raw["robot0_eef_pos"], quat2axisangle(raw["robot0_eef_quat"].copy()),
                          raw["robot0_gripper_qpos"]]
            state_dim, action_dim = 8, 7
        images = {}
        for slot, value in cameras.items():
            image = np.ascontiguousarray(value)
            if image.dtype != np.uint8 or image.ndim != 3 or image.shape[-1] != 3:
                raise ValueError("VLA requires uint8 RGB cameras")
            images[slot] = {"shape": list(image.shape), "data": base64.b64encode(image.tobytes()).decode()}
        if state.shape != (state_dim,) or not np.isfinite(state).all():
            raise ValueError("VLA state does not match checkpoint contract")
        response = self.request("/infer", {"images": images, "state": state.tolist(),
                                          "instruction": instruction, "query": self.query,
                                          "case_id": str(getattr(env, "task", env.name)), "seed": env.seed})
        self.query += 1
        self.last_diagnostics = response.get("diagnostics", {})
        actions = np.asarray(response["actions"], dtype=float)
        if actions.ndim != 2 or actions.shape[1] != action_dim or not 1 <= len(actions) <= 50:
            raise ValueError("Invalid policy action chunk")
        if not np.isfinite(actions).all() or np.any(np.abs(actions) > (2 * np.pi if action_dim == 14 else 1.0001)):
            raise ValueError("Nonfinite or out-of-envelope policy action")
        return actions


def register_policy(env, registry, endpoint):
    expected = {"robotwin_aloha_qpos14_v1": "robotwin", "libero_franka_osc7_v1": "libero"}
    contract = endpoint.metadata["contract"]
    if env.name != expected.get(contract):
        raise ValueError("VLA checkpoint does not match this environment")

    def run(args, ctx):
        import numpy as np
        if env.name == "libero" and env.done:
            return ToolResult("failed", error_code="environment_terminated")
        executed = clipped = 0
        for chunk in range(args["chunks"]):
            started = time.monotonic()
            actions = endpoint.infer(env, args["instruction"])
            ctx.trace.emit("vla_prediction", model=endpoint.metadata, chunk=chunk,
                           latency_s=time.monotonic() - started, predicted_actions=len(actions),
                           diagnostics=getattr(endpoint, "last_diagnostics", {}),
                           executed_horizon=min(10, len(actions)))
            for action in actions[:10]:
                action = action.copy()
                if env.name == "robotwin":
                    before = action[[6, 13]].copy()
                    action[[6, 13]] = np.clip(before, 0, 1)
                    changed = bool(np.any(before != action[[6, 13]]))
                    clipped += int(changed)
                    env.env.take_action(action, action_type="qpos")
                    action_format = "absolute_qpos14"
                else:
                    if env.done:
                        return ToolResult("failed", error_code="environment_terminated")
                    previous = float(env.env.sim.data.time)
                    _, _, env.done, _ = env.env.step(action.tolist())
                    if float(env.env.sim.data.time) < previous or not np.isfinite(env.env.sim.data.qpos).all():
                        raise RuntimeError("Invalid physics state after VLA action")
                    changed, action_format = False, "normalized_osc_pose7"
                env.tick += 1
                executed += 1
                yield {"policy_action": action.tolist(), "action_format": action_format,
                       "chunk": chunk, "gripper_clipped": changed}
                if env.name == "libero" and env.done:
                    ctx.trace.emit("environment_terminal", native_done=True,
                                   criterion="LIBERO_BDDLBaseDomain_step_success", control_tick=env.tick)
                    ctx.observe()
                    return ToolResult("succeeded", {"policy_actions":executed,
                        "environment_terminated":True,
                        "meaning":"Native environment ended; evaluator determines task success"})
            ctx.observe()
        return ToolResult("succeeded", {"policy_actions": executed, "gripper_clipped": clipped,
                                        "meaning": "Chunk executed; task completion is not verified"})

    registry.add(Tool("run_vla", f"Execute a bounded π0.5 policy segment with contract {contract}. "
                      "One chunk executes at most 10 native actions, observing between chunks. "
                      "No success oracle; reobserve and decide after the segment. Preserves full policy "
                      "orientation control. Checkpoint is fixed by the operator.",
                      object_schema({"instruction": {"type": "string", "minLength": 1, "maxLength": 500},
                                     "chunks": {"type": "integer", "enum": [1, 2, 4, 8]}}), run,
                      timeout_s=8 * endpoint.timeout + 120, max_ticks=81))


def configured_policy(env, registry):
    """Use --tools-factory embodied_harness.vla:configured_policy with operator env vars."""
    import os
    endpoint = PolicyEndpoint(os.environ["VLA_ENDPOINT"], os.environ["VLA_CHECKPOINT_SHA256"])
    register_policy(env, registry, endpoint)
