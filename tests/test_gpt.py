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


def test_stream_ignores_partial_arguments_and_uses_terminal_response():
    import io

    from embodied_harness.gpt import read_response_stream

    terminal = {"status": "completed", "output": []}
    events = [
        {"type": "response.function_call_arguments.delta", "delta": '{"steps":'},
        {"type": "response.completed", "response": terminal},
    ]
    stream = io.BytesIO(
        b": keepalive\n\n"
        + b"".join(("data: " + json.dumps(event) + "\n\n").encode() for event in events)
    )
    assert read_response_stream(stream) == terminal


def test_stream_disconnect_cannot_become_a_plan():
    import io

    from embodied_harness.gpt import read_response_stream

    with pytest.raises(ValueError, match="without a terminal"):
        read_response_stream(io.BytesIO(b'data: {"type":"response.created"}\n\n'))


def test_stream_error_redacts_upstream_message():
    import io

    from embodied_harness.gpt import read_response_stream

    with pytest.raises(RuntimeError, match="^GPT API returned a stream error$"):
        read_response_stream(io.BytesIO(b'data: {"type":"error","message":"secret"}\n\n'))


def test_stream_deadline_is_checked_on_incoming_events():
    import io

    from embodied_harness.gpt import read_response_stream

    with pytest.raises(TimeoutError, match="time budget"):
        read_response_stream(io.BytesIO(b": keepalive\n\n"), deadline=0)


def test_chat_compatibility_preserves_images_tools_and_usage(inputs):
    def transport(body):
        assert body["messages"][0]["role"] == "system"
        assert any(x["type"] == "image_url" for x in body["messages"][1]["content"])
        assert body["tools"][0]["function"]["name"] == "submit_plan"
        assert body["tools"][0]["function"]["strict"] is True
        return {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "tool_calls": [
                            {
                                "id": "fixture-call",
                                "type": "function",
                                "function": {
                                    "name": "finish",
                                    "arguments": '{"outcome":"blocked","summary":"fixture"}',
                                },
                            }
                        ]
                    },
                }
            ],
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 5,
                "input_tokens": 0,
                "output_tokens": 0,
            },
        }

    planner = GPTPlanner("fixture", api_mode="chat-completions", transport=transport)
    assert planner.decide("task", *inputs[:2], [], inputs[2])["outcome"] == "blocked"
    assert (planner.input_tokens, planner.output_tokens) == (12, 5)


def test_chat_truncated_tool_call_is_rejected(inputs):
    planner = GPTPlanner(
        "fixture",
        api_mode="chat-completions",
        transport=lambda body: {
            "choices": [{"finish_reason": "length", "message": {"tool_calls": []}}]
        },
    )
    with pytest.raises(ValueError, match="complete tool call"):
        planner.decide("task", *inputs[:2], [], inputs[2])


def test_single_primitive_mode_preserves_raw_model_call(inputs):
    def transport(body):
        names = [t["name"] for t in body["tools"]]
        assert "move_relative" in names and "submit_plan" not in names
        return {
            "status": "completed",
            "output": [
                {
                    "type": "function_call",
                    "name": "move_relative",
                    "arguments": '{"arm":"arm","direction":"up","distance":"small"}',
                }
            ],
        }

    planner = GPTPlanner("fixture", plan_mode="single", transport=transport)
    result = planner.decide("lift", *inputs[:2], [], inputs[2])
    assert result["plan"]["steps"][0]["tool"] == "move_relative"
    raw = next(e for e in inputs[2].events if e["kind"] == "model_response")
    assert raw["payload"]["calls"][0]["name"] == "move_relative"
