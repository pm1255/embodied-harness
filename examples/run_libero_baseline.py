"""Paired checkpoint-only / GPT + checkpoint baseline on original LIBERO.

The robot worker holds no GPT credential. Its DirectoryPlanner exchanges RGB and
proprioception through an operator-run broker. Official goal checks never enter
that channel. This is an integration baseline, not RPent result reproduction.
"""

import argparse
import hashlib
import json
from pathlib import Path

from embodied_harness.adapters.robosuite import LiberoEnvironment
from embodied_harness.broker import DirectoryPlanner
from embodied_harness.runner import run_episode
from embodied_harness.trace import Trace
from embodied_harness.vla import PolicyEndpoint, register_policy


class CheckpointPlanner:
    model = "pi05_checkpoint_only"
    calls = input_tokens = output_tokens = 0

    def decide(self, task, observation, registry, history, trace):
        return {
            "kind": "plan",
            "plan": {
                "steps": [
                    {
                        "id": "policy-segment",
                        "tool": "run_vla",
                        "arguments": {"instruction": task, "chunks": 8},
                        "require_fact": None,
                    }
                ]
            },
        }


class RecordedLibero(LiberoEnvironment):
    def reset(self, seed):
        import numpy as np

        observation = super().reset(seed)
        self.initial_state_sha256 = hashlib.sha256(
            np.asarray(self.env.sim.get_state().flatten(), dtype="<f8").tobytes()
        ).hexdigest()
        return observation


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--broker", required=True)
    p.add_argument("--endpoint", default="http://127.0.0.1:8907")
    p.add_argument("--checkpoint-sha256", required=True)
    a = p.parse_args()
    manifest = json.loads(Path(a.manifest).read_text())
    root = Path(a.out)
    root.mkdir(parents=True, exist_ok=True)
    if (root / "protocol.json").exists():
        raise ValueError("A campaign directory is immutable; use a new run directory")
    (root / "protocol.json").write_text(json.dumps(manifest, indent=2))
    rows = []
    for case in manifest["cases"]:
        for arm in manifest["arms"]:
            output = root / f"{case['id']}--{arm}"
            env = RecordedLibero(output / "camera", **case["config"])
            endpoint = PolicyEndpoint(a.endpoint, a.checkpoint_sha256, timeout_s=120)
            planner = (
                CheckpointPlanner()
                if arm == "checkpoint_only"
                else DirectoryPlanner(a.broker, manifest["model"], timeout_s=300)
            )
            trace = Trace(output)
            trace.emit(
                "baseline_identity", arm=arm, case_id=case["id"], checkpoint=endpoint.metadata
            )
            result = run_episode(
                env,
                planner,
                trace,
                case["instruction"],
                seed=case["seed"],
                max_decisions=manifest["max_decisions"],
                max_control_ticks=manifest["max_control_ticks"],
                tools_factory=lambda e, r: register_policy(e, r, endpoint),
                stop_on_native_success=True,
            )
            rows.append(
                {
                    "case_id": case["id"],
                    "arm": arm,
                    "initial_state_sha256": getattr(env, "initial_state_sha256", None),
                    "summary": result,
                    "trace": str(output),
                }
            )
            (root / "results.json").write_text(
                json.dumps({"completed": False, "rows": rows}, indent=2)
            )
            print(
                json.dumps(
                    {
                        "case_id": case["id"],
                        "arm": arm,
                        "success": result["success"],
                        "status": result["status"],
                        "api_calls": result["api_calls"],
                    }
                ),
                flush=True,
            )
    (root / "results.json").write_text(json.dumps({"completed": True, "rows": rows}, indent=2))


if __name__ == "__main__":
    main()
