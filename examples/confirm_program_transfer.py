"""Combine development-only coverage without reading held-out outcomes into selection.

The first candidate and gate remain immutable. This supplements missing fresh
instances of its supported task; it neither rewrites the tool nor relaxes checks.
"""

import argparse
import hashlib
import json
from pathlib import Path

from embodied_harness.rsi.program_evaluation import evaluate_validation


def combine(campaigns, candidate, candidate_sha256):
    rows, cases, reference = [], [], None
    for campaign in map(Path, campaigns):
        protocol = json.loads((campaign / "protocol.json").read_text())
        if protocol["candidate_sha256"] != candidate_sha256:
            raise ValueError("Candidate artifact does not match frozen protocol")
        result = json.loads((campaign / "results.json").read_text())
        if not result["completed"]:
            raise ValueError("Finish each declared campaign before combining evidence")
        if reference is None:
            reference = protocol.copy()
        for key in (
            "candidate_sha256",
            "checkpoint_sha256",
            "model",
            "max_decisions",
            "max_control_ticks",
            "planner_settings",
        ):
            if protocol[key] != reference[key]:
                raise ValueError("Cannot combine different candidates or evaluation settings")
        # No held-out summary, score, image or plan is passed to the gate.
        rows += [r for r in result["rows"] if r["split"] == "validation"]
        cases += [c for c in protocol["cases"] if c["split"] == "validation"]
    if len({c["id"] for c in cases}) != len(cases):
        raise ValueError("Do not double-count an original validation instance")
    reference["cases"] = cases
    report = evaluate_validation(rows, reference, candidate)
    report["coverage_supplement"] = {
        "candidate_changed": False,
        "gate_relaxed": False,
        "original_validation_gate_preserved": True,
        "meaning": "Additional original-task resets, not harder tasks or extra independent task families",
    }
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--campaign", action="append", required=True)
    p.add_argument("--candidate", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    content = Path(a.candidate).read_bytes()
    report = combine(a.campaign, json.loads(content), hashlib.sha256(content).hexdigest())
    with Path(a.output).open("x") as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps(report))
