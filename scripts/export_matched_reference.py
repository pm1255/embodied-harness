"""Join complete GPT/candidate pairs with their independently run policy reference."""

import argparse
import copy
import gzip
import hashlib
import json
import os
from pathlib import Path

from export_rsi import video
from package_baseline_evidence import public_events, usage_missing_calls


def verify_matched_cases(scope_protocol, policy_protocol, scope_rows, policy_rows):
    for field in ("max_decisions", "max_control_ticks", "success_criterion", "checkpoint_sha256"):
        if scope_protocol[field] != policy_protocol[field]:
            raise ValueError("Reference changed the execution contract: " + field)
    cases = {c["id"]: c for c in scope_protocol["cases"]}
    reference = {c["id"]: c for c in policy_protocol["cases"]}
    if not cases or cases != reference or len(cases) != len(scope_protocol["cases"]):
        raise ValueError("Reference must use every identical task, instruction and reset")
    if len(reference) != len(policy_protocol["cases"]):
        raise ValueError("Duplicate reference case")
    expected = {
        (case, arm) for case in cases for arm in ("baseline", "candidate", "checkpoint_only")
    }
    rows = scope_rows + policy_rows
    keys = [(r["case_id"], r["arm"]) for r in rows]
    if set(keys) != expected or len(keys) != len(expected):
        raise ValueError("Complete unique triplets required; do not omit failed episodes")
    for case in cases:
        fingerprints = {r["initial_state_sha256"] for r in rows if r["case_id"] == case}
        if len(fingerprints) != 1 or not next(iter(fingerprints)):
            raise ValueError("Initial state differs between compared arms")
    return cases


def export(scope, scope_export, policy, destination, broker_audit=None):
    scope, scope_export, policy, destination = map(Path, (scope, scope_export, policy, destination))
    sr = json.loads((scope / "results.json").read_text())
    pr = json.loads((policy / "results.json").read_text())
    if not sr["completed"] or not pr["completed"]:
        raise ValueError("Finish every arm before publishing a matched reference")
    sp = json.loads((scope / "protocol.json").read_text())
    pp = json.loads((policy / "protocol.json").read_text())
    cases = verify_matched_cases(sp, pp, sr["rows"], pr["rows"])
    displayed = json.loads((scope_export / "data.json").read_text())
    visible = {(r["case_id"], r["arm"]): r for r in displayed["rows"]}
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "media").mkdir(exist_ok=True)
    rows, checkpoints = [], []
    for source, originals in ((scope, sr["rows"]), (policy, pr["rows"])):
        for original in originals:
            identity = original["case_id"] + "--" + original["arm"]
            root = source / identity
            events = [json.loads(x) for x in (root / "events.jsonl").read_text().splitlines()]
            summary = json.loads((root / "summary.json").read_text())
            ends = [e["payload"] for e in events if e["kind"] == "episode_end"]
            if len(ends) != 1 or ends[0] != summary or summary != original["summary"]:
                raise ValueError("Displayed result differs from original execution")
            if summary["success"] and (
                summary.get("native_terminal_success") is not True
                or not any(e["kind"] == "environment_terminal" for e in events)
            ):
                raise ValueError("Success requires native terminal evidence")
            identities = [
                e for e in events if e["kind"] in ("baseline_identity", "candidate_identity")
            ]
            if len(identities) != 1:
                raise ValueError("Missing execution identity")
            item = identities[0]["payload"]
            metadata = item.get("checkpoint", item.get("model"))
            if metadata["checkpoint_sha256"] != sp["checkpoint_sha256"]:
                raise ValueError("Unexpected checkpoint")
            checkpoints.append(metadata)
            if original["arm"] == "checkpoint_only":
                if summary["api_calls"] != 0 or any(e["kind"] == "model_request" for e in events):
                    raise ValueError("Policy reference must not call the brain model")
                row = {k: copy.deepcopy(v) for k, v in original.items() if k != "trace"}
                row["timeline"] = video(events, root, destination / "media" / (identity + ".mp4"))
                row["video"] = "media/" + identity + ".mp4"
                row["public_trace"] = "media/" + identity + ".jsonl.gz"
                with gzip.open(destination / row["public_trace"], "wt", encoding="utf-8") as stream:
                    for event in public_events(events):
                        stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            else:
                row = copy.deepcopy(visible[(original["case_id"], original["arm"])])
                if (
                    row["summary"] != summary
                    or row["initial_state_sha256"] != original["initial_state_sha256"]
                ):
                    raise ValueError("Paired viewer is not bound to this campaign")
                for field in ("video", "public_trace"):
                    row[field] = os.path.relpath(scope_export / row[field], destination)
            row["split"] = cases[row["case_id"]]["split"]
            row["usage_missing_calls"] = usage_missing_calls(events)
            row["errors"] = [
                {"type": e["payload"]["error_type"],
                 "message": e["payload"]["message"].splitlines()[0][:2000]}
                for e in events if e["kind"] == "error"
            ]
            rows.append(row)
    if any(metadata != checkpoints[0] for metadata in checkpoints):
        raise ValueError("Checkpoint preprocessing, denoising or runtime metadata changed")
    accounting = json.loads(Path(broker_audit).read_text()) if broker_audit else None
    if accounting:
        for filename, field in (("results.json", "campaign_results_sha256"),
                                ("protocol.json", "protocol_sha256")):
            if hashlib.sha256((scope / filename).read_bytes()).hexdigest() != accounting[field]:
                raise ValueError("Cost audit is not bound to the displayed campaign")
        expected = {row["case_id"] + "--" + row["arm"] for row in sr["rows"]}
        if any(row["episode"] not in expected for row in accounting["rows"]):
            raise ValueError("Cost audit contains an unrelated episode")
        for row in rows:
            requests = [entry for entry in accounting["rows"]
                        if entry["episode"] == row["case_id"] + "--" + row["arm"]]
            row["provider_api_attempts"] = len(requests)
            for field in ("input_tokens", "output_tokens", "usage_missing_calls"):
                row["provider_" + field] = sum(entry[field] for entry in requests)
    statistics = []
    for split in ("validation", "heldout", "all"):
        for arm in ("checkpoint_only", "baseline", "candidate"):
            selected = [
                r for r in rows if r["arm"] == arm and (split == "all" or r["split"] == split)
            ]
            statistics.append(
                {
                    "split": split,
                    "arm": arm,
                    "n": len(selected),
                    "successes": sum(r["summary"]["success"] for r in selected),
                    "usage_missing_calls": sum(r["usage_missing_calls"] for r in selected),
                    **({field: sum(row[field] for row in selected)
                        for field in ("provider_api_attempts", "provider_input_tokens",
                                      "provider_output_tokens", "provider_usage_missing_calls")}
                       if accounting else {}),
                    "infrastructure_errors": sum(
                        r["summary"]["status"] == "infrastructure_error" for r in selected
                    ),
                    **{
                        k: sum(r["summary"][k] for r in selected)
                        for k in (
                            "api_calls",
                            "input_tokens",
                            "output_tokens",
                            "control_ticks",
                            "wall_seconds",
                        )
                    },
                }
            )
    data = {
        "cases": list(cases.values()),
        "rows": rows,
        "statistics": statistics,
        "scope_protocol": sp,
        "reference_protocol": pp,
        "checkpoint": checkpoints[0],
        "candidate_id": displayed["candidate"]["candidate_id"],
        "broker_cost_audit": accounting,
        "note": "Supplementary matched execution reference, not a candidate-selection round. All task/state pairs included. No model weights changed; standard LIBERO is in-domain.",
    }
    (destination / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    template = Path(__file__).parents[1] / "src/embodied_harness/web/matched-reference.html"
    (destination / "index.html").write_text(
        template.read_text().replace(
            "__DATA__", json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scope", required=True)
    p.add_argument("--scope-export", required=True)
    p.add_argument("--policy", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--broker-audit")
    a = p.parse_args()
    export(a.scope, a.scope_export, a.policy, a.out, a.broker_audit)
