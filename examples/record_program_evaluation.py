"""Verify the development gate against traces before recording or activating a revision."""

import argparse
import hashlib
import json
from pathlib import Path

from embodied_harness.rsi.candidates import CandidateArchive
from embodied_harness.rsi.evolution import EvolutionStore
from embodied_harness.rsi.program_evaluation import evaluate_validation


def record(proposal, campaign, activate=False):
    proposal, campaign = Path(proposal), Path(campaign)
    raw = (proposal / "candidate.json").read_bytes()
    candidate = json.loads(raw)
    protocol = json.loads((campaign / "protocol.json").read_text())
    if hashlib.sha256(raw).hexdigest() != protocol["candidate_sha256"]:
        raise ValueError("Candidate artifact changed")
    gate = json.loads((campaign / "validation-gate.json").read_text())
    rows = json.loads((campaign / "results.json").read_text())["rows"]
    development = []
    for row in rows:
        if row["split"] == "validation":
            row = dict(row)
            row["trace"] = str(campaign / (row["case_id"] + "--" + row["arm"]))
            development.append(row)
    recomputed = evaluate_validation(development, protocol, candidate)
    if recomputed != gate:
        raise ValueError("Stored development decision does not match the actual traces")
    archive = CandidateArchive(EvolutionStore(proposal / "evolution"))
    event = archive.record_evaluation(candidate["candidate_id"], gate)
    if activate and event["payload"]["accepted"]:
        archive.activate(event["event_id"])
    return {
        **event["payload"],
        "active_development_revision": archive.active_revision(),
        "next_action": "evaluate_original_scope_for_mastery"
        if event["payload"]["accepted"]
        else "propose_successor_from_development_only",
        "heldout_used_for_selection": False,
        "statistical_mastery_established": False,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--proposal", required=True)
    p.add_argument("--campaign", required=True)
    p.add_argument("--activate", action="store_true")
    a = p.parse_args()
    print(json.dumps(record(a.proposal, a.campaign, a.activate)))
