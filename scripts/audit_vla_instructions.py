"""Describe instruction preservation in complete runs; never select a revision."""

import argparse
import json
from pathlib import Path


def audit(campaigns):
    rows = []
    for name, root in campaigns:
        root = Path(root)
        protocol = json.loads((root / "protocol.json").read_text())
        goals = {case["id"]: case["instruction"] for case in protocol["cases"]}
        result = json.loads((root / "results.json").read_text())
        if not result["completed"]:
            raise ValueError("Descriptive audit requires a complete campaign")
        for arm in protocol["arms"]:
            total = canonical = program = 0
            for row in result["rows"]:
                if row["arm"] != arm:
                    continue
                path = root / (row["case_id"] + "--" + arm) / "events.jsonl"
                for line in path.read_text().splitlines():
                    event = json.loads(line)
                    payload, arguments = event["payload"], None
                    if event["kind"] == "tool_start" and payload["step"]["tool"] == "run_vla":
                        arguments = payload["step"]["arguments"]
                    if event["kind"] == "program_step" and payload["primitive"] == "run_vla":
                        arguments = payload["arguments"]
                        program += 1
                    if arguments is not None:
                        total += 1
                        canonical += (
                            arguments["instruction"].strip() == goals[row["case_id"]].strip()
                        )
            rows.append(
                {
                    "campaign": name,
                    "arm": arm,
                    "vla_primitive_invocations": total,
                    "exact_original_instruction": canonical,
                    "inside_generated_program": program,
                }
            )
    return {
        "kind": "posthoc_descriptive_audit",
        "fed_to_proposing_model": False,
        "counts_are_gpt_calls": False,
        "meaning": "Instruction equality strips surrounding whitespace only. Each actual "
        "run_vla entry is counted, including repeated inner calls. This does not isolate "
        "the effect of wording, call duration, memory or skills.",
        "rows": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", action="append", required=True, help="NAME=PATH")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    campaigns = [value.split("=", 1) for value in args.campaign]
    if any(len(value) != 2 for value in campaigns):
        parser.error("Each campaign must be NAME=PATH")
    Path(args.out).write_text(json.dumps(audit(campaigns), indent=2) + "\n")
