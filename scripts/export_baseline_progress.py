"""Publish measured paired baseline progress, changes and empty evolution axes honestly."""

import argparse
import copy
import gzip
import json
from pathlib import Path
import subprocess

from export_rsi import video


def export(source, destination):
    source, destination = Path(source), Path(destination)
    destination.mkdir(parents=True, exist_ok=True)

    def read(name, default):
        path = source / name
        return json.loads(path.read_text()) if path.exists() else default

    results = read("results.json", {"completed": False, "rows": []})
    rows = copy.deepcopy(results["rows"])
    for row in rows:
        campaign = Path(row.pop("trace", "runs/preflight-v1/episode")).parent.name
        identity = row["case_id"] + "--" + row["arm"]
        root = source / "runs" / campaign / identity
        if (root / "events.jsonl").exists():
            events = [json.loads(line) for line in (root / "events.jsonl").read_text().splitlines()]
            media = destination / "media" / identity
            media.parent.mkdir(exist_ok=True)
            row["timeline"] = video(events, root, media.with_suffix(".mp4"))
            row["video"] = "media/" + identity + ".mp4"
            public = copy.deepcopy(events)
            for event in public:
                if event["kind"] == "model_response":
                    payload = event["payload"]
                    payload.pop("response_id", None)
                    (payload.get("usage") or {}).pop("attribution", None)
                    for call in payload.get("calls", []):
                        call.pop("id", None)
                        call.pop("call_id", None)
            with gzip.open(media.with_suffix(".jsonl.gz"), "wt", encoding="utf-8") as stream:
                for event in public:
                    stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            row["public_trace"] = "media/" + identity + ".jsonl.gz"
    data = {
        "status": read("status.json", {"stage": "preparing"}),
        "rows": rows,
        "completed": results["completed"],
        "setup_attempts": read("setup-attempts.json", []),
        "job": read("job.json", {}),
        "protocol": read("protocol.json", {}),
        "evolution_rounds_completed": 0,
        "new_task_difficulty": "not_measured",
        "change_actor": "engineering_agent",
        "diff": (source / "engineering.diff").read_text()
        if (source / "engineering.diff").exists()
        else subprocess.check_output(
            ["git", "diff", "--", "src/embodied_harness/runner.py", "src/embodied_harness/vla.py"],
            text=True,
        ),
        "note": "Original-task preflight. No model-generated harness improvement measured yet.",
    }
    (destination / "data.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    template = Path(__file__).resolve().parents[1] / "src/embodied_harness/web/baseline.html"
    (destination / "index.html").write_text(
        template.read_text().replace(
            "__DATA__", json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source")
    p.add_argument("destination")
    a = p.parse_args()
    export(a.source, a.destination)
