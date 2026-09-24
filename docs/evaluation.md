# Evaluation contract

The project reports a fixed-budget 20-case GPT pilot, not an official benchmark success score. API access, simulator smoke validation and task-solving evaluation are separate milestones.

For comparisons, freeze model ID, reasoning setting, task/seed list, observation channels, tool implementations, controller limits, max decisions and control-step budget. Compare single-tool decisions with multi-tool plans on paired tasks and seeds. Keep memory/traces from evaluation episodes out of later test prompts unless evaluating an explicitly declared online-learning protocol.

Report per environment and per protocol:

- Environment task success, with trial count and uncertainty.
- Model-reported completion separately from environment success.
- GPT request count, input/output tokens, request latency and total wall time.
- Local policy/perception calls when plugins use them.
- Controller ticks, recovery attempts and budget exhaustion.
- Infrastructure errors and unknown outcomes separately from task failures.

`report` groups by environment, observation protocol and model. It excludes infrastructure errors from its known-valid success denominator and prints their count. Cancellations count as unsuccessful when the evaluator supplies an outcome. It is a descriptive report, not a leaderboard certification.

The built-in adapters render simulator depth as a camera sensor and read robot proprioception. They do not read object poses, contact labels, future actions or task predicates for model decisions. The evaluator calls the task predicate only after the run. If a plugin uses privileged information, change and document the observation protocol; never merge those results with sensor-only runs.

Offline fixture examples use a deterministic planner and kinematic motion. A `smoke` run uses a scripted 2cm upward motion. Neither demonstrates GPT intelligence, generalization, manipulation skill or real-world safety.

The manifest runner additionally reports task success over **all planned attempts**, with no hidden retry or failure filtering; see `scripts/run_benchmark.py`. Integration smoke checks require a successful motion tool, not merely a zero process exit.
