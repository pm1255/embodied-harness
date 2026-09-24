import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("cost_audit", ROOT / "scripts/audit_broker_costs.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_late_request_is_counted_once_and_missing_usage_is_not_free(tmp_path):
    campaign, broker = tmp_path / "campaign", tmp_path / "broker"
    episode = campaign / "task--candidate"
    episode.mkdir(parents=True)
    broker.mkdir()
    (campaign / "protocol.json").write_text('{}')
    (campaign / "results.json").write_text(json.dumps({
        "completed": True,
        "rows": [{"summary": {"api_calls": 1, "input_tokens": 12, "output_tokens": 3}}],
    }))
    (episode / "events.jsonl").write_text('\n'.join(json.dumps(e) for e in [
        {"kind": "observation", "payload": {"episode_id": "ep"}},
        {"kind": "model_request", "payload": {"observation_id": "ep:1"}},
    ]))
    for index in (1, 2):
        usage = {"input_tokens": 12, "output_tokens": 3} if index == 1 else {}
        (broker / f'{index}.response.json').write_text(json.dumps({
            "nonce": str(index), "calls": 1, "input_tokens": 12 if index == 1 else 0,
            "output_tokens": 3 if index == 1 else 0,
            "events": [["model_request", {"observation_id": f"ep:{index}"}],
                       ["model_response", {"usage": usage, "response_id": "provider-private"}]],
        }))
    report = module.audit(campaign, broker)
    assert report["broker_recorded_api_attempts"] == 2
    assert report["worker_recorded_api_attempts"] == 1
    assert report["unacknowledged_api_attempts"] == report["usage_missing_calls"] == 1
    assert report["input_tokens"] == 12 and report["output_tokens"] == 3
    assert "provider-private" not in json.dumps(report)
    (broker / '1.response.json').unlink()
    with pytest.raises(ValueError, match="missing"):
        module.audit(campaign, broker)
