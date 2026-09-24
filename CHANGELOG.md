# Changelog

## 0.1.0 — engineering alpha

- GPT Responses API image/tool planner with dynamic typed plans.
- Bounded sequential executor, observed preconditions, cancellation, deadlines and execution tracing.
- LIBERO and MetaWorld sensor/control adapters with real simulator smoke evidence.
- RoboCasa adapter and RoboTwin task-factory bridge, explicitly pending runtime validation.
- Offline success/failure fixtures, portable trace viewer, CLI, packaging, tests and CI.

No live GPT benchmark, universal grasp skill, collision planner, remote RPC service or validated physical-robot adapter is included in this release.

### Live API diagnostics

- Add explicit Responses streaming and Chat Completions compatibility modes, bounded stream parsing, and no hidden retries.
- Add single-primitive vs batch plan selection and provider/protocol provenance in traces.
- Publish all initial simulator attempts and two portable camera/tool traces, including gateway errors and incomplete LIBERO execution.
