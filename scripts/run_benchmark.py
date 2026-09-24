"""Run a fixed manifest in isolated simulator processes, retaining every failure.

Runtime map: {"libero": {"python": "/path/python", "env": {"PYTHONPATH": "..."}}}
Credentials are inherited from the environment, never written into reports.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def execute_case(case, runtime, root, mode, model_args, timeout):
    dest = root / case["id"]
    # Refuse reuse, including interrupted cases: each attempt has its own directory.
    dest.mkdir()
    config = dest / "config.json"
    config.write_text(json.dumps(case["config"], indent=2))
    cmd = [
        runtime["python"],
        "-m",
        "embodied_harness",
        mode,
        "--env",
        case["environment"],
        "--config",
        str(config),
        "--seed",
        str(case["seed"]),
        "--out",
        str(dest / "trace"),
    ]
    if mode == "run":
        cmd += ["--task", case["instruction"]] + model_args
    env = {**os.environ, **runtime.get("env", {})}
    started = time.monotonic()
    state, returncode = "finished", None
    try:
        with (dest / "process.log").open("w") as log:
            proc = subprocess.run(
                cmd, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=timeout
            )
            returncode = proc.returncode
    except subprocess.TimeoutExpired:
        state = "process_timeout"
    except OSError as exc:
        state = "launch_error"
        (dest / "process.log").write_text(str(exc))
    path = dest / "trace/summary.json"
    summary = json.loads(path.read_text()) if path.exists() else {}
    events_path = dest / "trace/events.jsonl"
    kinds = []
    tool_statuses = []
    if events_path.exists():
        for line in events_path.read_text().splitlines():
            try:
                event = json.loads(line)
                kinds.append(event["kind"])
                if event["kind"] == "tool_end":
                    tool_statuses.append(event["payload"]["status"])
            except (ValueError, KeyError):
                pass
    # A successful reset alone is not a successful integration test.
    integrated = returncode == 0 and all(
        k in kinds for k in ("observation", "control_tick", "tool_end", "episode_end")
    )
    if mode == "smoke":
        integrated = (
            integrated and bool(tool_statuses) and all(s == "succeeded" for s in tool_statuses)
        )
    result = {
        **case,
        "mode": mode,
        "process_status": state,
        "returncode": returncode,
        "integration_passed": integrated,
        "task_success": mode == "run" and bool(summary.get("success")),
        "wall_seconds": round(time.monotonic() - started, 3),
        "summary": summary,
    }
    (dest / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                "case": case["id"],
                "integrated": integrated,
                "task_success": result["task_success"],
                "status": summary.get("status", state),
            }
        ),
        flush=True,
    )
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", required=True)
    p.add_argument("--runtimes", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--mode", choices=["smoke", "run"], required=True)
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--timeout", type=int, default=900)
    args, model_args = p.parse_known_args()
    manifest = json.loads(Path(args.manifest).read_text())
    runtimes = json.loads(Path(args.runtimes).read_text())
    cases = manifest["cases"]
    ids = [c["id"] for c in cases]
    if len(ids) != len(set(ids)) or any(
        not s or Path(s).name != s or s in (".", "..") for s in ids
    ):
        p.error("case IDs must be unique single directory names")
    if args.workers < 1 or args.timeout < 1:
        p.error("workers and timeout must be positive")
    for case in cases:
        if case["environment"] not in runtimes:
            p.error("Missing runtime: " + case["environment"])
    root = Path(args.out).resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (root / "protocol.json").write_text(
        json.dumps(
            {
                "mode": args.mode,
                "model_arguments": model_args,
                "workers": args.workers,
                "case_timeout_s": args.timeout,
                "planned_episodes": len(cases),
                "manifest_sha256": hashlib.sha256(Path(args.manifest).read_bytes()).hexdigest(),
                "note": "No retry or success filtering; this manifest is a subset unless explicitly stated.",
            },
            indent=2,
        )
    )
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(
            pool.map(
                lambda c: execute_case(
                    c, runtimes[c["environment"]], root, args.mode, model_args, args.timeout
                ),
                cases,
            )
        )
    report = {
        "planned_episodes": len(cases),
        "completed_attempts": len(results),
        "integration_passes": sum(r["integration_passed"] for r in results),
        "task_successes": sum(r["task_success"] for r in results),
        "task_success_rate_all_attempts": sum(r["task_success"] for r in results) / len(cases)
        if args.mode == "run" and cases
        else None,
        "results": results,
    }
    (root / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if all(r["integration_passed"] for r in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
