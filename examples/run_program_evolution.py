"""Run predeclared repair rounds, feeding back development evidence only.

Requires a running policy endpoint and broker, plus the installed LIBERO runtime.
This controller does not provision GPUs or claim mastery after its small gate.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile

from record_program_evaluation import record


def freeze_protocols(paths, destination):
    """Reject test/development overlap before the first model request."""
    destination = Path(destination)
    protocols, seen, goals = [], set(), {}
    fixed = None
    families = {"libero_spatial", "libero_object", "libero_goal", "libero_10"}
    for path in map(Path, paths):
        protocol = json.loads(path.read_text())
        settings = {
            key: protocol[key]
            for key in (
                "model",
                "checkpoint_sha256",
                "planner_settings",
                "max_decisions",
                "max_control_ticks",
                "success_criterion",
                "arms",
            )
        }
        if fixed is not None and settings != fixed:
            raise ValueError("All rounds must preserve models, evaluator, budgets and arms")
        fixed = settings
        if (protocol["max_decisions"], protocol["max_control_ticks"]) != (24, 960):
            raise ValueError("This proposer currently implements the 24-decision/960-tick pilot")
        if protocol["arms"] != ["baseline", "candidate"]:
            raise ValueError("Paired baseline/candidate arms required")
        if protocol["success_criterion"] != "native_success_terminal":
            raise ValueError("Frozen native success evaluator required")
        if protocol["planner_settings"].get("reasoning_effort") != "high":
            raise ValueError("This proposal protocol uses high reasoning effort")
        for split in ("validation", "heldout"):
            cases = [c for c in protocol["cases"] if c["split"] == split]
            if len(cases) != 4 or {c["config"]["suite"] for c in cases} != families:
                raise ValueError("This proposer requires four original task-0 families per split")
            for case in cases:
                config = case["config"]
                if config["task_id"] != 0:
                    raise ValueError("This proposer currently uses task 0 in each family")
                family = config["suite"]
                goal = case["instruction"]
                if family in goals and goals[family] != goal:
                    raise ValueError("Original task instructions must remain unchanged")
                goals[family] = goal
                # Same simulator reset with a different RNG seed is still a reused scene.
                identity = (config["suite"], config["task_id"], config["init_state_index"])
                if identity in seen:
                    raise ValueError("No reset may cross rounds or development/heldout splits")
                seen.add(identity)
        splits = [c["split"] for c in protocol["cases"]]
        if splits != ["validation"] * 4 + ["heldout"] * 4:
            raise ValueError("Seal development selection before collecting heldout cases")
        protocols.append(protocol)
    if not protocols:
        raise ValueError("At least one predeclared round is required")
    destination.mkdir(parents=True, exist_ok=False)
    for i, protocol in enumerate(protocols, 1):
        (destination / f"round-{i}.json").write_text(json.dumps(protocol, indent=2) + "\n")
    return protocols


def run_step(command, log):
    # Commands contain a key-file path, never the secret; do not echo argv into artifacts.
    with Path(log).open("x") as stream:
        subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True)


def run(args):
    root = Path(args.out).resolve()
    root.mkdir(parents=True, exist_ok=False)
    protocols = freeze_protocols(args.round_protocol, root / "predeclared")
    if any(p["model"] != args.model for p in protocols):
        raise ValueError("Proposal model must match the predeclared experiment brain")
    examples = Path(__file__).resolve().parent
    extractor = examples.parent / "scripts/extract_development_evidence.py"
    evidence, parent = str(Path(args.campaign).resolve()), None
    state = {"rounds": [], "heldout_used_for_proposals": False, "mastery_established": False}

    def save(status):
        state["status"] = status
        (root / "controller.json").write_text(json.dumps(state, indent=2) + "\n")

    save("running")
    try:
        for number, template in enumerate(protocols, 1):
            current = root / f"round-{number}"
            current.mkdir()
            previous = None
            for attempt in (1, 2):
                proposal = current / f"proposal-{attempt}"
                command = [
                    sys.executable,
                    str(examples / "propose_baseline_repair.py"),
                    "--campaign",
                    evidence,
                    "--out",
                    str(proposal),
                    "--key-file",
                    args.key_file,
                    "--base-url",
                    args.base_url,
                    "--model",
                    args.model,
                ]
                if parent:
                    command += ["--parent-proposal", str(parent)]
                if previous:
                    command += ["--previous-proposal", str(previous)]
                try:
                    run_step(command, current / f"proposal-{attempt}.log")
                    break
                except subprocess.CalledProcessError:
                    if not (proposal / "rejected.json").exists() or attempt == 2:
                        raise
                    previous = proposal
            candidate = proposal / "candidate.json"
            protocol = dict(
                template, candidate_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest()
            )
            manifest = current / "protocol.json"
            manifest.write_text(json.dumps(protocol, indent=2) + "\n")
            campaign = current / "evaluation"
            run_step(
                [
                    args.sim_python,
                    str(examples / "run_program_validation.py"),
                    "--manifest",
                    str(manifest),
                    "--candidate",
                    str(candidate),
                    "--out",
                    str(campaign),
                    "--broker",
                    args.broker,
                    "--endpoint",
                    args.endpoint,
                ],
                current / "evaluation.log",
            )
            decision = record(proposal, campaign, activate=True)
            state["rounds"].append(
                {"round": number, "proposal": str(proposal.relative_to(root)), **decision}
            )
            save("running")
            if decision["accepted"]:
                save("advance_to_original_scope_mastery_evaluation")
                return state
            archive = current / "development-only.tar.gz"
            run_step(
                [
                    sys.executable,
                    str(extractor),
                    "--campaign",
                    str(campaign),
                    "--output",
                    str(archive),
                ],
                current / "feedback.log",
            )
            with tarfile.open(archive) as stream:
                for member in stream.getmembers():
                    target = (current / member.name).resolve()
                    target.relative_to(current.resolve())
                    if not member.isfile():
                        raise ValueError("Feedback must contain regular files only")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open("xb") as output:
                        output.write(stream.extractfile(member).read())
            evidence, parent = str(current / "development-only"), proposal
        save("predeclared_round_budget_exhausted_not_capability_limit")
    except Exception:
        save("interrupted_see_preserved_step_logs")
        raise
    return state


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--campaign", required=True, help="Completed initial development baseline")
    p.add_argument("--round-protocol", action="append", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--key-file", required=True)
    p.add_argument("--base-url", required=True)
    p.add_argument("--model", default="gpt-6-astra")
    p.add_argument("--broker", required=True)
    p.add_argument("--endpoint", default="http://127.0.0.1:8907")
    p.add_argument("--sim-python", default=sys.executable)
    print(json.dumps(run(p.parse_args()), indent=2))
