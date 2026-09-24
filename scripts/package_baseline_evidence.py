"""Package every supplied baseline attempt with all referenced sensor frames.

Provider request identifiers are removed; raw and public event hashes are recorded.
No credentials, broker directories, model weights or training artifacts are scanned.
"""

import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import tarfile


def usage_missing_calls(events):
    """Failed provider responses can omit billed usage; never report it as zero."""
    requests = sum(event["kind"] == "model_request" for event in events)
    reported = sum(
        event["kind"] == "model_response"
        and all(
            type((event["payload"].get("usage") or {}).get(field)) is int
            for field in ("input_tokens", "output_tokens")
        )
        for event in events
    )
    return max(0, requests - reported)


def public_events(events):
    rows = copy.deepcopy(events)
    for event in rows:
        if event["kind"] == "model_response":
            payload = event["payload"]
            payload.pop("response_id", None)
            (payload.get("usage") or {}).pop("attribution", None)
            for call in payload.get("calls", []):
                call.pop("id", None)
                call.pop("call_id", None)
    return rows


def package(campaigns, output):
    manifest = {
        "schema_version": 1,
        "campaigns": [],
        "files": 0,
        "note": "Includes failed and incomplete attempts. Incomplete traces have no fabricated summary.",
    }
    with tarfile.open(output, "w:gz") as archive:

        def add(name, data):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(data))
            manifest["files"] += 1

        for campaign in map(Path, campaigns):
            name = campaign.name
            if any(c["name"] == name for c in manifest["campaigns"]):
                raise ValueError("Campaign names must be unique")
            row = {"name": name, "episodes": []}
            for filename in ("protocol.json", "results.json"):
                path = campaign / filename
                if path.exists():
                    data = json.loads(path.read_text())
                    if filename == "results.json":
                        for result in data["rows"]:
                            if "trace" in result:
                                result["trace"] = Path(result["trace"]).name
                    add(
                        f"{name}/{filename}",
                        json.dumps(data, ensure_ascii=False, indent=2).encode(),
                    )
            for path in sorted(campaign.glob("*/events.jsonl")):
                root = path.parent.resolve()
                raw = path.read_bytes()
                events = [json.loads(line) for line in raw.splitlines()]
                cleaned = public_events(events)
                body = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in cleaned).encode()
                prefix = f"{name}/{root.name}"
                add(prefix + "/events.jsonl", body)
                summary = root / "summary.json"
                if summary.exists():
                    add(prefix + "/summary.json", summary.read_bytes())
                frames = {}
                for event in cleaned:
                    if event["kind"] == "observation":
                        for frame in event["payload"]["frames"]:
                            frame_path = (root / frame["image_path"]).resolve()
                            relative = frame_path.relative_to(root)
                            frame_data = frame_path.read_bytes()
                            if hashlib.sha256(frame_data).hexdigest() != frame["sha256"]:
                                raise ValueError("Frame hash mismatch")
                            frames[str(relative)] = frame_data
                for relative, data in frames.items():
                    add(prefix + "/" + relative, data)
                row["episodes"].append(
                    {
                        "id": root.name,
                        "complete": summary.exists(),
                        "frames": len(frames),
                        "events": len(events),
                        "raw_events_sha256": hashlib.sha256(raw).hexdigest(),
                        "public_events_sha256": hashlib.sha256(body).hexdigest(),
                    }
                )
            manifest["campaigns"].append(row)
        add(
            "manifest.json",
            json.dumps(
                dict(manifest, files=manifest["files"] + 1), ensure_ascii=False, indent=2
            ).encode(),
        )
    result = {
        "archive": Path(output).name,
        "bytes": Path(output).stat().st_size,
        "sha256": hashlib.sha256(Path(output).read_bytes()).hexdigest(),
        **manifest,
    }
    Path(str(output) + ".json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--campaign", action="append", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    result = package(a.campaign, a.output)
    print(json.dumps({k: result[k] for k in ("archive", "bytes", "sha256", "files")}))
