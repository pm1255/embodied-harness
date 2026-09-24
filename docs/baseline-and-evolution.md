# Baseline first, then evidence-backed self-evolution

The current priority is to establish a capable GPT + execution baseline on original LIBERO and then LIBERO-PRO. A low score from a three-decision geometric-servo pilot does not establish the capability of GPT, π0.5, or their properly configured combination.

## References and concrete engineering choices

| Reference | What we take from it | What this repository must demonstrate |
|---|---|---|
| [Harness VLA / RPent](https://rpent.readthedocs.io/en/latest/rst_source/awesome_works/harnessvla.html) | Frozen contact-capable VLA combined with geometric primitives, observation-based checks and targeted retries | Same initial states, policy-only versus GPT + policy, full-task success and cost |
| [NVIDIA ASPIRE](https://research.nvidia.com/labs/gear/aspire/) | Fine-grained execution evidence, program debugging and reusable skills | Each proposed fix cites an actual failure and transfers beyond its development scene |
| [Zetta](https://github.com/air-embodied-brain/Zetta-Embodiment) | Fast runtime checks and recovery separated from slower diagnosis and validation | Local checks detect failure early; candidate changes pass fresh paired evaluation before promotion |

These are references, not results reproduced by this repository. Published numbers use different models, skills, memory, task coverage and budgets; they must not be copied into our results table.

## Capable execution baseline

The corrected two-task preflight (`preflight-v4`) completed: GPT + tools **2/2**, frozen π0.5 **1/2**, with no infrastructure-error episodes. These are original LIBERO tasks, official initial state 0, with paired `checkpoint_only` and `gpt_policy` arms. Both use the same frozen RLinf π0.5 LIBERO-130 SFT checkpoint. The GPT arm can additionally choose existing geometric tools. Both have 24 segment decisions and a 1,200-control-tick ceiling; a policy segment executes at most eight freshly inferred chunks, with five executed actions per chunk for this checkpoint bridge. Policy-only therefore has an effective 960-tick ceiling (24 × 40); GPT can batch multiple tools per decision. This four-episode integration diagnostic is not an official benchmark score or a statistically established baseline. The subsequent repair comparison uses a common 960-tick ceiling for both GPT arms.

The operator chooses the checkpoint and endpoint; GPT cannot switch either. The official norm statistics, vocabulary, model hash, transforms, action clipping and gripper binarization are recorded. This bridge uses OpenPI's `pi05_libero` preset (continuous state prompt disabled), ten denoising steps and a ten-action prediction horizon; it is not an exact reproduction of RPent's inference settings. If this checkpoint/runtime combination fails, audit the transformation and inference contract before attributing the failure to the planner.

The endpoint has returned the requested `gpt-6-astra` model label during a transport check. The provider is AiXor; its upstream identity is not independently verified. A successful text check is not a visual reasoning or robot performance measurement.

LIBERO's native `done` corresponds to its success predicate. For this explicit new protocol the executor checks that terminal state after **each control tick**, including inside composed programs, and closes the generator before another action. A later render/contact query can disagree with the step-time predicate; both `native_terminal_success` and `final_state_success` are recorded. The native event determines this protocol's success, rather than the model's own completion claim. No reward, hidden object pose or task predicate is sent to the planner. Historical experiments keep their original final-state protocol unchanged. Scoring repairs and startup fixes are engineering history, not model evolution.

The SFT checkpoint was trained on LIBERO-130. Standard LIBERO measures in-domain execution here; it must not be represented as unseen-task generalization. LIBERO-PRO, additional validation resets and frozen memory experiments must be reported separately.

### Completed eight-task development baseline

`development-v2`, job 1066102, completed all 16 episodes without infrastructure errors. Each arm uses official initial state 0 on task IDs 0 and 1 from four suites. All 13 successful episodes have recorded native terminal events; all paired initial-state hashes match.

| Task | Frozen π0.5 | GPT + tools | GPT calls |
|---|---|---|---:|
| Spatial 0: bowl between plate and ramekin | Success | Success | 2 |
| Spatial 1: bowl next to ramekin | Success | Success | 4 |
| Object 0: alphabet soup into basket | Failure | Success | 4 |
| Object 1: cream cheese into basket | Success | Success | 4 |
| Goal 0: open middle drawer | Success | Failure | 21 |
| Goal 1: bowl onto stove | Success | Success | 3 |
| Long 0: soup and tomato sauce into basket | Success | Success | 7 |
| Long 1: cream cheese and butter into basket | Success | Failure | 8 |

Totals: checkpoint **7/8**, 2,017 control ticks, 296.4 s; GPT + tools **6/8**, 53 API calls, 1,864 ticks, 811.2 s. Wall times include policy startup warm-up within the first episode and broker overhead. They are observed system times, not a pure model-latency comparison. The GPT arm's two failures include repeated drawer instruction changes and a visually declared completion without native success. These are plausible orchestration hypotheses for a subsequent model-authored repair, not established causes.

[Watch every paired episode](https://pm1255.github.io/embodied-harness/rsi/baseline/) · [All-attempt archive manifest](rsi/baseline/evidence-release.json). Earlier setup failures, scoring discrepancies and the interrupted development-v1 run remain separate records. They are not silently replaced by this corrected run.

## What counts as self-evolution

The experiment brain should perform the following cycle after baseline integration:

1. Diagnose a concrete failure from synchronized cameras, tool inputs, controller feedback and outcomes.
2. Decompose the failed benchmark task; search existing task/skill contracts before creating missing practice.
3. Propose a versioned change to memory, skill, tool, runtime checking/recovery or task-facing harness code.
4. Run the candidate with fixed goal evaluators and matched execution budgets, in isolation from credentials and evaluation internals.
5. Validate on fresh original-task instances and regression tasks; promote or roll back while retaining both branches.
6. After the selected original scope is mastered, create a feasible harder scene/task version and continue.

A failed repair should change the next hypothesis or defer that branch, not terminate all exploration. A completed fixed-size experiment is a budget/schedule boundary, not evidence that the model has reached its capability limit.

**Implementation boundary:** the archive, curriculum rules, policy-backed baseline and bounded model-authored Python tool path are implemented. The latter admits `def run(args, api)`, local JSON data, status checks and nonnested literal loops of at most four iterations. Programs may compose existing robot primitives, with per-control-tick termination and operator budgets. They have no direct file/network access, imports, evaluator access, credentials or arbitrary host capabilities. This deliberately restricted grammar is not an arbitrary Python sandbox. General harness source mutation and autonomous construction of arbitrary simulator tasks remain outside the connected execution path. Do not describe an engineering-authored integration change as the experiment model improving itself.

## A real model-authored repair round

`examples/propose_baseline_repair.py` gives the experiment model the completed development outcomes, tool plans and first/last dual-camera observations. The model returns an evidence-citing diagnosis, falsifiable hypothesis, memory entries, a reusable skill procedure and actual Python tool source. The original response, rejected source, admitted artifact and content-addressed lineage are preserved.

`benchmarks/libero-program-transfer.json` fixes four original-task families and two fresh resets **before** the proposal. Freeze the candidate's exact SHA-256 in a copy of that protocol. `examples/run_program_validation.py` compares baseline GPT and GPT with the frozen candidate on the same initial states and settings. Both have 24 decisions / 960 control ticks. There are no online edits during evaluation.

The independent validator requires complete matched pairs, matching native terminal evidence and budgets, unchanged source, no task regressions, and either more successes or equal positive successes with more than 10% fewer GPT calls. The new program must actually run in at least two successful fresh instances. The validation decision is written before starting final held-out resets; held-out results never select the candidate. A four-family gate remains a small engineering check, not statistical mastery. Memory, skill and tool are evaluated together, so the experiment cannot attribute a gain to one component without additional ablations.

The export in `scripts/export_program_evolution.py` exposes the model-authored files, exact diff, gate, ledger, all paired outcomes, dual-camera replay and expansion from model call to program primitive to VLA action. Task difficulty stays unchanged until the original-task mastery criterion is met. A rejected candidate is retained for a new development hypothesis; it is not evidence that GPT cannot progress.

## What the evolution viewer must show

- **Performance:** paired baseline/candidate original-task success, fresh-reset success, regression failures, confidence intervals and API/control/wall-time costs. Changed evaluation budgets start separate curves.
- **Changes:** parent revision, proposing actor, exact before/after source, cited failure, evaluator report and promotion/rollback decision. A code diff without an executed evaluation is untested.
- **Difficulty:** separate axes for clutter, occlusion, position shift, grasp/placement tolerance, contact constraints and sequential goals, each tied to simulator configuration and a feasible task witness. A model's “level 5” label is not measured difficulty.
- **Coverage:** task × difficulty × seed results, including failures, blocked environments and missing data. No fabricated progress points or success-only clips.

The baseline checkpoint and execution adapter are fixed engineering prerequisites. RSI gains begin only when a subsequent experiment-brain proposal is evaluated under the same protocol.

## Run the paired integration diagnostic

The policy process needs a matching OpenPI PyTorch installation (including its transformers patches), the checkpoint above, the checkpoint's `norm_stats.json`, and the PaliGemma vocabulary. The simulator process needs the original LIBERO source/assets and compatible robosuite/MuJoCo. Keep their Python environments and dynamic-library paths separate if their Python/PyTorch versions differ. Merely putting the right package first on `PYTHONPATH` does not isolate `libtorch_python.so` selected through `LD_LIBRARY_PATH`.

```bash
# GPU policy process: these point to operator-installed, verified artifacts.
export OPENPI_CHECKPOINT=/path/to/checkpoint
export OPENPI_NORM_STATS=/path/to/norm_stats.json
export OPENPI_TOKENIZER=/path/to/paligemma_tokenizer.model
export VLA_CHECKPOINT_SHA256=4d9089c941793f170b625c2ed0ac7a3aa09b6f103e52dbbc82e67301529d6683
python examples/serve_policy_bridge.py --factory embodied_harness.policies.openpi_libero:create

# In the compatible LIBERO environment on the same worker:
python examples/run_libero_baseline.py \
  --manifest benchmarks/libero-policy-preflight.json \
  --out /path/to/campaign/runs/preflight-v1 \
  --broker /path/to/campaign/broker \
  --checkpoint-sha256 "$VLA_CHECKPOINT_SHA256"

# Credential-bearing machine: relay only sensor observations and tool decisions.
python examples/run_ssh_broker.py \
  --host your-worker --remote-root /path/to/campaign \
  --out runs/local-broker --key-file /private/path/to/key \
  --model gpt-6-astra --base-url https://your-provider/v1 \
  --reasoning-effort low --max-requests 48 --duration 5400
```

Start the broker before the first GPT episode. Every campaign directory is immutable; use a new directory after a failed attempt. A clean process exit can still contain infrastructure-error episodes: inspect each result, not just the scheduler's job status. Initialization failures, rejected loader changes, and successful model loading are retained separately from robot task outcomes.

The next predeclared development scope is in [`libero-policy-eight-task.json`](../benchmarks/libero-policy-eight-task.json): task IDs 0 and 1 in Spatial, Object, Goal, and Long (`libero_10`), official initial state 0. It is planned separately with `high` reasoning effort; the two-task `low`-effort integration diagnostic is not a performance improvement baseline for that protocol. Neither scope is a full benchmark or a final held-out test.
