"""Run the credential-holding planner on a Linux CPU host beside simulator storage.

The GPU worker uses DirectoryPlanner and receives no API credential. Keep the key
outside the campaign, generated-program namespace and public evidence archives.
"""

import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import time

from jsonschema import ValidationError

from embodied_harness.gpt import GPTPlanner
from embodied_harness.protocol import CameraFrame, Observation
from embodied_harness.runtime import Registry, Tool


def process(root, request, planner_factory, key=""):
    root = Path(root).resolve()
    nonce = request["nonce"]
    if len(nonce) != 32 or any(c not in "0123456789abcdef" for c in nonce):
        raise ValueError("Invalid broker nonce")
    target = root / "broker" / (nonce + ".response.json")
    if target.exists():
        return False
    journal = target.with_suffix(".events.jsonl")
    marker = target.with_suffix(".started.json")
    events = []

    class Recorder:
        def emit(self, kind, **payload):
            events.append([kind, payload])
            with journal.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps([kind, payload], ensure_ascii=False) + "\n")

    if marker.exists():
        events = [json.loads(line) for line in journal.read_text().splitlines()] if journal.exists() else []
        response = {
            "nonce": nonce, "decision": None, "events": events,
            "error": "Interrupted broker attempt; no automatic paid-request retry",
            "error_kind": "InterruptedAttempt", "validation_message": None,
            "calls": sum(kind == "model_request" for kind, _ in events),
            **{field: sum((payload.get("usage") or {}).get(field, 0)
                          for kind, payload in events if kind == "model_response")
               for field in ("input_tokens", "output_tokens")},
        }
    else:
        observation = dict(request["observation"])
        frames = []
        for index, frame in enumerate(observation["frames"]):
            path = Path(frame["image_path"]).resolve(strict=True)
            path.relative_to(root / "runs")
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != request["frame_sha256"][frame["name"]]:
                raise ValueError("Sensor frame changed before model input")
            frozen = root / "broker" / (nonce + f"-{index}.png")
            frozen.write_bytes(content)
            frames.append(CameraFrame(**dict(frame, image_path=str(frozen))))
        observation["frames"] = frames
        registry = Registry()
        for tool in request["tools"]:
            registry.add(Tool(tool["name"], tool["description"], tool["parameters"], None,
                              tool["timeout_s"], tool["max_ticks"]))
        # Write before invoking the provider. A restart never repeats an ambiguous call.
        marker.write_text(json.dumps({"nonce": nonce, "started_at": time.time(),
                                      "frame_sha256": request["frame_sha256"]}))
        planner = planner_factory(request.get("experience", {}))
        error = error_kind = validation_message = None
        try:
            decision = planner.decide(request["task"], Observation(**observation), registry,
                                      request["history"], Recorder())
        except Exception as exc:
            decision = None
            error, error_kind = str(exc), type(exc).__name__
            if key:
                error = error.replace(key, "[redacted]")
            if isinstance(exc, ValidationError):
                errors = [exc]
                for item in errors:
                    errors.extend(item.context)
                bounds = [f"Argument {list(item.absolute_path)} exceeds maxLength={item.validator_value}."
                          for item in errors if item.validator == "maxLength"]
                validation_message = (bounds[0] if bounds else error)[:1500]
        response = {"nonce": nonce, "decision": decision, "events": events,
                    "error": error, "error_kind": error_kind,
                    "validation_message": validation_message, "calls": planner.calls,
                    "input_tokens": planner.input_tokens, "output_tokens": planner.output_tokens}
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(response, ensure_ascii=False))
    temporary.replace(target)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--key-file", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--reasoning-effort", default="high")
    parser.add_argument("--max-requests", type=int, default=48)
    parser.add_argument("--duration", type=int, default=3600)
    args = parser.parse_args()
    if args.max_requests < 1 or args.duration < 1:
        parser.error("Use positive request and duration budgets")
    root = Path(args.root).resolve()
    (root / "broker").mkdir(parents=True, exist_ok=True)
    lock = (root / "broker/server.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    key = Path(args.key_file).read_text().strip()
    deadline = time.monotonic() + args.duration

    def factory(context):
        return GPTPlanner(args.model, api_key=key, base_url=args.base_url, stream=True,
                          timeout_s=180, reasoning_effort=args.reasoning_effort, context=context)

    for marker in (root / "broker").glob("*.started.json"):
        process(root, {"nonce": marker.name.split(".")[0]}, factory, key)
    while time.monotonic() < deadline:
        path = root / "broker/request.json"
        if path.exists():
            request = json.loads(path.read_text())
            existing = root / "broker" / (request["nonce"] + ".response.started.json")
            if not existing.exists() and len(list((root / "broker").glob("*.started.json"))) >= args.max_requests:
                break
            if process(root, request, factory, key):
                print(json.dumps({"completed_requests": len(list((root / "broker").glob("*.response.json")))}), flush=True)
        time.sleep(0.2)


if __name__ == "__main__":
    main()
