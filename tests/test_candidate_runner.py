import hashlib
import json
from pathlib import Path
import runpy

import pytest

read_bundle = runpy.run_path(str(Path(__file__).parents[1] / "examples/run_candidate.py"))[
    "read_bundle"
]


def test_candidate_runner_pins_exact_bytes_and_identifies_required_primitives(tmp_path):
    source = 'def run(args, api):\n    result = yield from api.call("run_vla", {"instruction": args["instruction"], "chunks": 8})\n    return result\n'
    raw = json.dumps({"program": {"source": source}}).encode()
    path = tmp_path / "candidate.json"
    path.write_bytes(raw)
    sha = hashlib.sha256(raw).hexdigest()
    _, required, saved = read_bundle(path, sha)
    assert required == {"run_vla"} and saved == raw
    path.write_bytes(raw + b"\n")
    with pytest.raises(ValueError, match="exact artifact"):
        read_bundle(path, sha)


def test_matching_hash_does_not_admit_unrestricted_python(tmp_path):
    raw = json.dumps(
        {"program": {"source": "import os\ndef run(args, api):\n    return {}\n"}}
    ).encode()
    path = tmp_path / "candidate.json"
    path.write_bytes(raw)
    with pytest.raises(ValueError):
        read_bundle(path, hashlib.sha256(raw).hexdigest())
