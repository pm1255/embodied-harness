"""Credential-free robot worker protocol for a separately operated decision broker.

The directory is private to the operator (SSH transport in examples). Requests and
responses are nonce-bound; observations never contain privileged task state.
"""
from __future__ import annotations

import json
from pathlib import Path
import time
import uuid

from jsonschema import ValidationError

from .rsi.core import write_json


class DirectoryPlanner:
    def __init__(self, directory, model, timeout_s=180, context=None):
        self.root = Path(directory)
        self.root.mkdir(parents=True, exist_ok=True)
        self.model, self.timeout = model, timeout_s
        self.calls = self.input_tokens = self.output_tokens = 0
        self.provider_host = "local_decision_broker"
        self.api_mode, self.stream, self.plan_mode = "responses", True, "batch"
        self.context = context or {}

    def decide(self, task, observation, registry, history, trace):
        nonce = uuid.uuid4().hex
        data = {"nonce": nonce, "task": task, "observation": observation.to_dict(),
                "tools": registry.descriptions(), "history": history[-4:],
                "experience": self.context}
        temporary = self.root / (nonce + ".tmp")
        write_json(temporary, data)
        temporary.replace(self.root / "request.json")
        response_path = self.root / (nonce + ".response.json")
        started = time.monotonic()
        while not response_path.exists():
            if time.monotonic() - started > self.timeout:
                raise TimeoutError("Decision broker deadline exceeded")
            time.sleep(.2)
        response = json.loads(response_path.read_text(encoding="utf-8"))
        if response["nonce"] != nonce:
            raise ValueError("Decision broker nonce mismatch")
        for kind, payload in response["events"]:
            trace.emit(kind, **payload)
        self.calls += response["calls"]
        self.input_tokens += response["input_tokens"]
        self.output_tokens += response["output_tokens"]
        if response.get("error"):
            if response.get("error_kind") == "ValidationError":
                raise ValidationError(response.get("validation_message") or response["error"])
            raise RuntimeError("Decision broker: " + response["error"])
        decision = response["decision"]
        if decision["kind"] == "plan":
            registry.validate(decision["plan"])
        elif decision["kind"] == "finish":
            if decision.get("outcome") not in ("completed", "blocked") or not isinstance(decision.get("summary"), str):
                raise ValueError("Invalid finish result")
        else:
            raise ValueError("Invalid broker decision kind")
        return decision
