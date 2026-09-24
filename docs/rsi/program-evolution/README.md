# Model-written tools, memory and skills: measured v0.4 pilot

[Interactive evolution viewer](https://pm1255.github.io/embodied-harness/rsi/program-evolution/) · [Baseline and engineering history](../../baseline-and-evolution.md)

## Result

The third frozen revision passed its development gate and improved the four-task held-out outcome from **3/4 to 4/4**, with **19 to 10 GPT calls**. The first two revisions failed their development gates and are preserved. This is a small in-domain pilot, not full LIBERO / LIBERO-PRO mastery, a matched RPent comparison, or evidence of arbitrary self-modification.

| Revision | Split | Arm | Native successes | GPT calls | Input / output tokens | Control ticks | Observed seconds |
|---|---|---|---|---:|---:|---:|---:|
| 1 | validation | baseline | 4/4 | 15 | 30,347 / 940 | 554 | 247.9 |
| 1 | validation | candidate | 4/4 | 14 | 40,572 / 830 | 611 | 232.6 |
| 1 | heldout | baseline | 3/4 | 19 | 39,685 / 2,231 | 590 | 345.3 |
| 1 | heldout | candidate | 4/4 | 20 | 59,586 / 1,328 | 629 | 359.0 |
| 2 | validation | baseline | 4/4 | 16 | 32,841 / 967 | 585 | 281.1 |
| 2 | validation | candidate | 4/4 | 16 | 47,397 / 1,109 | 685 | 285.6 |
| 2 | heldout | baseline | 4/4 | 18 | 37,415 / 1,716 | 630 | 330.2 |
| 2 | heldout | candidate | 4/4 | 17 | 50,649 / 1,239 | 697 | 307.4 |
| 3 | validation | baseline | 3/4 | 22 | 47,516 / 3,389 | 792 | 457.1 |
| 3 | validation | candidate | 4/4 | 11 | 33,238 / 641 | 615 | 206.8 |
| 3 | heldout | baseline | 3/4 | 19 | 39,271 / 1,147 | 616 | 293.5 |
| 3 | heldout | candidate | 4/4 | 10 | 29,987 / 594 | 703 | 206.0 |

## What actually changed

- Revision 1: GPT wrote `program_bounded_full_goal_delegation`, plus evidence-citing memory and a skill, initially for opening the drawer. The program can make eight `run_vla` calls, each with eight newly inferred chunks, executing five actions per chunk: at most 320 ticks before returning to GPT. Native success interrupts every control tick. This is bounded Python that is AST-validated, compiled into a restricted namespace, and connected to an existing primitive API, not arbitrary host execution.
- Revision 2: GPT retained the program body and changed memory, skill and tool description to include the observed Spatial bowl placement.
- Revision 3: GPT again retained the program body and expanded stated applicability to the observed soup placement. The prompt changes globally; improvements on another task cannot be causally attributed to this route alone.
- The 31 Python runtime modules were identical across the three rounds. Model weights, evaluator, geometric primitives and per-episode budgets did not change. Tool registration limits were operator-fixed.
- One initial proposal failed schema validation because its tool name lacked the required prefix; it consumed an API request but never executed. One worker startup failed on archive metadata before any robot episode; that was an engineering repair, not model evolution.

All four proposal API requests, including the schema-rejected one, used **70,614 input and 6,936 output tokens** in addition to the robot execution costs above. Those costs must be amortized; fewer execution calls alone do not prove lower total experiment cost. The broker/worker audits for [round 1](round-1/broker-cost-audit.json), [round 2](round-2/broker-cost-audit.json) and [round 3](broker-cost-audit.json) reconcile all 68, 67 and 62 execution requests respectively, with no late unacknowledged requests or missing usage.

## Selection, retention and blinding

Each revision used four original task-0 families: Spatial, Object, Goal, Long. Round 1 used states 1/2; round 2 states 3/4; round 3 states 5/6, respectively development/final held-out. All arms used the same initial-state hashes, GPT model/effort, checkpoint and 24-decision / 960-control-tick budget. Every comparison keeps failures and infrastructure errors in the denominator; these 48 episodes had no infrastructure-error outcomes.

The gate requires complete evidence, matched states, unchanged source/settings, no task regression, and more successes or equal positive successes with more than 10% fewer calls. The program must actually execute in two successful new instances. Gates are evaluated from native terminal events and traces. They do not use the model's own completion claim.

Round 1 retained 4/4 but saved only 6.7% of calls and had one successful program-use instance. Its conditional coverage-only supplement was **not triggered**, because efficiency also failed. Round 2 had two program-use successes but no aggregate call reduction. Both therefore remained rejected. Their held-out improvements did not retroactively change selection.

The third gate was recomputed locally from all eight development traces and recorded before held-out outcomes were opened. See [selection record](selection.json), immutable event histories in each `data.json`, and the published source/proposal bundle. No held-out outcomes or frames entered successor proposals.

## Larger original-task confirmation

The [eight-task protocol](../../../benchmarks/libero-program-eight-task-confirmation.json) was published in commit `b01705c` before third-round selection and before any repair held-out outcomes were viewed. Passing the third development gate triggered a test of the **same frozen candidate**, task IDs 0 and 1 in each of the four suites, states 7/8, 32 paired episodes. It completed: development 1/8 → 8/8 (82 → 8 GPT calls), held-out 0/8 → 6/8 (64 → 17). Eight baseline episodes and one candidate episode ended with interface errors. Four baseline errors were overlong VLA instructions, one lacked a complete tool call, one was a TLS transport error, and two were broker deadlines; the candidate had one broker deadline. The other candidate failure exhausted 960 control ticks on the two-object basket task. These are end-to-end outcomes, not clean evidence of a GPT ability ceiling.

The wider development gate rejected promotion because three baseline development episodes violated the interface-integrity condition. The [scope decision](scope-review.json) was sealed before opening this scope’s held-out outcomes. The previous four-task activation is retained; the eight-task scope is not accepted. The [cost audit](confirmation/broker-cost-audit.json) reconciles all 171 recorded execution attempts with no unacknowledged late attempts. Two attempts lack token usage; 440,945 input and 75,231 output tokens are known totals, not a complete billing claim.


**Strong execution reference, same eight tasks × two states:**

| Arm | Native success | Recorded GPT calls | Interface-error episodes |
|---|---:|---:|---:|
| Independent π0.5 | 15/16 | 0 | 0 |
| Original GPT + tools | 1/16 | 146 | 8 |
| Frozen revision 3 + tools | 14/16 | 25 | 1 |

[Inspect all 48 matched rollouts](https://pm1255.github.io/embodied-harness/rsi/program-evolution/matched-reference/). Revision 3 **does not beat the strong VLA reference**. Its long-task failure is also a policy-only failure; its other failure is a broker deadline. Improvement over a fragile orchestration baseline is not evidence of a new manipulation capability. The supplementary reference was frozen before examining the wider outcomes and does not change the original selection rules.

## Separate server integration check

After the controlled experiments, the same frozen third bundle ran entirely through a Linux CPU decision broker and a single GPU simulation worker. The [separate two-task protocol](../../../benchmarks/libero-server-broker-smoke.json) used state 9, six decisions and 960 control ticks per task, with explicit schema feedback enabled. Bowl placement succeeded with one GPT call; the cream-cheese-and-butter task exhausted six decisions without native success. All seven requests returned; no parameter rejection occurred, so the schema-recovery path has unit-test coverage but was not triggered in these robot runs. This is **1/2**, not a new model revision, matched speedup or evidence of a capability gain. [Both dual-camera replays](https://pm1255.github.io/embodied-harness/rsi/program-evolution/server-smoke/) preserve that distinction.

The full v0.4 collection contains 112 comparative episodes (16 initial baseline, 48 repair, 32 scope, 16 supplementary policy) plus two separate engineering episodes. Earlier startup/preflight failures remain in the archives and are not counted as robot evolution episodes.

## Interpretation and remaining limits

A [post-hoc instruction audit](instruction-audit.json) found that baseline VLA invocations preserved the exact original goal in 0/32, 0/33 and 0/36 calls across rounds 1–3; candidate invocations did so in 38/38, 40/40 and 37/37. Counts include inner primitive entries, not GPT requests. On the eight-task confirmation this was 0/89 versus 80/83; the candidate rewrote the last three direct VLA calls in its failed long-task episode. This audit was not fed back to proposal generation. Instruction wording and delegation duration changed together, so reduced interference with the in-domain VLA is a plausible explanation, not an isolated causal result.

The useful result is a concrete model-written control-flow tool and evidence-backed changes to when GPT uses it. Less frequent GPT dispatch still leaves VLA reobserving between chunks. This is not one stale trajectory played open-loop. The third held-out run needed more control ticks, despite fewer calls/tokens and less observed time.

The SFT checkpoint is `RLinf/RLinf-Pi05-LIBERO-130-fullshot-SFT`; original LIBERO tasks overlap its training domain. “Held-out” means withheld from this repair loop, not proven unseen by the checkpoint. The provider requested/reported `gpt-6-astra` at AiXor; upstream model identity is not independently verified.

The original repair gate had four tasks with one state per split, giving wide uncertainty intervals. Baseline precedes candidate, order is not counterbalanced, and warm-up and transport contribute to wall time. Memory, skill and tool are changed together, without component ablations. There is no stronger-versus-weaker brain comparison, no unrestricted harness-source mutation, and no harder-scene gain in this experiment. **Task difficulty remains unchanged.**

The next capability experiment should start from a reliable full-goal VLA default, keeping GPT for observed exceptions. Re-test interface failures as a new, labeled engineering cohort; never overwrite the original failures. Then use development-only examples where the fixed specialist actually fails to motivate model-authored decomposition or tools, with fresh original-task evaluation before any difficulty increase. Task-generation infrastructure and old scenario experiments exist, but this repair cohort generated no new task and demonstrated no harder-environment gain.

The original benchmark-first rules still apply: fix failures and reuse suitable existing practice; create missing practice only after an audited gap; unlock harder tasks after the selected original scope is stably mastered. A failed proposal changes the next hypothesis. A fixed experiment budget ending is not a model capability boundary.

## Inspect or reproduce

- [Revision 1: all 16 episodes](https://pm1255.github.io/embodied-harness/rsi/program-evolution/round-1/)
- [Revision 2: all 16 episodes](https://pm1255.github.io/embodied-harness/rsi/program-evolution/round-2/)
- [Revision 3: all 16 episodes and cross-round tables](https://pm1255.github.io/embodied-harness/rsi/program-evolution/)
- [Execution and controller commands](../../baseline-and-evolution.md#repeat-the-bounded-repair-loop)
- [Full rollout archives, proposals and immutable executed source snapshots](https://github.com/pm1255/embodied-harness/releases/tag/v0.4.0), with [checksums and asset links](evidence-release.json).
- [All 32 eight-task confirmation episodes](https://pm1255.github.io/embodied-harness/rsi/program-evolution/confirmation/) and [48 matched three-arm replays](https://pm1255.github.io/embodied-harness/rsi/program-evolution/matched-reference/).

The single-host controller was added after these distributed jobs. It uses the same underlying proposal/evaluation/feedback commands and has contract tests; these results must not be represented as an extra end-to-end run of that new entry point.
