# Benchmark execution status — 2026-09-24

| Environment | Actual coverage | Result | What it does not establish |
|---|---|---|---|
| MetaWorld 3.1.1 | 50 task types, seed 0 / MT1 instance 0 | 50/50 integration checks passed | Official MT50 success or generalization |
| LIBERO, robosuite 1.4.0 / MuJoCo 2.3.7 | 130 tasks across all five suites, official initial state 0 | 129/130 motion checks passed; task 85 in LIBERO-90 hit unstable physics | Official all-state policy evaluation |
| RoboCasa 365 | Three actual GPU cases, three asset-setup attempts | 0/3 on each attempt: missing Lightwheel objects after cabinets/registries were restored | Runtime or GPT success |
| RoboTwin 2 | lift_pot, click_bell, move_can_pot; one RTX 4090 | **3/3 integration checks passed**, native source factory | Task solving or full benchmark coverage |

[20-case GPT pilot with all outcomes](basic-20/README.md) · [MetaWorld interface records](metaworld-integration.json) · [LIBERO interface records](libero-integration.json) · [frozen manifests and commands](../../benchmarks/README.md).

## LIBERO-90 task 85 diagnostic

The first sweep's motion tool exhausted 120 ticks with a 57.9mm target error. Its process exited normally; the report was re-audited against each `tool_end` and this case is **not** a pass. Repeating the case reproduced the failure. A separate native LIBERO control run, without this harness, also triggered `Nan, Inf or huge value in QACC at DOF 10` at simulation time 0.53s. The simulation clock dropped from 0.50s to 0.02s under zero-motion actions. [Native diagnostic](libero85-native-diagnostic.json).

The adapter now detects simulation clock rollback and nonfinite physics and stops with an infrastructure error. This makes failures visible; it does not fix this initial state's physics. We have not changed the simulator timestep, skipped the state or relabeled the repeat as a success.

## Remaining asset dependency

RoboCasa is not yet validated. Supply the complete compatible Lightwheel object package in the isolated asset directory, then rerun the frozen three-case manifest. Do not remove scene objects or replace them with dummy meshes to make the check pass. Failed runs have no fabricated camera video.

## Camera correction

The MetaWorld `corner` and `corner2` rasters were upside down. New runs rotate RGB, depth, intrinsics and the optical frame together by 180 degrees; a pixel-ray invariance test checks that world coordinates remain unchanged. Old GIFs/viewers rotate only their presentation and keep recorded model JSON in the original coordinates, explicitly labeled. LIBERO views keep their original correct sensor orientation.

## Reproduction and limitations

The two completed interface sweeps ran on macOS in separate actual simulator runtimes. The GPT pilot uses an AiXor endpoint reporting `gpt-6-sol`; upstream model identity is not independently verified. RoboCasa/RoboTwin setup was attempted on the authorized evaluation server in new isolated environments. Three bounded single-RTX-4090 jobs then tested existing user-owned runtime assets. No old runtime or asset directory was modified. RoboTwin passed; RoboCasa exposed missing fixture models, then fixture registry metadata, then Lightwheel objects. The first two gaps were repaired in a new project-owned source/asset directory. The remaining `objects/lightwheel/paper_towel_holder/PaperTowelHolder006/model.xml` is missing, and the official Lightwheel archive returned HTTP 404. See [all GPU attempts and RoboTwin replays](gpu-smokes/README.md). Mock tests, an adapter file, and package installation do not count as an environment passing. All three GPU jobs have ended; no evaluation GPU job remains queued or running.

Three model decisions per pilot task are a deliberately short diagnostic budget, especially restrictive for multi-stage pick-and-place. Compare neither this pilot's success rate with RPent's official published results nor the earlier two selected examples against each other as a single-vs-batch ablation. [Comparison requirements](../rpent-comparison.md).
