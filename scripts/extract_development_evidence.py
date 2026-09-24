"""Create a complete development-only feedback bundle, never including held-out rows."""

import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile


def extract(campaign, output):
    campaign = Path(campaign)
    protocol = json.loads((campaign / "protocol.json").read_text())
    result = json.loads((campaign / "results.json").read_text())
    cases = [c for c in protocol["cases"] if c["split"] == "validation"]
    rows = [r for r in result["rows"] if r["split"] == "validation"]
    expected = {(c["id"], arm) for c in cases for arm in protocol["arms"]}
    actual = [(r["case_id"], r["arm"]) for r in rows]
    if not expected or set(actual) != expected or len(actual) != len(expected):
        raise ValueError("Complete unique paired development evidence is required")
    if not (campaign / "validation-gate.json").exists():
        raise ValueError("Seal the development gate before requesting another proposal")
    subset = dict(
        protocol, cases=cases, purpose="Development-only feedback; held-out outcomes excluded"
    )
    with tarfile.open(output, "x:gz") as archive:

        def add(name, content):
            info = tarfile.TarInfo("development-only/" + name)
            info.size = len(content)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(content))

        add("protocol.json", json.dumps(subset, indent=2).encode())
        add("results.json", json.dumps({"completed": True, "rows": rows}, indent=2).encode())
        add("validation-gate.json", (campaign / "validation-gate.json").read_bytes())
        add(
            "subset-provenance.json",
            json.dumps(
                {
                    "source_protocol_sha256": hashlib.sha256(
                        (campaign / "protocol.json").read_bytes()
                    ).hexdigest(),
                    "heldout_included": False,
                    "development_instances": len(cases),
                    "episodes": len(rows),
                },
                indent=2,
            ).encode(),
        )
        for row in rows:
            identity = row["case_id"] + "--" + row["arm"]
            root = (campaign / identity).resolve()
            root.relative_to(campaign.resolve())
            events = [json.loads(line) for line in (root / "events.jsonl").read_text().splitlines()]
            summary = json.loads((root / "summary.json").read_text())
            if summary != row["summary"]:
                raise ValueError("Development summary does not match its recorded episode")
            for name in ("events.jsonl", "summary.json"):
                add(identity + "/" + name, (root / name).read_bytes())
            observations = [e for e in events if e["kind"] == "observation"]
            frames = {}
            if observations:
                for observation in (observations[0], observations[-1]):
                    for frame in observation["payload"]["frames"][:2]:
                        path = (root / frame["image_path"]).resolve()
                        relative = path.relative_to(root)
                        content = path.read_bytes()
                        if hashlib.sha256(content).hexdigest() != frame["sha256"]:
                            raise ValueError("Changed sensor frame")
                        frames[str(relative)] = content
            for name, content in frames.items():
                add(identity + "/" + name, content)
    return {"development_instances": len(cases), "episodes": len(rows), "heldout_included": False}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--campaign", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    print(json.dumps(extract(a.campaign, a.output)))
