# How does this compare with RPent?

**We have not demonstrated an advantage over RPent.** This repository is an experimental execution kernel. RPent is a broader agent framework with substantially more published manipulation evidence. A simpler implementation is not evidence of better robotics performance.

Reference inspected on 2026-09-24: [RPent commit eecf206](https://github.com/RLinf/RPent/tree/eecf206959008700a315f58dc98146f147006f09). Published scores are the authors' reports, not results reproduced here.

| Question | This repository today | RPent's public implementation | Conclusion |
|---|---|---|---|
| What executes movement? | Local Cartesian tools and a verified LIBERO π0.5 bridge; bounded model-written Python tools in 0.4 | Frozen VLA primitives, geometric tools, environment services | No matched executor comparison; grasp and contact behavior depends on the frozen policy |
| Does it support pixels and depth? | `move_to_pixel` projects current calibrated depth | LIBERO registers camera metadata, `back_project` and segmentation tools | Pixel grounding is **not** unique to us |
| Are tools backed by real interfaces? | Capability-gated registry and schema checks | Toolkit binds specs to available primitive methods | Shared engineering practice, not a differentiator |
| Can the agent reuse skills? | Evidence-bound memory, generated typed skills and bounded tool programs with paired acceptance gates | Memory, reusable primitives and flash mode | Our new RSI implementation is not evidence of superior performance |
| Is a VLA checkpoint required? | Not for the built-in local servo tools | Published manipulation configurations use Pi0.5, RLDX-1 or LingBot-VLA | Potentially smaller setup for our simple tasks; not proof of better success or total cost |
| Can execution be inspected? | Exact model JSON, projected target, TCP samples, tool result and two camera streams in one portable trace | Dashboard, logs and service/tool traces | Our portable format is a design choice; inspectability is not exclusive |
| Is task performance established? | Eight-task policy/GPT baseline and fresh-reset revision pilots; integration smoke tests separately labeled | Published multi-suite benchmark results | No matched comparison yet |
| Is real hardware validated here? | No | Public real-robot integrations and demos | Do not infer hardware readiness from our simulator traces |

Sources: [tool binding and geometry](https://github.com/RLinf/RPent/blob/eecf206959008700a315f58dc98146f147006f09/robots/libero/toolkit.py), [project feature matrix](https://github.com/RLinf/RPent/blob/eecf206959008700a315f58dc98146f147006f09/README.md), [evaluation protocols and leaderboard](https://rpent.readthedocs.io/en/latest/rst_source/leaderboard.html). Our optional RoboTwin integration uses the RLinf-maintained runtime distribution; credit for that runtime belongs to its maintainers.

## What could make this project useful?

A small, reusable layer for **measuring and reducing expensive model decisions**: one validated plan can run several local tools, stop on failure, then return fresh observations. The useful deliverable is a reproducible execution contract and evidence of its trade-offs. Fewer tool names or less code is not the objective by itself. A capable grasp skill may reduce reasoning calls more than removing tools does.

The current depth cache invalidates pixels after movement. This avoids silently executing stale targets but limits batching. Persistent target handles and general contact-aware recovery are still missing. The new LIBERO policy can execute grasps, but does not supply a general geometric grasp verifier. Straight-line servoing is not obstacle avoidance. Adding these capabilities may make the harness larger while making the robot more effective.

## What experiment could justify “better”?

| Experiment | Hold fixed | Measure |
|---|---|---|
| Single tool vs batched plans in this harness | Model endpoint/version, image resolution, tasks, initial states, tools, budgets | Task success, all API requests including failures, tokens, wall time, control ticks |
| Our executor vs RPent's executor | Same planner and evaluation states where possible; explicitly disclose different VLA/skill prerequisites | Success first, then calls/time/cost per successful task; include setup and inference costs |
| Recovery under injected tool failure | Same failure schedule, tasks and stopping budget | Recovery rate, invalid/stale actions blocked, extra model calls |

Run paired seeds, keep every attempt, publish confidence intervals, and freeze memory/exploration before evaluation. Report official suites separately from short pilots. No performance ranking should be drawn from the existing README examples.

## 中文说明

目前不能说我们比 RPent 好。RPent 已经具备 VLA 技能、几何工具、记忆和多环境评测；像素定位、工具调用、批量执行、可视化本身都不是独有优势。

我们的定位可以是一个小而可复用的执行与评测内核：把“模型决策 → 工具参数 → 几何目标 → 控制轨迹 → 执行反馈”完整记录下来，研究在保持成功率的前提下减少模型调用。这个方向有价值，但必须通过同任务、同初始状态、同模型预算的实验来证明。当前已接通 LIBERO π0.5 抓取执行与受限模型编写工具，但通用抓取验证、目标跟踪、实测避障和广泛的配对性能验证仍不足，不能用“harness 更少”掩盖能力不足。
