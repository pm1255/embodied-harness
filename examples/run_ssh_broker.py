"""Bounded SSH decision broker. Keep the GPT credential off simulator workers."""

import argparse
import json
from pathlib import Path, PurePosixPath
import subprocess
import time

from embodied_harness.gpt import GPTPlanner
from embodied_harness.protocol import CameraFrame, Observation
from embodied_harness.runtime import Registry, Tool


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", required=True)
    p.add_argument("--remote-root", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--key-file", required=True)
    p.add_argument("--model", default="gpt-6-astra")
    p.add_argument("--base-url", required=True)
    p.add_argument("--reasoning-effort", default="low", choices=("low", "medium", "high", "xhigh"))
    p.add_argument("--max-requests", type=int, default=48)
    p.add_argument("--duration", type=int, default=7200)
    a = p.parse_args()
    remote = PurePosixPath(a.remote_root)
    if not remote.is_absolute() or any(
        c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/_-."
        for c in str(remote)
    ):
        raise ValueError("Use an absolute simple remote directory")
    local = Path(a.out)
    local.mkdir(parents=True, exist_ok=True)
    key = Path(a.key_file).read_text().strip()
    seen = set()
    start = time.monotonic()
    count = len(list(local.glob("*.response.json")))

    def ssh(command):
        return subprocess.run(
            ["ssh", "-o", "BatchMode=yes", a.host, command],
            capture_output=True,
            text=True,
            timeout=30,
        )

    while time.monotonic() - start < a.duration:
        try:
            result = ssh("cat " + str(remote / "broker/request.json") + " 2>/dev/null")
        except subprocess.TimeoutExpired:
            # A transient read failure must not kill the decision relay. No API
            # request has been made at this point, so this retry is unambiguous.
            time.sleep(2)
            continue
        if result.returncode:
            time.sleep(2)
            continue
        request = json.loads(result.stdout)
        nonce = request["nonce"]
        if nonce in seen:
            time.sleep(2)
            continue
        if len(nonce) != 32 or any(c not in "0123456789abcdef" for c in nonce):
            raise ValueError("Invalid request nonce")
        saved = local / (nonce + ".response.json")
        if saved.exists():
            # Restarting a broker may redeliver a completed response, but must
            # never repeat a paid model request for the same observation nonce.
            tmp = str(remote / "broker" / (nonce + ".tmp"))
            subprocess.run(["scp", "-q", str(saved), a.host + ":" + tmp], check=True, timeout=30)
            moved = ssh("mv " + tmp + " " + str(remote / "broker" / (nonce + ".response.json")))
            if moved.returncode:
                raise RuntimeError("Could not redeliver saved decision")
            seen.add(nonce)
            continue
        if count >= a.max_requests:
            break
        seen.add(nonce)
        count += 1
        observation = request["observation"]
        for i, frame in enumerate(observation["frames"]):
            path = PurePosixPath(frame["image_path"])
            if (
                ".." in path.parts
                or not path.is_relative_to(remote / "runs")
                or any(c in str(path) for c in "' \n\r")
            ):
                raise ValueError("Unexpected sensor artifact path")
            target = local / (nonce + f"-{i}.png")
            subprocess.run(
                ["scp", "-q", a.host + ":" + str(path), str(target)], check=True, timeout=60
            )
            frame["image_path"] = str(target)
        observation["frames"] = [CameraFrame(**f) for f in observation["frames"]]
        registry = Registry()
        for tool in request["tools"]:
            registry.add(
                Tool(
                    tool["name"],
                    tool["description"],
                    tool["parameters"],
                    None,
                    tool["timeout_s"],
                    tool["max_ticks"],
                )
            )
        planner = GPTPlanner(
            a.model,
            api_key=key,
            base_url=a.base_url,
            stream=True,
            timeout_s=180,
            reasoning_effort=a.reasoning_effort,
            context=request.get("experience", {}),
        )

        class Recorder:
            def __init__(self):
                self.events = []

            def emit(self, kind, **payload):
                self.events.append([kind, payload])

        trace = Recorder()
        try:
            decision = planner.decide(
                request["task"], Observation(**observation), registry, request["history"], trace
            )
            error = None
        except Exception as exc:
            decision = None
            error = (type(exc).__name__ + ": " + str(exc)).replace(key, "[redacted]")
        response = {
            "nonce": nonce,
            "decision": decision,
            "events": trace.events,
            "error": error,
            "calls": planner.calls,
            "input_tokens": planner.input_tokens,
            "output_tokens": planner.output_tokens,
        }
        target = local / (nonce + ".response.json")
        target.write_text(json.dumps(response))
        tmp = str(remote / "broker" / (nonce + ".tmp"))
        subprocess.run(["scp", "-q", str(target), a.host + ":" + tmp], check=True, timeout=30)
        moved = ssh("mv " + tmp + " " + str(remote / "broker" / (nonce + ".response.json")))
        if moved.returncode:
            raise RuntimeError("Could not deliver decision")
        print(
            json.dumps({"request": count, "nonce": nonce, "error": error, "decision": decision}),
            flush=True,
        )


if __name__ == "__main__":
    main()
