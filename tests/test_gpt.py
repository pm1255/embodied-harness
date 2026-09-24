import base64
import json

import pytest

from embodied_harness.adapters.toy import ToyEnvironment
from embodied_harness.cli import step
from embodied_harness.gpt import GPTPlanner
from embodied_harness.protocol import CameraFrame, Observation
from embodied_harness.tools import make_registry
from embodied_harness.trace import Trace


@pytest.fixture
def inputs(tmp_path):
    # A valid 1px PNG; no external image or network needed.
    png = tmp_path / "camera.png"
    png.write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j0ioAAAAASUVORK5CYII="
        )
    )
    obs = Observation(
        "obs-1",
        "ep-1",
        0,
        [CameraFrame("front", 1, 1, str(png), 0)],
        {"eef_position_m": [0, 0, 0]},
        {},
    )
    registry = make_registry(ToyEnvironment(tmp_path / "capture"))
    trace = Trace(tmp_path / "run")
    yield obs, registry, trace
    trace.file.close()


def test_real_request_shape_and_response_parsing(inputs):
    obs, registry, trace = inputs
    plan = {
        "steps": [
            step("lift", "move_relative", {"arm": "arm", "direction": "up", "distance": "small"})
        ]
    }

    def transport(body):
        assert body["store"] is False
        assert body["parallel_tool_calls"] is False
        assert body["tools"][0]["strict"] is True
        content = body["input"][0]["content"]
        assert any(p["type"] == "input_image" for p in content)
        assert "image_path" not in content[0]["text"]
        return {
            "status": "completed",
            "id": "fake-response",
            "model": "gpt-test-fixture",
            "usage": {"input_tokens": 20, "output_tokens": 10},
            "output": [
                {"type": "function_call", "name": "submit_plan", "arguments": json.dumps(plan)}
            ],
        }

    planner = GPTPlanner("gpt-test-fixture", transport=transport)
    assert planner.decide("lift", obs, registry, [], trace) == {"kind": "plan", "plan": plan}
    assert planner.calls == 1 and planner.input_tokens == 20


@pytest.mark.parametrize(
    "response",
    [
        {"status": "incomplete", "output": []},
        {"status": "completed", "output": []},
        {
            "status": "completed",
            "output": [{"type": "function_call", "name": "unknown", "arguments": "{}"}],
        },
        {
            "status": "completed",
            "output": [
                {"type": "function_call", "name": "submit_plan", "arguments": '{"steps":[]}'}
            ],
        },
    ],
)
def test_no_motion_on_incomplete_or_invalid_model_output(inputs, response):
    planner = GPTPlanner("gpt-test-fixture", transport=lambda body: response)
    with pytest.raises(ValueError):
        planner.decide("task", *inputs[:2], [], inputs[2])


def test_key_never_enters_trace(inputs):
    planner = GPTPlanner(
        "gpt-test-fixture",
        api_key="test-secret-not-a-real-key",
        transport=lambda body: {
            "status": "completed",
            "output": [
                {
                    "type": "function_call",
                    "name": "finish",
                    "arguments": '{"outcome":"blocked","summary":"test"}',
                }
            ],
        },
    )
    planner.decide("task", *inputs[:2], [], inputs[2])
    assert "test-secret-not-a-real-key" not in json.dumps(inputs[2].events)
