# Historical v1 RSI Lab: generate, attempt, remember, verify

**The recommended development route is now [benchmark-first RSI](benchmark-first-rsi.md). This page documents the preserved v1 implementation and experiment, not the new curriculum order.**

Embodied Harness now includes an experimental **non-parametric self-improvement loop**. GPT proposes scenario configurations, operates a robot through real tools, inspects development failures, writes a memory document and composes reusable skills. Model weights remain frozen. Improvement is a hypothesis to test, not a property guaranteed by the loop.

The design is inspired by [NVIDIA ASPIRE](https://research.nvidia.com/labs/gear/aspire/) and its [open implementation](https://github.com/NVlabs/ASPIRE). ASPIRE already establishes iterative skill programming and reusable skill libraries. We do **not** claim to invent that approach, reproduce its paper, or outperform ASPIRE / RPent. Our contribution here is an inspectable small implementation with typed skills, evidence-bound memory, explicit promotion records and paired ablations.

For the next-generation exploration/absorption controller and precise implemented-versus-planned status, see [frontier evolution](frontier-evolution.md).

## What the brain can change

| Artifact | Model writes | Harness enforces | What is frozen for testing |
|---|---|---|---|
| Scenario | Native task family, MT1 instance, camera yaw, light scale, weakness hypothesis | Supported task catalog, parameter bounds, native simulator construction | Scenario manifest, initial seeds, native success predicate |
| Memory | Short observations / hypotheses with episode citations and task scope | Evidence IDs must exist in development records; retrieval is task-scoped | Exact candidate memory hash |
| Skill | 1–4 parameterized existing primitive calls | No generated Python, loops, imports or nested skills; validate before motion; stop on failure | Exact program hash and primitive API |
| VLA delegation | Instruction and bounded chunk count | Operator-selected checkpoint, embodiment/action contract, numerical checks, per-tool/global budgets | Weight SHA-256 and preprocessing contract |
| Benchmark | A collection of generated scenario specs | Freeze before held-out evaluation; no test feedback to discovery | Content-addressed manifest and evaluation protocol |

The initial scenario generator uses **MetaWorld-native layout randomization plus camera and lighting interventions**. It does not synthesize arbitrary meshes, new collision geometry, or new success predicates. Calling these six scenario families a new benchmark does not make them six new manipulation primitives.

## Two separate update loops

1. **Within an episode:** camera observation → GPT tool plan → bounded execution → new observation. Skills reduce repeated planning when their constituent actions can execute safely in sequence. Pixel targets require a current observation; a skill cannot store demonstration pixels or reuse projection after motion.
2. **Across development episodes:** generated scenario → rollout evidence → candidate memory / skills → paired development gate → accepted or rejected snapshot. A rejected candidate remains visible, and may be evaluated as an explicitly labeled experimental ablation. It is not automatically promoted.

The current gate accepts a *bundle*, not a causal claim about each skill. It requires no paired development regression and either more successes or equal nonzero successes with at least 10% fewer calls. One validation seed per family is deliberately labeled a small gate. The final four-arm test is what separates memory and skill effects.

## Experimental protocol

`python -m embodied_harness.rsi.experiment --output runs/my-rsi --model MODEL --base-url URL`

Set `OPENAI_API_KEY` through your secret store. The command never prints it. Install `.[metaworld]` first. Native rendering must work on the host.

- Two cycles, three previously unused task families proposed per cycle.
- Discovery seed 11. Validation seed 31. Held-out seeds 101 and 102.
- Four held-out arms: baseline, memory only, skills only, memory + skills.
- Identical physical scenario / seed and budgets across arms: 8 GPT decisions, 400 control ticks.
- 72 planned episodes, at most 576 episode decision requests. Initially four designer calls; contract repairs and explicitly retried infrastructure failures are separately recorded, with an amended budget when needed.
- Native final-state success predicate. All infrastructure failures remain in the denominator. No success-oracle feedback in observations or early stopping.
- The final candidate and the last development-approved snapshot are exported separately. Test results never choose the next skill or memory revision.

This tests transfer to **unseen scene seeds within selected task families**. It does not establish unseen-family generalization, long-horizon autonomy, or weight-level recursive improvement. Two seeds per family are not enough for a strong scientific claim. Successes, failures, paired wins/losses, request counts, token usage and uncertainty are published together.

Runs are resumable only when recorded inputs match. An incomplete episode directory is not silently rerun. `--retry-designer --designer-timeout 300` explicitly permits a preserved failed designer request to be tried again; it does not retry robot episodes. Model-generated invalid programs are rejected. A separate typed-contract repair is retained, rather than silently rewriting model output by hand.

## π0.5 is a callable specialist

[OpenPI](https://github.com/Physical-Intelligence/openpi) exposes policies that map visual/proprioceptive observations to action chunks. A checkpoint must match the embodiment, preprocessing and action representation. Installing a generic π0.5 base model is not enough to control an arbitrary simulator.

Our first bridge targets an **existing user-trained π0.5 checkpoint with RoboTwin ALOHA qpos14 actions**, not the official π0.5-LIBERO checkpoint. `run_vla(instruction, chunks)` executes at most 10 actions per chunk and 8 chunks per call, reobserves between chunks, and returns control to GPT. The endpoint is selected by the operator, not by generated code. The trace includes checkpoint identity, predicted/executed horizons, action vectors and actual camera observations. Gripper clipping is recorded. Tool completion does not claim task success.

`examples/serve_policy_bridge.py --factory my_policy:create` starts a loopback policy service. Supply an object with `metadata` and `infer(message)`; metadata must declare `robotwin_aloha_qpos14_v1` and a checkpoint SHA. Register it with `--tools-factory embodied_harness.vla:configured_policy`, `VLA_ENDPOINT`, and `VLA_CHECKPOINT_SHA256`.

The public-checkpoint route is `examples/openpi_libero_policy.py:create`, using the official `pi05_libero` checkpoint and `libero_franka_osc7_v1`. Run it in an OpenPI environment:

```bash
PYTHONPATH=examples python examples/serve_policy_bridge.py \
  --factory openpi_libero_policy:create
```

Its metadata identifies a SHA-256 fingerprint of the resolved checkpoint tree. The LIBERO bridge extracts only RGB and robot proprioception, follows OpenPI's native-image rotation, and executes normalized 7D OSC actions. We have tested that sensor/action boundary with a **non-model fixture**; that check is not a π0.5-LIBERO success rate. The actual checkpoint-backed robot experiments in this release use the separately identified user-trained RoboTwin checkpoint. Its training overlap is unknown, so those demonstrations do not establish generalization.

`DirectoryPlanner` permits a separate GPT decision broker while the robot worker holds no API key. It exchanges nonce-bound camera requests and validated decisions. `examples/run_brokered_episode.py` demonstrates the robot side. The transfer channel must be operated privately, such as SSH. This is a cooperative simulation controller, not a hardware safety system.

## Inspection and extension

`python scripts/export_rsi.py runs/my-rsi docs/rsi/my-rsi` renders the experiment dashboard. It shows two-view recorded replay, exact model calls, skill expansion, geometry, memory revisions, source episodes, rejection decisions and all episode results. Videos are explicitly labeled **sampled event replays**, not real-time camera footage.

Runtime primitives and skill composition are environment-independent. The first automated discovery protocol is MetaWorld-specific; adapting task generation to LIBERO, RoboCasa or RoboTwin requires supported scene constructors and independently defined evaluators. Existing adapters are not evidence that this RSI experiment ran on all four suites.

Future experiments should expand seeds and task families, compare with stronger baselines under matched budgets, validate memory expiration and retrieval, and test VLA delegation on checkpoints whose training overlap is known. We publish the present evidence before making those claims.
