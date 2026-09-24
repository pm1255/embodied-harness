# Frontier exploration, absorption, and local stopping

**Current curriculum: [benchmark first, decompose failures, return to the original task](benchmark-first-rsi.md).** Task generation is gated by that controller: only missing-subtask practice may be created early, after catalog search; harder challenges wait for whole-scope mastery. This document supplies the lower-level evidence and stopping rules.

The goal is **measurable progress on existing unsolved benchmark tasks**, not an endless stream of harder tasks or longer memory files. The agent may propose changes to its model configuration, task-facing harness, memory, skills, tool source code, and task definitions. An external experiment controller holds the evaluator, evidence store, resource budgets, and final-test partition fixed for a comparison.

## Status of this implementation

- **Executed in v1:** GPT-generated MetaWorld scenario parameters, development rollouts, evidence-bound memory, typed primitive-composition skills, paired development selection and a frozen four-arm final test. See the [actual results](rsi/README.md).
- **Implemented and tested as v2 infrastructure:** content-addressed evolution archive; branching proposals for all six component types; validation/activation/rollback records; conservative frontier assessment; prompt-ready exploration guidance; development-only retrospective visualization.
- **Not yet demonstrated:** an autonomous v2 run that writes and executes arbitrary Python tools or harness patches, constructs new physical task predicates, or improves model weights. Python source can be archived as a proposal; it is **not executed by the archive**. The current v1 run is not retroactively described as using v2.

`rsi/evolution.py`, `rsi/candidates.py`, and `rsi/frontier.py` implement those separate boundaries. `CandidateArchive.record_evaluation` is a trusted-runner API, not an authentication system or a statistical evaluator. A model's own assertions must never be passed as evaluator reports.

## The learning unit is a hypothesis and its evidence

Each proposal should bind:

1. A failed development episode and an observable failure: target missed, contact lost, grasp not verified, timeout, or tool contract failure.
2. A parent task and a positive anchor: a simpler scene or a verified controller that can solve the intended physical goal.
3. One repair hypothesis and its intervention: a memory correction, a reusable skill, a new perception/control tool, a harness change, or a different model configuration.
4. An expected observation and a comparison protocol under matched budgets.
5. Fresh validation instances, transfer instances, and previously solved regression tasks.

For example, if a mug is reached but never lifted, “try a harder mug task” is poor curriculum. First distinguish an incorrect target from a lost grasp: run an easier isolated mug scene, inspect gripper/contact feedback, propose a `verify_grasp` tool or a compliant lift skill, and test new mug positions plus old pick-and-place tasks. This is an **illustrative proposed experiment**, not a result claimed by our release.

## How exploration follows the frontier

| Evidence | Controller response | What the brain proposes next |
|---|---|---|
| Goal semantics or scene feasibility unverified | Validate the task first | A positive witness, a simpler anchor, or a corrected task |
| Too many infrastructure errors / unknown outcomes | Repair reliability | A diagnostic, not harder scenes |
| Too few valid trials | Keep uncertainty explicit | Additional development trials with independent instances |
| Success interval entirely low | Step back toward solvable tasks | A bridge task or a missing tool |
| Mixed success and failure | Probe a nearby weakness | Change one difficulty axis and test one repair |
| Success reliably high | Consolidate and test transfer | Vary position, occlusion, contact tolerance, or horizon one at a time |
| Diverse repairs have no meaningful gain with adequate evidence | Record a local plateau | Decompose the task or change the tool / representation class |
| Budget exhausted | Stop the current allocation | Preserve the frontier as unresolved |

Task difficulty is a **vector**: clutter, visibility, precision, contact complexity, horizon and embodiment can change independently. Raw novelty is not progress. Start with original benchmark failures and existing practice tasks. Use positive anchors to validate genuinely missing subtask practice. Allocate attempts to measured learning progress per cost, while reserving trials for uncertainty reduction and old-task retention. A scalar leaderboard score should not allow fewer API calls to compensate for failing the physical task.

The present `FrontierPolicy` classifies evidence and `guidance_packet` builds a proposer contract. It does not claim to implement a learned difficulty metric or an optimal budget allocator.

## Absorb facts, hypotheses, and procedures differently

| Knowledge | Can it be retained after failure? | When does it affect the default policy? |
|---|---|---|
| Observed fact | Yes, with trace citation and scope | As factual context, not a claim that a fix works |
| Repair hypothesis | Yes, explicitly unverified | For exploration, with budgeted tests |
| Validated procedure / skill / tool | Yes, including prior rejected versions | After fresh transfer, retention, contract and budget checks |

Memory entries should also carry the environment/tool version, applicable task scope, evidence IDs, and invalidation conditions. A tool or camera change can invalidate an old instruction. Summaries are derived views; they must not overwrite the underlying evidence. A rejected skill bundle should not erase valid failure observations. **v1 currently gates memory and skills as a bundle; separating factual retention from procedural promotion is a v2 design requirement.**

A candidate becomes the default only after an external evaluator checks its exact content hash. Regressions create a rollback event. Model-generated Python needs a credential-free, resource-bounded process/container with no access to evaluator internals or hidden tests; parsing Python or validating a JSON schema is not an OS sandbox. Generated task predicates need independent semantic review and positive/negative witness states. Otherwise a model can appear to improve simply by weakening the goal.

## When can we say it cannot advance?

We cannot establish an absolute limit of a foundation model from a finite experiment. We can establish **local stagnation under a named model, tools, task stratum, and resource budget**.

The configurable default policy requires:

- A validated physical task and enough valid development trials. The initial floor is 20; it is not a power guarantee.
- Three completed repair windows, covering at least two repair classes, with distinct validation instances and fresh comparisons.
- An independently computed paired improvement interval whose upper bound is below a predeclared useful gain, initially 5 percentage points, in all three windows.
- Infrastructure reliability checked separately; API failures and cancellations cannot certify a capability limit.

`paired_window` computes a conservative bounded paired-outcome interval and spends significance budget across numbered inspections. It does not accept an LLM's confidence estimate. Small windows will usually remain inconclusive. “We observed zero improvement” is not equivalent to “we have excluded a useful improvement.” Independence and truthful report production are responsibilities of the external evaluator; metadata alone cannot prove them.

At a local plateau the scheduler stops spending on that branch, preserves the evidence, and changes the decomposition/tool class. If all active branches plateau, it can stop that run with a boundary report. If funds or time run out first, the report says **budget exhausted**, not **model incapable**. Any model/tool/evaluator change starts a new comparison lineage; old stagnation evidence is not automatically a certificate for the new system.

## Preserve every branch for visualization

Run:

```bash
python scripts/capture_evolution.py runs/my-rsi runs/my-rsi/evolution
python scripts/export_rsi.py runs/my-rsi docs/rsi/my-rsi
```

The archive keeps content-addressed artifacts and an append-only hash-linked event log: task proposals, raw designer attempts, candidates, memory documents, promotion decisions, and completed rollout inputs/results/traces. New component proposals can include `harness/`, `tools/`, `memory/`, `skills/`, `tasks/`, and `model_config/` artifacts. Rejected branches and rollback targets remain addressable.

Historical imports use the actual archival timestamp; they are not backdated as live evolution events. The dashboard distinguishes the experiment brain, external evaluator, runtime and engineering changes. It shows candidate memory/skill diffs, acceptance decisions, evidence hashes, videos and frontier diagnostics. The latter use **development data only** and are explicitly retrospective for v1.

Hash chaining detects accidental or partial modification; it is not tamper-proof against an administrator rewriting the whole archive. Publishing the chain head and mirroring the immutable run directory provide independent reference points. Public traces remove provider request identifiers; full sensor frames and original traces remain in the research archive.
