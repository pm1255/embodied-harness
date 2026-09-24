"""Independent paired gate for a frozen bounded-tool candidate.

Held-out rows cannot affect selection. Four validation families are a small
engineering gate, not statistical evidence of universal improvement or mastery.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .core import promotion_gate
from .frontier import VALID_OUTCOMES


def evaluate_validation(rows, protocol, candidate):
    expected = {c["id"] for c in protocol["cases"] if c["split"] == "validation"}
    selected = [r for r in rows if r["split"] == "validation"]
    pairs = {}
    for row in selected:
        arms = pairs.setdefault(row["case_id"], {})
        if row["arm"] in arms:
            raise ValueError("Duplicate validation outcome")
        arms[row["arm"]] = row
    if set(pairs) != expected or any(
        set(arms) != {"baseline", "candidate"} for arms in pairs.values()
    ):
        raise ValueError("Incomplete paired validation")
    fingerprints = []
    source_hash = hashlib.sha256(candidate["program"]["source"].encode()).hexdigest()
    observed_program_successes = []
    evidence_valid = True
    budgets = True
    settings = True
    errors = []
    base = {}
    new = {}
    for identity, arms in pairs.items():
        fingerprint = arms["baseline"]["initial_state_sha256"]
        if not fingerprint or fingerprint != arms["candidate"]["initial_state_sha256"]:
            evidence_valid = False
        fingerprints.append(fingerprint)
        for arm, row in arms.items():
            root = Path(row["trace"])
            events = [json.loads(line) for line in (root / "events.jsonl").read_text().splitlines()]
            summary = json.loads((root / "summary.json").read_text())
            ends = [e["payload"] for e in events if e["kind"] == "episode_end"]
            evidence_valid &= bool(ends) and ends[-1] == summary == row["summary"]
            starts = [e["payload"] for e in events if e["kind"] == "episode_start"]
            budgets &= (
                len(starts) == 1
                and starts[0]["max_control_ticks"] == protocol["max_control_ticks"]
                and starts[0]["max_decisions"] == protocol["max_decisions"]
            )
            budgets &= (
                summary["control_ticks"] <= protocol["max_control_ticks"]
                and summary["decisions"] <= protocol["max_decisions"]
            )
            requests = [e["payload"] for e in events if e["kind"] == "model_request"]
            settings &= bool(requests) and all(
                e["model"] == protocol["model"]
                and e.get("reasoning_effort") == protocol["planner_settings"]["reasoning_effort"]
                for e in requests
            )
            if summary["status"] not in VALID_OUTCOMES:
                errors.append(identity + "/" + arm)
            if summary["success"]:
                evidence_valid &= summary.get("native_terminal_success") is True
                evidence_valid &= any(e["kind"] == "environment_terminal" for e in events)
            if arm == "candidate":
                registrations = [e["payload"] for e in events if e["kind"] == "program_registered"]
                evidence_valid &= (
                    len(registrations) == 1 and registrations[0]["source_sha256"] == source_hash
                )
                if any(e["kind"] == "program_step" for e in events) and summary["success"]:
                    observed_program_successes.append(identity)
            (base if arm == "baseline" else new)[identity] = {**summary, "split": "validation"}
    evidence_valid &= len(set(fingerprints)) == len(fingerprints)
    small_gate = promotion_gate(base, new)
    report = {
        "candidate_id": candidate["candidate_id"],
        "split": "validation",
        "contract_passed": not errors and bool(settings),
        "transfer_passed": small_gate["accepted"] and len(observed_program_successes) >= 2,
        "retention_passed": not small_gate["regressions"],
        "budget_passed": bool(budgets),
        "independent_evaluator": True,
        "evidence_verified": bool(evidence_valid),
        "small_development_gate": small_gate,
        "program_successful_fresh_instances": observed_program_successes,
        "infrastructure_or_unknown_outcomes": errors,
        "validation_instances": len(pairs),
        "heldout_used_for_selection": False,
        "statistical_mastery_established": False,
    }
    return report
