"""Frozen GPT baseline versus a model-authored memory/skill/tool candidate.

Both arms get identical task resets, GPT settings and total motion/decision
budgets. Candidate code can only access the bounded primitive API. Native goal
checks remain in the unchanged external evaluator.
"""

import argparse
import hashlib
import json
from pathlib import Path

from embodied_harness.broker import DirectoryPlanner
from embodied_harness.runner import run_episode
from embodied_harness.trace import Trace
from embodied_harness.vla import PolicyEndpoint, register_policy
from embodied_harness.rsi.programs import install_program
from embodied_harness.rsi.program_evaluation import evaluate_validation
from run_libero_baseline import RecordedLibero


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", required=True)
    p.add_argument("--candidate", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--broker", required=True)
    p.add_argument("--endpoint", default="http://127.0.0.1:8907")
    p.add_argument(
        "--validation-only",
        action="store_true",
        help="Collect additional development evidence without opening a held-out split",
    )
    a = p.parse_args()
    protocol = json.loads(Path(a.manifest).read_text())
    content = Path(a.candidate).read_bytes()
    if hashlib.sha256(content).hexdigest() != protocol["candidate_sha256"]:
        raise ValueError("Candidate does not match the frozen validation protocol")
    candidate = json.loads(content)
    root = Path(a.out)
    root.mkdir(parents=True, exist_ok=False)
    (root / "protocol.json").write_text(json.dumps(protocol, indent=2))
    rows = []
    splits = [case["split"] for case in protocol["cases"]]
    expected_splits = {"validation"} if a.validation_only else {"validation", "heldout"}
    if set(splits) != expected_splits or splits != sorted(splits, reverse=True):
        raise ValueError("Run all validation cases before sealed held-out cases")
    gate_sealed = False
    for case in protocol["cases"]:
        if case["split"] == "heldout" and not gate_sealed:
            report = evaluate_validation(rows, protocol, candidate)
            # Seal selection before obtaining any held-out results, even when rejected.
            with (root / "validation-gate.json").open("x") as stream:
                json.dump(report, stream, indent=2)
            gate_sealed = True
            print(json.dumps({"validation_gate_sealed": report}), flush=True)
        for arm in ("baseline", "candidate"):
            output = root / (case["id"] + "--" + arm)
            env = RecordedLibero(output / "camera", **case["config"])
            endpoint = PolicyEndpoint(a.endpoint, protocol["checkpoint_sha256"], timeout_s=120)
            trace = Trace(output)
            context = (
                {
                    "memory": candidate["memory"],
                    "skills": [candidate["skill"]],
                    "candidate_id": candidate["candidate_id"],
                    "status": "development_candidate_not_promoted",
                }
                if arm == "candidate"
                else {}
            )
            planner = DirectoryPlanner(a.broker, protocol["model"], timeout_s=300, context=context)

            def tools_factory(e, r):
                register_policy(e, r, endpoint)
                if arm == "candidate":
                    install_program(r, candidate["program"], trace=trace)

            trace.emit(
                "candidate_identity",
                arm=arm,
                split=case["split"],
                case_id=case["id"],
                candidate_id=candidate["candidate_id"] if arm == "candidate" else "baseline",
                candidate_sha256=protocol["candidate_sha256"],
                model=endpoint.metadata,
            )
            summary = run_episode(
                env,
                planner,
                trace,
                case["instruction"],
                seed=case["seed"],
                max_decisions=protocol["max_decisions"],
                max_control_ticks=protocol["max_control_ticks"],
                tools_factory=tools_factory,
                stop_on_native_success=True,
            )
            row = {
                "case_id": case["id"],
                "task_id": case["task_id"],
                "split": case["split"],
                "arm": arm,
                "initial_state_sha256": getattr(env, "initial_state_sha256", None),
                "summary": summary,
                "trace": str(output),
            }
            rows.append(row)
            (root / "results.json").write_text(
                json.dumps({"completed": False, "rows": rows}, indent=2)
            )
            print(
                json.dumps(
                    {k: row[k] for k in ("case_id", "arm", "split")}
                    | {
                        "success": summary["success"],
                        "status": summary["status"],
                        "api_calls": summary["api_calls"],
                    }
                ),
                flush=True,
            )
    if not gate_sealed:
        with (root / "validation-gate.json").open("x") as stream:
            json.dump(evaluate_validation(rows, protocol, candidate), stream, indent=2)
    (root / "results.json").write_text(json.dumps({"completed": True, "rows": rows}, indent=2))


if __name__ == "__main__":
    main()
