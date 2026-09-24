"""Publish GPU interface checks separately from GPT policy results."""

from pathlib import Path
import argparse
import json
import shutil
from embodied_harness.trace import export_viewer
from export_benchmark import gif

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("source")
p.add_argument("destination")
args = p.parse_args()
root, dest = Path(args.source), Path(args.destination)
dest.mkdir(parents=True, exist_ok=True)
records = []
cards = []
for source in sorted(root.glob("*/report.json")):
    report = json.loads(source.read_text())
    for record in report["results"]:
        key = source.parent.name + "--" + record["id"]
        trace = source.parent / record["id"] / "trace"
        events = [json.loads(line) for line in (trace / "events.jsonl").read_text().splitlines()]
        errors = [e["payload"]["message"] for e in events if e["kind"] == "error"]
        # Remove operator-specific filesystem prefixes from public setup errors.
        record["setup_errors"] = [
            message.replace(
                "/user/panmiao/workspace/robodojo-data-windtunnel/runtime/robocasa365-source",
                "<RoboCasa source>",
            ).replace(
                "/user/panmiao/robot_vlm_project/opensource/benchmark-20260924/robocasa-with-assets",
                "<isolated RoboCasa source>",
            )
            for message in errors
        ]
        record["attempt"] = source.parent.name
        records.append(record)
        if record["environment"] != "robotwin":
            continue
        out = dest / key
        out.mkdir(exist_ok=True)
        for name in ["events.jsonl", "summary.json"]:
            shutil.copy2(trace / name, out / name)
        shutil.copytree(trace / "frames", out / "frames", dirs_exist_ok=True)
        export_viewer(out)
        gif(events, out, out / "replay.gif")
        cards.append(
            f"### {record['id']}\n\nInterface passed: {record['integration_passed']}. {record['summary']['control_ticks']} native EE action call; the native action performs multiple internal physics steps. **No GPT task-solving claim.**\n\n![Recorded interface motion]({key}/replay.gif)\n\n[Interactive trace]({key}/index.html)\n"
        )
(dest / "all-attempts.json").write_text(json.dumps(records, indent=2) + "\n")
(dest / "README.md").write_text(
    "# GPU interface checks\n\nActual one-RTX-4090 runs. Three RoboTwin cases passed. RoboCasa failed in three asset-setup attempts (nine cases); failures are retained in [all attempts](all-attempts.json). A 2cm TCP command is checked at a 12mm tolerance; this is not precision grasping or task completion.\n\n"
    + "\n".join(cards)
)
