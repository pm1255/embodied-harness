"""Subprocess failures must remain in the planned denominator."""

import importlib.util
from pathlib import Path
import subprocess
import sys
import json

import pytest

spec = importlib.util.spec_from_file_location(
    "benchmark_runner", Path(__file__).parents[1] / "scripts/run_benchmark.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize(
    "mode,behavior", [("smoke", "timeout"), ("run", "crash"), ("smoke", "tool_failed")]
)
def test_failed_attempt_retained_and_never_reused(tmp_path, monkeypatch, mode, behavior):
    case = dict(id="case-0", environment="libero", seed=0, instruction="Move", config={})

    def run(cmd, **kw):
        if behavior == "timeout":
            raise subprocess.TimeoutExpired(cmd, 1)
        trace = tmp_path / "case-0/trace"
        trace.mkdir()
        events = [
            dict(kind=k, payload={"status": "failed"} if k == "tool_end" else {})
            for k in ["observation", "control_tick", "tool_end", "episode_end"]
        ]
        (trace / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
        return subprocess.CompletedProcess(cmd, 1 if behavior == "crash" else 0)

    monkeypatch.setattr(module.subprocess, "run", run)
    result = module.execute_case(case, {"python": sys.executable}, tmp_path, mode, [], 1)
    assert not result["integration_passed"]
    assert not result["task_success"]
    assert (tmp_path / "case-0/result.json").exists()
    with pytest.raises(FileExistsError):
        module.execute_case(case, {"python": sys.executable}, tmp_path, mode, [], 1)
