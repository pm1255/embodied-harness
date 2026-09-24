import json
from pathlib import Path
import runpy
import tarfile

import pytest

extract = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts/extract_development_evidence.py")
)["extract"]


def campaign(tmp_path):
    protocol = {
        "arms": ["baseline", "candidate"],
        "cases": [
            {"id": "dev", "split": "validation"},
            {"id": "SECRET_TEST_CASE", "split": "heldout"},
        ],
    }
    rows = []
    for arm in protocol["arms"]:
        root = tmp_path / ("dev--" + arm)
        root.mkdir()
        summary = {"success": True}
        (root / "summary.json").write_text(json.dumps(summary))
        (root / "events.jsonl").write_text(
            json.dumps({"kind": "episode_end", "payload": summary}) + "\n"
        )
        rows.append({"case_id": "dev", "arm": arm, "split": "validation", "summary": summary})
    # There is deliberately no readable held-out directory. It must never be opened.
    rows.append(
        {
            "case_id": "SECRET_TEST_CASE",
            "arm": "candidate",
            "split": "heldout",
            "summary": {"secret_score": 12345},
        }
    )
    (tmp_path / "protocol.json").write_text(json.dumps(protocol))
    (tmp_path / "results.json").write_text(json.dumps({"completed": False, "rows": rows}))
    (tmp_path / "validation-gate.json").write_text(json.dumps({"split": "validation"}))
    return rows


def test_feedback_excludes_heldout_even_while_campaign_is_running(tmp_path):
    campaign(tmp_path)
    output = tmp_path / "feedback.tar.gz"
    assert extract(tmp_path, output)["episodes"] == 2
    with tarfile.open(output) as archive:
        text = b"".join(archive.extractfile(m).read() for m in archive.getmembers())
    assert b"SECRET_TEST_CASE" not in text and b"12345" not in text


def test_feedback_rejects_missing_paired_validation(tmp_path):
    rows = campaign(tmp_path)
    (tmp_path / "results.json").write_text(json.dumps({"rows": rows[1:]}))
    with pytest.raises(ValueError, match="Complete unique paired"):
        extract(tmp_path, tmp_path / "incomplete.tar.gz")
