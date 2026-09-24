"""CLI: runnable offline demo, GPT episodes, simulator smoke checks and reports."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import sys
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .adapters import create_environment, load_factory
from .runner import run_episode
from .trace import Trace, export_viewer


def step(identifier, tool, arguments):
    return {"id": identifier, "tool": tool, "arguments": arguments, "require_fact": None}


class DemoPlanner:
    """A deterministic fixture, explicitly not a language model."""

    def __init__(self, per_tool=False):
        self.index = 0
        actions = [
            step("lift", "move_relative", {"arm": "arm", "direction": "up", "distance": "large"}),
            step(
                "shift", "move_relative", {"arm": "arm", "direction": "left", "distance": "medium"}
            ),
            step("close", "set_gripper", {"arm": "arm", "state": "closed"}),
        ]
        self.plans = [{"steps": [a]} for a in actions] if per_tool else [{"steps": actions}]

    def decide(self, task, observation, registry, history, trace):
        if history and history[-1]["report"]["status"] != "completed":
            return {
                "kind": "finish",
                "outcome": "blocked",
                "summary": "Offline fixture stopped after a tool failure.",
            }
        if self.index >= len(self.plans):
            return {
                "kind": "finish",
                "outcome": "completed",
                "summary": "Offline fixture sequence ended.",
            }
        plan = self.plans[self.index]
        self.index += 1
        return {"kind": "plan", "plan": plan}


class SmokePlanner:
    def __init__(self, arm="arm"):
        self.used, self.arm = False, arm

    def decide(self, task, observation, registry, history, trace):
        if self.used:
            return {
                "kind": "finish",
                "outcome": "blocked",
                "summary": "Interface smoke test only; task success was not attempted.",
            }
        self.used = True
        return {
            "kind": "plan",
            "plan": {
                "steps": [
                    step(
                        "smoke-up",
                        "move_relative",
                        {"arm": self.arm, "direction": "up", "distance": "small"},
                    )
                ]
            },
        }


def read_config(path):
    return json.loads(Path(path).read_text(encoding="utf-8")) if path else {}


def doctor():
    packages = {}
    for name in (
        "embodied-harness",
        "jsonschema",
        "numpy",
        "Pillow",
        "metaworld",
        "mujoco",
        "robosuite",
        "robocasa",
    ):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    print(
        json.dumps(
            {
                "python": sys.version.split()[0],
                "packages": packages,
                "openai_key_configured": bool(os.environ.get("OPENAI_API_KEY")),
                "model_configured": bool(os.environ.get("OPENAI_MODEL")),
                "note": "Installed dependencies do not establish successful simulator or GPT evaluation.",
            },
            indent=2,
        )
    )


def aggregate(root):
    results = [json.loads(p.read_text()) for p in Path(root).rglob("summary.json")]
    groups = {}
    for result in results:
        key = (
            result["environment"],
            result.get("protocol"),
            result.get("model_tested"),
            result.get("provider"),
            result.get("api_mode"),
            result.get("stream"),
            result.get("plan_mode"),
        )
        groups.setdefault(key, []).append(result)
    report = []
    for (env, protocol, model, provider, api_mode, stream, plan_mode), rows in groups.items():
        valid = [r for r in rows if r["status"] != "infrastructure_error"]
        known = [r for r in valid if r.get("environment_success") is not None]
        report.append(
            {
                "environment": env,
                "protocol": protocol,
                "model": model,
                "provider": provider,
                "api_mode": api_mode,
                "stream": stream,
                "plan_mode": plan_mode,
                "episodes": len(rows),
                "infrastructure_errors": len(rows) - len(valid),
                "unknown_outcomes": len(valid) - len(known),
                "successes": sum(r["success"] for r in known),
                "success_rate_on_known_valid_episodes": sum(r["success"] for r in known)
                / len(known)
                if known
                else None,
                "total_api_calls": sum(r["api_calls"] for r in rows),
                "total_wall_seconds": sum(r["wall_seconds"] for r in rows),
            }
        )
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(prog="embodied-harness")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="Offline kinematic fixture; no GPT or physics")
    demo.add_argument("--out", default=None)
    demo.add_argument("--per-tool", action="store_true")
    demo.add_argument("--fault-after", type=int)
    for command in ("run", "smoke"):
        cmd = sub.add_parser(command)
        cmd.add_argument(
            "--env", choices=["libero", "metaworld", "robocasa", "robotwin"], required=True
        )
        cmd.add_argument("--config", help="Operator-authored JSON environment configuration")
        cmd.add_argument("--out", default=None)
        cmd.add_argument("--seed", type=int, default=0)
        if command == "run":
            cmd.add_argument("--task", required=True)
            cmd.add_argument("--model", default=os.environ.get("OPENAI_MODEL"))
            cmd.add_argument(
                "--base-url", default=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
            )
            cmd.add_argument("--reasoning-effort")
            cmd.add_argument("--api-timeout", type=float, default=90.0)
            cmd.add_argument("--plan-mode", choices=["batch", "single"], default="batch")
            cmd.add_argument(
                "--api-mode", choices=["responses", "chat-completions"], default="responses"
            )
            cmd.add_argument("--stream", action="store_true", help="Read Responses SSE events")
            cmd.add_argument("--max-decisions", type=int, default=12)
            cmd.add_argument("--max-control-ticks", type=int, default=1200)
            cmd.add_argument(
                "--tools-factory", help="Optional operator-trusted module:function(env, registry)"
            )
    sub.add_parser("doctor")
    report = sub.add_parser("report")
    report.add_argument("directory")
    view = sub.add_parser("view")
    view.add_argument("directory")
    view.add_argument("--port", type=int, default=8876)
    export = sub.add_parser("export")
    export.add_argument("directory")
    args = parser.parse_args(argv)
    if args.command == "doctor":
        doctor()
        return 0
    if args.command == "report":
        print(json.dumps(aggregate(args.directory), indent=2))
        return 0
    if args.command == "export":
        print(export_viewer(args.directory))
        return 0
    if args.command == "view":
        root = Path(args.directory).resolve()
        if not (root / "index.html").exists():
            export_viewer(root)
        server = ThreadingHTTPServer(
            ("127.0.0.1", args.port), partial(SimpleHTTPRequestHandler, directory=str(root))
        )
        print(f"Trace viewer: http://127.0.0.1:{args.port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    if args.command == "run" and not args.model:
        parser.error("Pass --model with your accessible GPT model ID, or set OPENAI_MODEL")
    if args.command == "run" and (args.max_decisions < 1 or args.max_control_ticks < 1):
        parser.error("Budgets must be positive")
    out = Path(args.out or f"runs/{args.command}-{time.time_ns()}")
    trace = Trace(out)
    try:
        if args.command == "demo":
            env = create_environment("toy", out / "capture", {"fault_after": args.fault_after})
            planner = DemoPlanner(args.per_tool)
            task = "Offline fixture: lift, shift left, and command gripper closed"
        else:
            env = create_environment(args.env, out / "capture", read_config(args.config))
            if args.command == "smoke":
                planner = SmokePlanner("left" if args.env == "robotwin" else "arm")
                task = "Interface smoke test: move TCP up by 2cm; no task-solving claim"
            else:
                from .gpt import GPTPlanner

                planner = GPTPlanner(
                    args.model,
                    base_url=args.base_url,
                    reasoning_effort=args.reasoning_effort,
                    stream=args.stream,
                    api_mode=args.api_mode,
                    timeout_s=args.api_timeout,
                    plan_mode=args.plan_mode,
                )
                task = args.task
        # Plugins may need initialized capabilities. Runner builds the registry after reset.
        tools_factory = (
            load_factory(args.tools_factory)
            if args.command == "run" and args.tools_factory
            else None
        )
        summary = run_episode(
            env,
            planner,
            trace,
            task,
            seed=getattr(args, "seed", 0),
            max_decisions=getattr(args, "max_decisions", 12),
            max_control_ticks=getattr(args, "max_control_ticks", 1200),
            tools_factory=tools_factory,
        )
    except Exception as exc:
        if not trace.file.closed:
            trace.finish({"status": "initialization_error", "message": str(exc)})
        print(f"Initialization failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2))
    print(f"Inspect: embodied-harness view {out}")
    return 2 if summary["status"] == "infrastructure_error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
