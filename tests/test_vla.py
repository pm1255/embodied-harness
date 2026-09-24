import base64

import numpy as np
import pytest

from embodied_harness.vla import PolicyEndpoint, register_policy
from embodied_harness.runtime import Registry


def test_endpoint_identity_and_embodiment_are_operator_bound(monkeypatch):
    monkeypatch.setattr(PolicyEndpoint, 'request', lambda *_: {
        'checkpoint_sha256': 'abc', 'contract':'robotwin_aloha_qpos14_v1'})
    with pytest.raises(ValueError):
        PolicyEndpoint('http://some-robot:1234', 'abc')
    with pytest.raises(ValueError):
        PolicyEndpoint('http://127.0.0.1:8907', 'wrong')
    policy = PolicyEndpoint('http://127.0.0.1:8907', 'abc')
    wrong_env = type('Env', (), {'name': 'metaworld'})()
    with pytest.raises(ValueError):
        register_policy(wrong_env, Registry(), policy)


def test_vla_rejects_bad_chunk_before_robot_control(monkeypatch):
    metadata = {'checkpoint_sha256':'abc', 'contract':'robotwin_aloha_qpos14_v1'}
    monkeypatch.setattr(PolicyEndpoint, 'request', lambda *_: metadata)
    policy = PolicyEndpoint('http://127.0.0.1:8907', 'abc')
    class Native:
        def get_obs(self):
            return {'observation':{c:{'rgb':np.zeros((8,8,3),dtype=np.uint8)} for c in
                                   ['head_camera','left_camera','right_camera']},
                    'joint_action':{'vector':[0]*14}}
    env = type('Env', (), {'env':Native(), 'task':'click_bell', 'seed':0, 'name':'robotwin'})()
    for bad in ([[float('nan')]*14], [[0]*7], [[9]*14], []):
        policy.request = lambda *_, data=bad: {'actions':data}
        with pytest.raises(ValueError):
            policy.infer(env, 'Press bell')
    def valid(route, message):
        assert route == '/infer'
        assert len(base64.b64decode(message['images']['0']['data'])) == 8*8*3
        assert set(message)=={'images','state','instruction','query','case_id','seed'}
        return {'actions':[[0]*14]*10}
    policy.request = valid
    assert policy.infer(env, 'Press bell').shape == (10,14)
