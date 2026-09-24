"""Append-only events plus a self-contained, network-free trace viewer."""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from importlib.resources import files
from pathlib import Path


class Trace:
    def __init__(self, directory: str | Path):
        self.root = Path(directory).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        # Never silently merge unrelated runs.
        self.file = (self.root / "events.jsonl").open("x", encoding="utf-8")
        self.started = time.monotonic()
        self.count = 0
        self.events: list[dict] = []

    def emit(self, kind: str, **payload) -> dict:
        event = {
            "schema_version": 1,
            "seq": self.count,
            "elapsed_s": round(time.monotonic() - self.started, 6),
            "kind": kind,
            "payload": payload,
        }
        line = json.dumps(event, ensure_ascii=False, allow_nan=False)
        self.file.write(line + "\n")
        self.file.flush()
        self.events.append(event)
        self.count += 1
        return event

    def observation(self, obs) -> None:
        data = obs.to_dict()
        for frame in data["frames"]:
            source = Path(frame["image_path"])
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            suffix = source.suffix.lower()
            if suffix not in (".png", ".jpg", ".jpeg", ".svg"):
                raise ValueError("Unsupported frame format")
            relative = Path("frames") / (digest + suffix)
            dest = self.root / relative
            dest.parent.mkdir(exist_ok=True)
            if not dest.exists():
                shutil.copyfile(source, dest)
            frame["image_path"] = relative.as_posix()
            frame["sha256"] = digest
        self.emit("observation", **data)

    def finish(self, summary: dict) -> None:
        self.emit("episode_end", **summary)
        (self.root / "summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8"
        )
        self.file.close()
        export_viewer(self.root)


def export_viewer(root: str | Path) -> Path:
    root = Path(root)
    events = []
    for line in (root / "events.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    # Embedded JSON must not be able to end the script element.
    encoded = json.dumps(events, ensure_ascii=False).replace("<", "\\u003c")
    template = files("embodied_harness").joinpath("web/viewer.html").read_text(encoding="utf-8")
    dest = root / "index.html"
    dest.write_text(template.replace("__TRACE_DATA__", encoded), encoding="utf-8")
    return dest
