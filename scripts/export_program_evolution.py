"""Export an actual model-authored revision and its paired execution evidence."""

import argparse
import difflib
import gzip
import hashlib
import json
from pathlib import Path

from embodied_harness.rsi.evolution import EvolutionStore
from export_rsi import video, wilson
from package_baseline_evidence import public_events, usage_missing_calls


def export(
    proposal,
    campaign,
    destination,
    rejected=(),
    supplements=(),
    confirmation_gate=None,
    parent_proposal=None,
    prior_exports=(),
    scope_export=None,
    matched_reference=None,
):
    proposal, campaign, destination = map(Path, (proposal, campaign, destination))
    destination.mkdir(parents=True, exist_ok=True)
    candidate = json.loads((proposal / "candidate.json").read_text())
    result = json.loads((campaign / "results.json").read_text())
    gate = json.loads((campaign / "validation-gate.json").read_text())
    initial_gate = gate
    if supplements and not confirmation_gate:
        raise ValueError("Seal the combined development decision before opening held-out replay")
    if confirmation_gate:
        gate = json.loads(Path(confirmation_gate).read_text())
    protocol = json.loads((campaign / "protocol.json").read_text())
    if (
        gate["candidate_id"] != candidate["candidate_id"]
        or protocol["candidate_sha256"]
        != hashlib.sha256((proposal / "candidate.json").read_bytes()).hexdigest()
    ):
        raise ValueError("Viewer evidence must bind the exact candidate artifact")
    source_rows = [(campaign, row) for row in result["rows"]]
    additional_protocols = []
    for supplement in map(Path, supplements):
        extra = json.loads((supplement / "results.json").read_text())
        if not extra["completed"] or any(r["split"] != "validation" for r in extra["rows"]):
            raise ValueError("Supplement must contain only completed development instances")
        source_rows += [(supplement, row) for row in extra["rows"]]
        additional_protocols.append(json.loads((supplement / "protocol.json").read_text()))
    rows = []
    for source, original in source_rows:
        row = {k: v for k, v in original.items() if k != "trace"}
        identity = row["case_id"] + "--" + row["arm"]
        root = source / identity
        events = [json.loads(line) for line in (root / "events.jsonl").read_text().splitlines()]
        row["usage_missing_calls"] = usage_missing_calls(events)
        row["errors"] = [
            {"type": e["payload"]["error_type"],
             "message": e["payload"]["message"].splitlines()[0][:2000]}
            for e in events if e["kind"] == "error"
        ]
        media = destination / "media" / identity
        media.parent.mkdir(exist_ok=True)
        row["timeline"] = video(events, root, media.with_suffix(".mp4"))
        row["video"] = "media/" + identity + ".mp4"
        row["program_invocations"] = sum(
            e["kind"] == "tool_start"
            and e["payload"]["step"]["tool"] == candidate["program"]["name"]
            for e in events
        )
        row["primitive_invocations"] = sum(e["kind"] == "program_step" for e in events)
        with gzip.open(media.with_suffix(".jsonl.gz"), "wt", encoding="utf-8") as stream:
            for event in public_events(events):
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        row["public_trace"] = "media/" + identity + ".jsonl.gz"
        rows.append(row)
    statistics = []
    for split in ("validation", "heldout"):
        for arm in ("baseline", "candidate"):
            selected = [r for r in rows if r["split"] == split and r["arm"] == arm]
            k, n = sum(r["summary"]["success"] for r in selected), len(selected)
            statistics.append(
                {
                    "split": split,
                    "arm": arm,
                    "successes": k,
                    "n": n,
                    "wilson95": wilson(k, n),
                    "usage_missing_calls": sum(r["usage_missing_calls"] for r in selected),
                    "infrastructure_errors": sum(
                        r["summary"]["status"] == "infrastructure_error" for r in selected
                    ),
                    **{
                        field: sum(r["summary"][field] for r in selected)
                        for field in (
                            "api_calls",
                            "control_ticks",
                            "wall_seconds",
                            "input_tokens",
                            "output_tokens",
                        )
                    },
                }
            )
    ledger = EvolutionStore(proposal / "evolution").verify()
    proposal_event = next(e for e in ledger if e["event_id"] == candidate["candidate_id"])
    parent_id = proposal_event["payload"]["parent"]
    parent_event = next((e for e in ledger if e["event_id"] == parent_id), None)
    parent_candidate = (
        json.loads((Path(parent_proposal) / "candidate.json").read_text())
        if parent_proposal
        else None
    )
    if parent_event and parent_candidate is None:
        raise ValueError("Supply the parent proposal to compare all tool metadata accurately")
    if parent_candidate and parent_candidate["candidate_id"] != parent_id:
        raise ValueError("Source comparison must use the actual parent candidate")
    names = {
        "MEMORY.md": "memory/MEMORY.md",
        "PROCEDURE.md": "skills/PROCEDURE.md",
        "program.py": "tools/program.py",
        "tool-binding.json": "harness/tool-binding.json",
    }

    def previous(name):
        if parent_event is None:
            return ""
        ref = parent_event["artifacts"][names[name]]
        return (proposal / "evolution/objects" / ref["sha256"]).read_text()

    changes = {}
    for name in ("MEMORY.md", "PROCEDURE.md", "program.py"):
        content = (proposal / name).read_text()
        (destination / name).write_text(content)
        changes[name] = {
            "source": content,
            "diff": "".join(
                difflib.unified_diff(
                    previous(name).splitlines(True),
                    content.splitlines(True),
                    fromfile=parent_id + "/" + name,
                    tofile="candidate/" + name,
                )
            ),
        }
    binding_ref = proposal_event["artifacts"]["harness/tool-binding.json"]
    binding = (proposal / "evolution/objects" / binding_ref["sha256"]).read_text()
    (destination / "tool-binding.json").write_text(binding)
    changes["tool-binding.json (operator registration)"] = {
        "source": binding,
        "diff": "".join(
            difflib.unified_diff(
                previous("tool-binding.json").splitlines(True),
                binding.splitlines(True),
                fromfile=parent_id + "/tool-binding.json",
                tofile="candidate/tool-binding.json",
            )
        ),
    }
    description = candidate["program"]["description"]
    old_description = parent_candidate["program"]["description"] if parent_candidate else ""
    (destination / "tool-description.md").write_text(description)
    changes["tool-description.md"] = {
        "source": description,
        "diff": "".join(
            difflib.unified_diff(
                old_description.splitlines(True),
                description.splitlines(True),
                fromfile=parent_id + "/tool-description.md",
                tofile="candidate/tool-description.md",
            )
        ),
    }
    data = {
        "candidate": candidate,
        "gate": gate,
        "initial_gate": initial_gate,
        "additional_protocols": additional_protocols,
        "protocol": protocol,
        "rows": rows,
        "statistics": statistics,
        "changes": changes,
        "ledger": ledger,
        "parent_revision": parent_id,
        "version_history": [
            {
                "candidate_id": e["payload"]["candidate"],
                "accepted": e["payload"]["accepted"],
                "report": json.loads(
                    (
                        proposal / "evolution/objects" / e["artifacts"]["report"]["sha256"]
                    ).read_text()
                ),
            }
            for e in ledger
            if e["kind"] == "candidate_evaluated"
        ],
        "api": json.loads((proposal / "api-metadata.json").read_text()),
        "completed": result["completed"],
        "difficulty_changed": False,
        "reader_summary": json.loads((proposal / "reader-summary.json").read_text())
        if (proposal / "reader-summary.json").exists()
        else None,
        "note": "One model-authored memory/skill/tool bundle; no component ablation, no new task or weight training. Small fresh-reset pilot, not a generalization or mastery claim.",
        "rejected_proposals": [
            {
                "proposal": json.loads((Path(path) / "model-output.json").read_text()),
                "rejection": json.loads((Path(path) / "rejected.json").read_text()),
                "api": json.loads((Path(path) / "api-metadata.json").read_text()),
            }
            for path in rejected
        ],
    }
    data["round_results"] = []
    known_candidates = {e["event_id"] for e in ledger if e["kind"] == "change_proposed"}
    for path in prior_exports:
        prior = json.loads((Path(path) / "data.json").read_text())
        if prior["candidate"]["candidate_id"] not in known_candidates or not prior["completed"]:
            raise ValueError("Round overview must use completed ancestors of this revision")
        data["round_results"].append(
            {"candidate_id": prior["candidate"]["candidate_id"], "statistics": prior["statistics"]}
        )
    data["round_results"].append(
        {"candidate_id": candidate["candidate_id"], "statistics": statistics}
    )
    if scope_export:
        scope = json.loads((Path(scope_export) / "data.json").read_text())
        if (
            not scope["completed"]
            or scope["candidate"]["candidate_id"] != candidate["candidate_id"]
        ):
            raise ValueError("Scope confirmation must execute the same frozen candidate completely")
        data["scope_confirmation"] = {
            "protocol": scope["protocol"],
            "gate": scope["gate"],
            "statistics": scope["statistics"],
            "details": "confirmation/",
        }
    if matched_reference:
        reference = json.loads((Path(matched_reference) / "data.json").read_text())
        if reference["candidate_id"] != candidate["candidate_id"] or not reference["broker_cost_audit"]:
            raise ValueError("Reference must bind this candidate and reconcile broker costs")
        data["matched_reference"] = {
            "statistics": reference["statistics"], "details": "matched-reference/",
            "broker_cost_audit": {key: value for key, value in reference["broker_cost_audit"].items()
                                  if key != "rows"},
        }
    (destination / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    template = (
        Path(__file__).resolve().parents[1] / "src/embodied_harness/web/program-evolution.html"
    )
    (destination / "index.html").write_text(
        template.read_text().replace(
            "__DATA__", json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("proposal")
    p.add_argument("campaign")
    p.add_argument("destination")
    p.add_argument("--rejected", action="append", default=[])
    p.add_argument("--supplement", action="append", default=[])
    p.add_argument("--confirmation-gate")
    p.add_argument("--parent-proposal")
    p.add_argument("--prior-export", action="append", default=[])
    p.add_argument("--scope-export")
    p.add_argument("--matched-reference")
    a = p.parse_args()
    export(
        a.proposal,
        a.campaign,
        a.destination,
        a.rejected,
        a.supplement,
        a.confirmation_gate,
        a.parent_proposal,
        a.prior_export,
        a.scope_export,
        a.matched_reference,
    )
