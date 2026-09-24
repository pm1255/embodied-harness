import copy
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "examples"))
spec = importlib.util.spec_from_file_location(
    "evolution_controller", ROOT / "examples/run_program_evolution.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def protocols():
    return [
        json.loads((ROOT / "benchmarks" / name).read_text())
        for name in ("libero-program-transfer.json", "libero-program-transfer-round2.json")
    ]


def write(tmp_path, values):
    paths = []
    for i, value in enumerate(values):
        path = tmp_path / f"input-{i}.json"
        path.write_text(json.dumps(value))
        paths.append(path)
    return paths


def test_predeclare_all_rounds_and_preserve_exact_protocols(tmp_path):
    values = protocols()
    result = module.freeze_protocols(write(tmp_path, values), tmp_path / "frozen")
    assert result == values
    assert json.loads((tmp_path / "frozen/round-2.json").read_text()) == values[1]


@pytest.mark.parametrize("violation", ["reset_leakage", "changed_goal", "changed_budget"])
def test_reject_evaluation_drift_before_any_proposal(tmp_path, violation):
    values = copy.deepcopy(protocols())
    if violation == "reset_leakage":
        # Reuse a prior HELDOUT state as new DEVELOPMENT under a different RNG seed.
        values[1]["cases"][0]["config"]["init_state_index"] = values[0]["cases"][4]["config"][
            "init_state_index"
        ]
    elif violation == "changed_goal":
        values[1]["cases"][0]["instruction"] = "an easier replacement goal"
    else:
        values[1]["max_control_ticks"] = 1200
    with pytest.raises(ValueError):
        module.freeze_protocols(write(tmp_path, values), tmp_path / "frozen")
    assert not (tmp_path / "frozen").exists()
