from copy import deepcopy

import pytest

from embodied_harness.rsi.core import (digest, install_skills, promotion_gate, seal,
                                        validate_skill, memory_for)
from embodied_harness.tools import make_registry


class Env:
    capabilities = {"arms": ["arm"], "cameras": ["front"], "cartesian_servo": True,
                    "surface_projection": True}


def pixel_skill():
    return {"name": "skill_approach", "description": "Approach then descend", "steps": [
        {"tool": "move_to_pixel", "arguments": {"arm": "arm", "camera": "front",
         "pixel": {"$arg": "pixel"}, "observation_id": {"$arg": "observation_id"}, "approach": "above"}},
        {"tool": "move_relative", "arguments": {"arm": "arm", "direction": "down", "distance": "small"}},
    ]}


def test_skill_fresh_pixel_schema_and_no_nested_code():
    registry = make_registry(Env())
    skill = pixel_skill()
    schema = validate_skill(skill, registry)
    assert schema["properties"]["pixel"]["items"]["type"] == "integer"
    for field, value in (("pixel", [42, 21]), ("observation_id", "old-frame")):
        bad = deepcopy(skill)
        bad["steps"][0]["arguments"][field] = value
        with pytest.raises(ValueError):
            validate_skill(bad, registry)
    bad = deepcopy(skill)
    bad["steps"].reverse()
    with pytest.raises(ValueError):
        validate_skill(bad, registry)
    bad["steps"][0]["tool"] = "exec_python"
    with pytest.raises(ValueError):
        validate_skill(bad, registry)
    install_skills(registry, [skill])
    assert "skill_approach" in registry.tools


def test_freeze_rejects_mutation(tmp_path):
    seal(tmp_path / "frozen.json", {"seed": 101})
    seal(tmp_path / "frozen.json", {"seed": 101})
    with pytest.raises(ValueError):
        seal(tmp_path / "frozen.json", {"seed": 102})
    assert digest({"b": 2, "a": 1}) == digest({"a": 1, "b": 2})


def test_no_heldout_skill_selection_and_no_failure_masking():
    row = {"split": "validation", "success": False, "api_calls": 8, "status": "agent_finished"}
    base = {"a": row}
    candidate = {"a": {**row, "success": True}}
    assert promotion_gate(base, candidate)["accepted"]
    assert not promotion_gate(candidate, base)["accepted"]
    assert not promotion_gate(base, {"a": {**row, "api_calls": 1}})["accepted"]
    with pytest.raises(ValueError):
        promotion_gate(base, {"a": {**row, "split": "heldout"}})
    with pytest.raises(ValueError):
        promotion_gate(base, {})
    assert not promotion_gate(base, {"a": {**row, "success": True,
                                           "status": "infrastructure_error"}})["accepted"]


def test_memory_retrieval_is_task_scoped():
    entries = [{"tasks": ["push-v3"]}, {"tasks": ["*"]}]
    assert memory_for(entries, "reach-v3") == entries[1:]


def test_composed_skill_stops_on_failure_and_obeys_global_budget(tmp_path):
    from embodied_harness.adapters.toy import ToyEnvironment
    from embodied_harness.cli import step
    from embodied_harness.runtime import Executor
    from embodied_harness.trace import Trace
    env = ToyEnvironment(tmp_path/'camera')
    env.reset(0)
    env.fault_after = 2
    registry = make_registry(env)
    skill = {'name': 'skill_move_close', 'description': 'test', 'steps': [
        {'tool': 'move_relative', 'arguments': {'arm': 'arm', 'direction': 'up', 'distance': 'large'}},
        {'tool': 'set_gripper', 'arguments': {'arm': 'arm', 'state': 'closed'}}]}
    install_skills(registry, [skill])
    trace = Trace(tmp_path/'run')
    executor = Executor(env, registry, trace, max_control_ticks=3)
    report = executor.execute({'steps': [step('s', skill['name'], {})]})
    assert report['status'] == 'needs_decision'
    assert env.gripper == 'open'
    assert env.tick <= 3
    trace.file.close()


def test_reflection_schema_rejects_fake_evidence_and_stringified_program():
    from jsonschema import validate, ValidationError
    from embodied_harness.rsi.experiment import reflection_schema
    schema = reflection_schema(make_registry(Env()), {'episode/1'}, {'push-v3'})
    valid = {'memory': [{'title': 'Contact', 'tasks': ['push-v3'], 'lesson': 'Check contact',
                          'evidence': ['episode/1']}], 'skills': []}
    validate(valid, schema)
    fake = deepcopy(valid)
    fake['memory'][0]['evidence'] = ['episode/1: claimed success']
    with pytest.raises(ValidationError):
        validate(fake, schema)
    fake = deepcopy(valid)
    fake['skills'] = [{'name':'skill_push', 'description':'test', 'tasks':['push-v3'],
                      'evidence':['episode/1'], 'steps_json':'[]'}]
    with pytest.raises(ValidationError):
        validate(fake, schema)


def test_broker_rejects_nonce_mismatch_before_exposing_decision(tmp_path, monkeypatch):
    import json
    from embodied_harness.broker import DirectoryPlanner
    from embodied_harness.protocol import Observation
    import embodied_harness.broker as broker
    monkeypatch.setattr(broker.uuid, 'uuid4', lambda: type('ID', (), {'hex':'fixed'})())
    (tmp_path/'fixed.response.json').write_text(json.dumps({'nonce':'stale'}))
    planner = DirectoryPlanner(tmp_path, 'test')
    with pytest.raises(ValueError, match='nonce'):
        planner.decide('fixture', Observation('o','e',0,[],{}), make_registry(Env()), [], None)
    assert planner.calls == 0
