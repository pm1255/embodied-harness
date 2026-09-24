from types import SimpleNamespace
import numpy as np
import pytest
from embodied_harness.adapters.robosuite import RobosuiteEnvironment


@pytest.mark.parametrize("unstable", [False, True])
def test_mobile_base_delta_and_physics_reset_guard(tmp_path, unstable):
    adapter = RobosuiteEnvironment(tmp_path)
    R = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]])
    adapter.controller = SimpleNamespace(
        input_ref_frame="base",
        origin_ori=R,
        ref_pos=np.array([2.0, 3.0, 1.0]),
        output_min=np.full(6, -0.05),
        output_max=np.full(6, 0.05),
        input_min=np.full(6, -1.0),
        input_max=np.full(6, 1.0),
        update=lambda **k: None,
    )
    commands = []
    data = SimpleNamespace(time=1.0, qpos=np.zeros(7), qvel=np.zeros(7))

    def step(action):
        commands.append(action)
        data.time = 0.02 if unstable else 1.05
        return None, 0, False, {}

    adapter.env = SimpleNamespace(step=step, sim=SimpleNamespace(data=data))
    adapter.arm_key = None
    adapter.done = False
    adapter.tick = 0
    if unstable:
        with pytest.raises(RuntimeError, match="simulation_clock_reset"):
            adapter.servo([2.01, 3.0, 1.0], "open")
        assert adapter.tick == 0
        return
    adapter.servo([2.01, 3.0, 1.0], "open")
    np.testing.assert_allclose(commands[0][:3], [0, -0.2, 0], atol=1e-12)
    np.testing.assert_allclose(adapter.ee_position(), [2.0, 3.0, 1.0])
