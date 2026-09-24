# Simulator adapters

The core and viewer are simulator-independent. Keep incompatible simulator versions in separate environments. Do not install every robotics dependency into one environment.

## MetaWorld 3.x

```bash
pip install -e '.[metaworld]'
embodied-harness smoke --env metaworld --config examples/metaworld.json
```

The adapter uses `metaworld.MT1`, a fixed task index, Gymnasium `step`, and MuJoCo's RGB/depth renderer. It exposes the end-effector position and robot joints, not the privileged MetaWorld observation vector. Depth renderer outputs are meters. The native `corner` / `corner2` camera rasters are rotated 180° together with depth, intrinsics and the optical coordinate frame, preserving the world ray for every pixel. Task outcome comes from the last `info['success']`, accessed only by the final evaluator. The fixed task-index protocol is a smoke/evaluation building block, not the complete official MT1 benchmark protocol.

On a Linux GPU server set `MUJOCO_GL=egl` before Python starts. On macOS a working graphical session is needed. A renderer initialization error is an infrastructure failure.

## LIBERO

Use the official [LIBERO installation](https://github.com/Lifelong-Robot-Learning/LIBERO) and configure its assets/config directory. In the same environment:

```bash
pip install -e '.[sim]'
embodied-harness smoke --env libero --config examples/libero.json
```

The adapter creates `OffScreenRenderEnv`, seeds and resets it, renders two current RGB-D cameras and inverts the delta OSC controller's configured scaling. It preserves orientation and only supports one Panda arm. Set `init_state_index` in JSON to load an official benchmark initial state and apply ten zero-motion settling steps; omit it for a randomized reset. No demonstration actions are replayed and the initial-state vector is never sent to the model. The 20-task pilot uses index 0, not all evaluation states. An initial-state subset is still not a full official benchmark score.

## RoboCasa

Install the official [RoboCasa stack and assets](https://github.com/robocasa/robocasa), then install this package with `pip install -e .`. Keep the upstream runtime NumPy version: the convenience `sim` extra is intended for the older LIBERO environment, not RoboCasa 365 with NumPy 2.

```bash
embodied-harness smoke --env robocasa --config examples/robocasa.json
```

The default constructor calls `robocasa.utils.env_utils.create_env`. Only a robot with fixed-impedance delta OSC pose control is accepted. World-space displacement is rotated into the controller reference frame when the arm expects base-frame commands. Mobile-base and other action channels are zeroed by the robot's named action-vector builder. This does not provide navigation or whole-body control. If your default controller is whole-body IK, supply a factory configured for a compatible controller:

```json
{"task":"PickPlaceCounterToCabinet","factory":"my_robocasa_setup:make_environment","size":256}
```

The factory receives `seed`, `task`, `size` and returns a configured robosuite environment with cameras `robot0_agentview_left` and `robot0_eye_in_hand`. Rejecting an unsupported controller is intentional; do not remove the mode check to make a demo run.

## RoboTwin 2

Install the official [RoboTwin repository, assets and embodiment configuration](https://github.com/RoboTwin-Platform/RoboTwin). This release does not invent a universal task initializer across RoboTwin versions. Supply an operator-owned factory that performs your version's documented evaluation setup and returns a fresh `TASK_ENV`:

```python
def make_environment(*, seed: int, task: str, size: int):
    # Initialize TASK_ENV with the official evaluator's task configuration.
    # Enable data_type.rgb and data_type.endpose. Do not execute play_once().
    # Set evaluator counters/step limits required by your installed version.
    return initialized_task_environment
```

```bash
embodied-harness smoke --env robotwin --config examples/robotwin.json
```

The example points to our **experimental, wheel-runtime-unvalidated** `embodied_harness.adapters.robotwin_factory:make_environment`, targeting `rlinf-robotwin-runtime==0.1.1` with the `mplib` backend. This distribution is maintained by RLinf/RoboTwin; this wheel path is not runtime-validated here. A separate `make_source_environment` factory, selected via `ROBOTWIN_SOURCE_ROOT`, passed three actual GPU smoke cases with an existing upstream source deployment; see [evidence](benchmarks/gpu-smokes/README.md). Install the runtime in its own Python 3.10 environment, run `robotwin-download-assets --output /path/to/assets-root`, and set `ROBOTWIN_ASSETS_ROOT`. You may replace the factory for another RoboTwin version. Some tasks require additional evaluator initialization; a generic factory does not establish all-task support. The bridge reads `get_obs()`, sends `take_action(..., action_type='ee')`, and closes through `close_env()`. It preserves each arm's native pose quaternion and commands only the selected arm. Execution is sequential, not synchronized bimanual skill execution.

Pixel projection is intentionally unavailable for RoboTwin until its camera units and extrinsics are independently validated. No ground-truth object poses, `grasp_actor`, contact annotations, or scripted task demonstrations are used.

## Adding another adapter

Implement `protocol.Environment`: reset/observe, current TCP position, optional calibrated surface projection, bounded servo, stop, evaluator-only success and close. Expose only implemented capabilities. `facts` should contain independently measured booleans; leave a fact absent when unknown. A model cannot make an unknown fact true by claiming it.

Run the contract tests, then record a real reset→capture→motion→capture→close smoke trace. Document controller representation, units, image orientation, simulator version and unsupported features. A fake backend test is not a replacement for this integration check.
