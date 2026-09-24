"""Execute one explicitly chosen frozen memory/skill/tool bundle on a new task.

This is an experimental runner, not evidence of mastery or hardware readiness.
The operator installs the environment and binds any VLA endpoint/checkpoint.
"""

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path

from embodied_harness.adapters import create_environment
from embodied_harness.broker import DirectoryPlanner
from embodied_harness.gpt import GPTPlanner
from embodied_harness.rsi.programs import install_program, validate_program
from embodied_harness.runner import run_episode
from embodied_harness.trace import Trace
from embodied_harness.vla import PolicyEndpoint, register_policy


def read_bundle(path, expected_sha256):
    content = Path(path).read_bytes()
    if hashlib.sha256(content).hexdigest() != expected_sha256:
        raise ValueError("Bundle differs from the exact artifact selected by the operator")
    candidate = json.loads(content)
    tree = validate_program(candidate["program"]["source"])
    required = {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "call"
    }
    return candidate, required, content


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bundle", required=True, help="Model-generated candidate.json")
    p.add_argument("--expected-sha256", required=True)
    p.add_argument("--env", required=True, choices=("libero", "metaworld", "robocasa", "robotwin"))
    p.add_argument("--config", required=True)
    p.add_argument("--task", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--model", default=os.environ.get("OPENAI_MODEL"))
    p.add_argument(
        "--base-url", default=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    )
    p.add_argument("--reasoning-effort", default="high")
    p.add_argument("--policy-endpoint")
    p.add_argument("--broker-root", help="Optional credential-free directory planner transport")
    p.add_argument("--checkpoint-sha256")
    p.add_argument("--max-decisions", type=int, default=24)
    p.add_argument("--max-control-ticks", type=int, default=960)
    p.add_argument("--native-success-terminal", action="store_true")
    p.add_argument(
        "--recover-invalid-plans", action="store_true",
        help="Return schema errors to GPT within the existing decision budget; no motion on rejection",
    )
    a = p.parse_args()
    if not a.model or a.max_decisions < 1 or a.max_control_ticks < 1:
        p.error("Choose an accessible model and positive episode budgets")
    if bool(a.policy_endpoint) != bool(a.checkpoint_sha256):
        p.error("Bind both --policy-endpoint and --checkpoint-sha256")
    candidate, required, content = read_bundle(a.bundle, a.expected_sha256)
    if "run_vla" in required and not a.policy_endpoint:
        p.error("This program needs an actual VLA endpoint; no dummy policy is substituted")
    root = Path(a.out)
    root.mkdir(parents=True, exist_ok=False)
    (root / "candidate.json").write_bytes(content)
    context = {
        "memory": candidate["memory"], "skills": [candidate["skill"]],
        "candidate_id": candidate["candidate_id"], "status": "operator_selected_frozen_bundle",
    }
    planner = DirectoryPlanner(a.broker_root, a.model, timeout_s=300, context=context) if a.broker_root else GPTPlanner(
        a.model,
        base_url=a.base_url,
        reasoning_effort=a.reasoning_effort,
        stream=True,
        timeout_s=180,
        context=context,
    )
    endpoint = PolicyEndpoint(a.policy_endpoint, a.checkpoint_sha256) if a.policy_endpoint else None
    trace = Trace(root)
    trace.emit(
        "candidate_identity",
        candidate_id=candidate["candidate_id"],
        candidate_sha256=a.expected_sha256,
        purpose="new_task_execution_not_promotion",
    )
    env = create_environment(a.env, root / "camera", json.loads(Path(a.config).read_text()))

    def register(e, registry):
        if endpoint:
            register_policy(e, registry, endpoint)
        if not required <= registry.tools.keys():
            raise ValueError(
                "Program requires unavailable robot primitives: "
                + str(sorted(required - registry.tools.keys()))
            )
        install_program(registry, candidate["program"], trace=trace)

    summary = run_episode(
        env,
        planner,
        trace,
        a.task,
        seed=a.seed,
        max_decisions=a.max_decisions,
        max_control_ticks=a.max_control_ticks,
        tools_factory=register,
        stop_on_native_success=a.native_success_terminal,
        recover_invalid_plans=a.recover_invalid_plans,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
