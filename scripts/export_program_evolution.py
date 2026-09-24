"""Export an actual model-authored revision and its paired execution evidence."""

import argparse
import difflib
import gzip
import json
from pathlib import Path

from embodied_harness.rsi.evolution import EvolutionStore
from export_rsi import video, wilson
from package_baseline_evidence import public_events


def export(proposal, campaign, destination):
    proposal, campaign, destination = map(Path, (proposal, campaign, destination))
    destination.mkdir(parents=True, exist_ok=True)
    candidate = json.loads((proposal / "candidate.json").read_text())
    result = json.loads((campaign / "results.json").read_text())
    gate = json.loads((campaign / "validation-gate.json").read_text())
    protocol = json.loads((campaign / "protocol.json").read_text())
    rows = []
    for original in result["rows"]:
        row = {k: v for k, v in original.items() if k != "trace"}
        identity = row["case_id"] + "--" + row["arm"]
        root = campaign / identity
        events = [json.loads(line) for line in (root / "events.jsonl").read_text().splitlines()]
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
    changes = {}
    for name in ("MEMORY.md", "PROCEDURE.md", "program.py"):
        content = (proposal / name).read_text()
        (destination / name).write_text(content)
        changes[name] = {
            "source": content,
            "diff": "".join(
                difflib.unified_diff(
                    [],
                    content.splitlines(True),
                    fromfile="baseline/" + name,
                    tofile="candidate/" + name,
                )
            ),
        }
    data = {
        "candidate": candidate,
        "gate": gate,
        "protocol": protocol,
        "rows": rows,
        "statistics": statistics,
        "changes": changes,
        "ledger": EvolutionStore(proposal / "evolution").verify(),
        "api": json.loads((proposal / "api-metadata.json").read_text()),
        "completed": result["completed"],
        "difficulty_changed": False,
        "note": "One model-authored memory/skill/tool bundle; no component ablation, no new task or weight training. Small fresh-reset pilot, not a generalization or mastery claim.",
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
    a = p.parse_args()
    export(a.proposal, a.campaign, a.destination)
