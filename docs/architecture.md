# Architecture

`gpt.py` builds a Responses API request from current raster observations and a dynamic tool schema. The model selects `submit_plan` or `finish`. A request is stateless except for up to four explicit recent plans and execution reports. No private model reasoning is collected.

`runtime.py` validates every step before any side effect. The executor owns one environment and a non-reentrant execution lock. Tools are cooperative generators: each yield is one bounded control iteration. Cancellation, elapsed time and tick budgets are checked before the next iteration. Results other than `succeeded` abort the remaining plan and request a new decision. Preconditions are observed boolean facts, never model-invented predicates.

`tools.py` implements local Cartesian servoing and gripper commands. Targets are converted into dense control commands from current robot state. This is not a global motion planner. Grasp pose estimation, target tracking, obstacle maps and contact verification are separate future or user-supplied plugins.

`adapters/` owns simulator-specific reset, sensor rendering, calibration and action encoding. A shared Python interface does not imply a shared raw action vector. LIBERO and RoboCasa validate OSC controller mode; MetaWorld uses Sawyer's action scale; RoboTwin preserves native quaternion ordering and fills both arms' EE channels.

`geometry.py` uses optical camera axes (+X right, +Y down, +Z forward), metric depth and world-from-camera transforms. DepthCache rejects references to any older observation or control tick. It never loads demonstration target depth.

`runner.py` alone reads task success after the model finishes or reaches its budget. That predicate is not used to plan, retry or terminate early. The summary keeps agent outcome, environment predicate and infrastructure status separate.

`trace.py` appends JSONL events, copies images by SHA256, and exports a standalone HTML viewer. The viewer uses textContent for untrusted strings and escapes embedded JSON. Its server is read-only and loopback-only. Model calls are traced without credentials; raw camera/task content is still sensitive and must be reviewed before sharing.

## Plan example

```json
{"steps":[
  {"id":"lift","tool":"move_relative","arguments":{"arm":"arm","direction":"up","distance":"small"},"require_fact":null},
  {"id":"release","tool":"set_gripper","arguments":{"arm":"arm","state":"open"},"require_fact":null}
]}
```

All fields are required by the strict GPT schema. Unknown fields, missing tools, duplicate step IDs and plans longer than eight steps are rejected. Retrying a failed motion requires a fresh model decision; potentially non-idempotent commands are never retried automatically.

## Concurrency and limitations

v0.1 runs one episode per CLI process, with synchronous simulator stepping. Multiple independent episodes can run in separate processes. There is no distributed job manager or remote simulator RPC implementation in this release. Use separate compatible Python environments and run the CLI alongside each simulator.

The deadline is cooperative. An adapter that blocks for ten seconds cannot be interrupted by a five-second Python deadline while inside that call. RoboTwin's native `take_action` may execute multiple internal physics steps. Hardware and remote-driver plugins must provide their own bounded I/O and stop implementation before being presented as usable robot tools.
