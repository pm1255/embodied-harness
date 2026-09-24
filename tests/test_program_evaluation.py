import hashlib
import json

import pytest

from embodied_harness.rsi.program_evaluation import evaluate_validation


def paired_evidence(tmp_path):
    source = 'def run(args, api):\n    return {"status": "succeeded"}\n'
    candidate = {"candidate_id": "candidate/test", "program": {"source": source}}
    protocol = {
        "cases": [{"id": name, "split": "validation"} for name in ("a", "b")],
        "max_control_ticks": 960,
        "max_decisions": 24,
        "model": "test-model",
        "planner_settings": {"reasoning_effort": "high"},
    }
    rows = []
    for name in ("a", "b"):
        for arm in ("baseline", "candidate"):
            root = tmp_path / (name + arm)
            root.mkdir()
            summary = {
                "status": "native_success",
                "success": True,
                "native_terminal_success": True,
                "control_ticks": 100,
                "decisions": 2 if arm == "candidate" else 4,
                "api_calls": 2 if arm == "candidate" else 4,
            }
            events = [
                {
                    "kind": "episode_start",
                    "payload": {"max_control_ticks": 960, "max_decisions": 24},
                },
                {
                    "kind": "model_request",
                    "payload": {"model": "test-model", "reasoning_effort": "high"},
                },
                {"kind": "environment_terminal", "payload": {"condition_met": True}},
                {"kind": "episode_end", "payload": summary},
            ]
            if arm == "candidate":
                events += [
                    {
                        "kind": "program_registered",
                        "payload": {"source_sha256": hashlib.sha256(source.encode()).hexdigest()},
                    },
                    {"kind": "program_step", "payload": {}},
                ]
            (root / "summary.json").write_text(json.dumps(summary))
            (root / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
            rows.append(
                {
                    "case_id": name,
                    "arm": arm,
                    "split": "validation",
                    "initial_state_sha256": name,
                    "trace": str(root),
                    "summary": summary,
                }
            )
    return rows, protocol, candidate


def test_gate_uses_only_complete_paired_validation_and_ignores_heldout(tmp_path):
    rows, protocol, candidate = paired_evidence(tmp_path)
    rows.append({"split": "heldout", "summary": {"success": False}})
    report = evaluate_validation(rows, protocol, candidate)
    assert all(
        report[k]
        for k in (
            "transfer_passed",
            "retention_passed",
            "budget_passed",
            "contract_passed",
            "evidence_verified",
        )
    )
    assert report["heldout_used_for_selection"] is False
    with pytest.raises(ValueError, match="Incomplete"):
        evaluate_validation(rows[1:], protocol, candidate)


@pytest.mark.parametrize("corruption", ["reset", "source", "unused", "terminal", "score"])
def test_gate_rejects_unverified_improvement(tmp_path, corruption):
    rows, protocol, candidate = paired_evidence(tmp_path)
    row = rows[1]
    path = tmp_path / "acandidate" / "events.jsonl"
    events = [json.loads(line) for line in path.read_text().splitlines()]
    if corruption == "reset":
        row["initial_state_sha256"] = "other-reset"
    elif corruption == "source":
        candidate["program"]["source"] += "# changed\n"
    elif corruption == "unused":
        events = [e for e in events if e["kind"] != "program_step"]
    elif corruption == "terminal":
        events = [e for e in events if e["kind"] != "environment_terminal"]
    else:
        row["summary"]["api_calls"] = 0
    path.write_text("".join(json.dumps(e) + "\n" for e in events))
    report = evaluate_validation(rows, protocol, candidate)
    assert not (report["evidence_verified"] and report["transfer_passed"])


def test_supplement_binds_frozen_artifact_and_never_selects_using_heldout(tmp_path):
    import runpy
    from pathlib import Path

    combine = runpy.run_path(
        str(Path(__file__).parents[1] / "examples/confirm_program_transfer.py")
    )["combine"]
    rows, protocol, candidate = paired_evidence(tmp_path)
    protocol.update(candidate_sha256="frozen", checkpoint_sha256="weights")
    rows.append({"split": "heldout", "summary": {"success": False}})
    campaign = tmp_path / "campaign"
    campaign.mkdir()
    (campaign / "protocol.json").write_text(json.dumps(protocol))
    (campaign / "results.json").write_text(json.dumps({"completed": True, "rows": rows}))
    assert combine([campaign], candidate, "frozen")["transfer_passed"]
    with pytest.raises(ValueError, match="artifact"):
        combine([campaign], candidate, "changed")
    with pytest.raises(ValueError, match="double-count"):
        combine([campaign, campaign], candidate, "frozen")
