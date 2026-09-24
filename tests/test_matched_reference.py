import copy
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "matched_reference", ROOT / "scripts/export_matched_reference.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_failed_provider_usage_remains_unknown_while_reported_zero_is_valid():
    events = [
        {"kind": "model_request", "payload": {}},
        {"kind": "model_response", "payload": {"usage": {}}},
        {"kind": "model_request", "payload": {}},
        {"kind": "model_response", "payload": {"usage": {
            "input_tokens": 0, "output_tokens": 0,
        }}},
    ]
    assert module.usage_missing_calls(events) == 1
    assert module.usage_missing_calls([]) == 0


def evidence():
    protocol = {
        "max_decisions": 24,
        "max_control_ticks": 960,
        "success_criterion": "native_success_terminal",
        "checkpoint_sha256": "fixed",
        "cases": [
            {
                "id": "a",
                "seed": 7,
                "instruction": "original full goal",
                "config": {"init_state_index": 7},
            }
        ],
    }
    scope = [
        {"case_id": "a", "arm": arm, "initial_state_sha256": "same", "summary": {"success": False}}
        for arm in ("baseline", "candidate")
    ]
    reference = [{"case_id": "a", "arm": "checkpoint_only", "initial_state_sha256": "same"}]
    return protocol, copy.deepcopy(protocol), scope, reference


def test_complete_reference_keeps_unsuccessful_pairs():
    p, q, rows, reference = evidence()
    assert set(module.verify_matched_cases(p, q, rows, reference)) == {"a"}


@pytest.mark.parametrize("drift", ["omit_failure", "initial_state", "goal", "budget", "duplicate"])
def test_reject_misleading_reference_comparisons(drift):
    p, q, rows, reference = evidence()
    if drift == "omit_failure":
        rows.pop()
    elif drift == "initial_state":
        reference[0]["initial_state_sha256"] = "different-reset"
    elif drift == "goal":
        q["cases"][0]["instruction"] = "easier replacement"
    elif drift == "budget":
        q["max_control_ticks"] = 1200
    else:
        reference += copy.deepcopy(reference)
    with pytest.raises(ValueError):
        module.verify_matched_cases(p, q, rows, reference)
