# Design rationale and evidence

The goal is to spend GPT decisions at useful boundaries while leaving continuous control to local tools. The current release establishes that execution interface; it does not establish superior manipulation performance.

## Where the abstraction helps

A pixel-target call expresses an observable visual choice. Calibration and current depth determine its surface position; the controller closes the loop at its own rate. This separates a model's visual error from camera/depth error and servo error. In the recorded MetaWorld run the model emitted one pixel target and the backend performed 35 ticks. The model request itself took 49.04s, so a low call count alone is not enough to claim low latency.

A plan is an ordered list of registered tools. Version 0.4 can additionally register model-written Python programs after strict AST validation and compilation into a restricted namespace: only bounded composition of existing primitives is admitted, with no imports or host I/O. Its structure is validated before movement, and an execution lock prevents two plans from concurrently owning the robot. The executor checks budgets and observes tool results. These contracts make integrations easier to inspect; they are not a certified safety layer. Drivers must bound their own blocking I/O.

The evaluator has a different responsibility from the planner. It reads the task predicate after execution and records it separately from model completion and tool success. A closed gripper is not evidence of a grasp. This distinction matters in the failed LIBERO attempt, where reaching above the selected surface did not complete the manipulation task.

## Compare execution patterns, not unsupported leaderboard claims

The following are patterns, not claims that all implementations of a model family behave alike. A VLA policy can be a tool inside this harness.

| Pattern | What a decision emits | Where intermediate motion lives | Useful when | Tradeoff |
|---|---|---|---|---|
| One model call per tool | One typed primitive | Local controller | Fresh visual feedback is needed after each step | More model round trips |
| Bounded tool plan | Several ordered primitives | Local controller plus executor | Later steps remain valid without a new image | Requires target validity and correct interruption boundaries |
| A chunked VLA policy | A learned action sequence/chunk | Policy and robot controller | Learned local manipulation behavior is available | Different training, deployment and debugging interface; no comparative result here |

The core implements the first two patterns. Versions 0.2–0.4 add model-written typed skills, bounded Python tool programs, evidence-bound memory and checkpoint-specific VLA bridges; see [RSI Lab](rsi-design.md) for their measured scope. MoveIt, SLAM, GraspNet and persistent target tracking are still not included. A policy endpoint is not a guarantee of contact or task success.

## What the first failures tell us to improve

| Observed limitation | Consequence | Candidate improvement — not yet implemented | Validation required |
|---|---|---|---|
| Pixel reference becomes stale after movement | The LIBERO batch stops at its second pixel operation | Resolve static targets into explicit snapshot handles, with validity checks and reacquisition | Moving-object and camera-motion cases; stale handles must never silently remain valid |
| Surface target is not a grasp pose | LIBERO surface approach stalled 43.07mm from target | Backend grasp-pose proposal and approach/contact controller, or a verified VLA tool | Grasp and placement tasks with independent success predicates |
| No collision planner | Cartesian servo follows a local target without obstacle reasoning | Calibrated geometry, collision checking and a planner-backed tool | Obstacle changes, clearance, failure recovery and contact-sensitive tasks |
| API timeouts and failed responses | Seven of eight simulator attempts had infrastructure errors | Provider diagnostics, explicit recovery policy and resumable execution state | Outage injection; no duplicate non-idempotent robot actions |
| Few tasks, selected examples, local renderer | No defensible generalization or benchmark conclusion | Frozen tasks, seeds, budgets, software versions and initial states | Reproducible held-out evaluation with every attempt retained |

In particular, batching alone cannot solve the stale-pixel issue. A list of pixel coordinates is not automatically a persistent spatial plan. The current implementation rejects stale references; it does not silently cache target geometry across movement.

## What would justify saying “better”

| Claim | Required controlled comparison | Report alongside it |
|---|---|---|
| Fewer GPT calls | Same model, tools, task/seed set and budgets; `single` versus `batch` | Success, failed calls, tokens, retries and total wall time |
| Better execution robustness | Same tasks with controlled tool failures, stale targets and missing depth | Recovery, aborted steps and unintended actions |
| Better task success | Same observations and evaluation protocol for the compared controllers | Per-task success, uncertainty, infrastructure failures and sample count |
| Useful stronger tools | Add grasp/planning/VLA tools one at a time | Runtime cost, model calls, contact outcomes and failure modes |
| Stronger models need fewer tools | Cross model choice with a fixed set of tool subsets | Success/cost Pareto comparison; no such experiment completed yet |

The paired offline demo already checks that changing scheduling preserves the executed path (28 ticks; four versus two deterministic planner decisions). The live MetaWorld and LIBERO recordings are different tasks and modes, so they cannot serve as a paired batching ablation.

Start with [all live attempts](live-tests/all-attempts.json), [validation status](validation.md), [tool extensions](extensions.md) and [evaluation protocol](evaluation.md). External projects such as [RPent](https://github.com/RLinf/RPent) are inspiration, not measured baselines in this release.
