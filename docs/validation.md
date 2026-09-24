# Validation status — 2026-09-24

This file distinguishes implemented code, contract tests, simulator execution and model performance. No success-rate or model-generalization claim is made.

| Component | Evidence | Remaining boundary |
|---|---|---|
| Runtime / offline demo | Unit tests, successful and injected-failure runs | Synthetic kinematic scene; no physics or GPT |
| GPT Responses adapter | Request/response contract tests using a fake transport | Live API run not performed; no API credential configured in validation environment |
| Trace viewer | Browser inspection; tool selection and observation synchronization exercised | Sampled observations, not full-rate video |
| MetaWorld | Actual reset, two RGB-D cameras, local servo and final evaluator run | No GPT task-solving evaluation |
| LIBERO | Actual reset, two RGB-D cameras, local servo and final evaluator run | No GPT task-solving evaluation or official init-state benchmark |
| RoboCasa | Constructor and named-controller integration implemented | Assets/controller configuration not tested in a real RoboCasa run |
| RoboTwin | Task-factory bridge, camera/pose extraction and native EE action path implemented | Requires operator task factory; not tested in an asset-backed RoboTwin run |
| Real robots | No adapter shipped | Not validated |

## Actual simulator smoke evidence

[Machine-readable results](smoke-results.json) contain the summaries and tool results. Both runs used a deterministic 2cm upward motion, not a model-generated task policy.

| Environment | Actual control ticks | Final target error | Task predicate |
|---|---:|---:|---|
| MetaWorld reach-v3 | 4 | 6.76mm | false, as expected for an interface smoke test |
| LIBERO spatial/task 0 | 4 | 11.55mm | false, as expected for an interface smoke test |

Runtime tolerance was 12mm. These measurements show interface execution, not precision grasping. MetaWorld emitted a macOS OpenGL depth-precision warning; validate depth accuracy again on the deployment renderer before using surface projection for manipulation.

Validation environments:

- macOS arm64, Python 3.10.20.
- MetaWorld 3.1.1, MuJoCo 3.3.0, NumPy 1.26.4.
- LIBERO source checkout, robosuite 1.4.0, MuJoCo 2.3.7, NumPy 1.22.4, PyTorch 2.6.0. The LIBERO source was already installed locally; its Git revision was not available, so this is not a version-pinned benchmark reproduction claim.

## Reproduce core checks

```bash
pip install -e '.[dev,sim]'
ruff check .
pytest -q
embodied-harness demo --out runs/batch
embodied-harness demo --per-tool --out runs/per-tool
embodied-harness demo --fault-after 12 --out runs/failure
```

The successful fixtures have identical final TCP positions and 28 control ticks. Batching reduces deterministic planner decisions from four to two, including final status. Both have zero GPT API calls. The injected fault stops remaining actions and reports a blocked outcome.

Sample portable traces: [successful offline fixture](demo/index.html), [injected failure](demo-failure/index.html). Serve this repository locally or open the HTML files after cloning. GitHub's source viewer does not execute HTML.
