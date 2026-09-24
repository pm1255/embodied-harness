import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("directory_server", ROOT / "examples/run_directory_broker.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def request(root):
    (root / "broker").mkdir()
    (root / "runs/task").mkdir(parents=True)
    image = root / "runs/task/frame.png"
    image.write_bytes(b"test sensor bytes; no live model in this test")
    return {
        "nonce": "a" * 32, "task": "goal", "history": [], "tools": [],
        "experience": {"memory": "frozen memory"},
        "frame_sha256": {"camera": hashlib.sha256(image.read_bytes()).hexdigest()},
        "observation": {"id": "episode:1", "episode_id": "episode", "timestamp_s": 0,
                        "proprioception": {}, "facts": {},
                        "frames": [{"name": "camera", "width": 1, "height": 1,
                                    "timestamp_s": 0, "image_path": str(image)}]},
    }


def test_server_freezes_frames_and_never_repeats_completed_request(tmp_path):
    packet = request(tmp_path)
    attempts = []

    class Planner:
        calls = 1
        input_tokens = 10
        output_tokens = 3

        def decide(self, task, observation, registry, history, trace):
            attempts.append(task)
            assert Path(observation.frames[0].image_path).parent == tmp_path / "broker"
            trace.emit("model_request", observation_id=observation.id)
            return {"kind": "finish", "outcome": "blocked", "summary": "test only"}

    def factory(context):
        assert context == {"memory": "frozen memory"}
        return Planner()

    assert module.process(tmp_path, packet, factory)
    assert not module.process(tmp_path, packet, factory)
    assert attempts == ["goal"]
    result = json.loads((tmp_path / "broker" / ("a" * 32 + ".response.json")).read_text())
    assert result["calls"] == 1 and result["input_tokens"] == 10


def test_interrupted_request_is_preserved_without_reissuing_provider_call(tmp_path):
    packet = request(tmp_path)
    prefix = tmp_path / "broker" / ("a" * 32 + ".response")
    Path(str(prefix) + ".started.json").write_text('{}')
    Path(str(prefix) + ".events.jsonl").write_text(json.dumps([
        "model_request", {"observation_id": "episode:1"},
    ]) + '\n')
    assert module.process(tmp_path, packet, lambda _: pytest.fail("Must not repeat paid request"))
    result = json.loads(Path(str(prefix) + ".json").read_text())
    assert result["error_kind"] == "InterruptedAttempt" and result["calls"] == 1


@pytest.mark.parametrize("change", ["tampered", "outside"])
def test_server_rejects_changed_or_out_of_campaign_images_before_api(tmp_path, change):
    packet = request(tmp_path)
    if change == "tampered":
        Path(packet["observation"]["frames"][0]["image_path"]).write_bytes(b"changed")
    else:
        private = tmp_path / "private-key"
        private.write_bytes(b"not an image")
        packet["observation"]["frames"][0]["image_path"] = str(private)
    with pytest.raises(ValueError):
        module.process(tmp_path, packet, lambda _: pytest.fail("No API before frame validation"))
