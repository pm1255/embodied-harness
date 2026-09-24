# π0.5 工具真实运行记录

[双视角回放与模型调用](https://pm1255.github.io/embodied-harness/rsi/pi05/)

用户已有 RoboTwin ALOHA π0.5 权重，训练重叠未知；不是官方 π0.5-LIBERO 基准。以下是保留全部尝试的工程诊断，后续版本修复不能当成 RSI 模型自主进化收益。

| 版本 / 作业 | 任务 | 控制步 | API 次数 | 原生物理成功 | 完整流程成功 | 状态 |
|---|---|---:|---:|---|---|---|
| v1 · UTF-8 输出失败 / 1063471 | click_bell | 0 | 0 | 否 | 否 | infrastructure_error |
| v1 · UTF-8 输出失败 / 1063471 | open_microwave | 0 | 0 | 否 | 否 | infrastructure_error |
| v2 · 推理接口 HTTP 400，原因未确认 / 1063602 | click_bell | 0 | 1 | 否 | 否 | infrastructure_error |
| v2 · 推理接口 HTTP 400，原因未确认 / 1063602 | open_microwave | 0 | 1 | 否 | 否 | infrastructure_error |
| v3 · 实际推理与动作；渲染过慢后显式停止 / 1063988 | click_bell | 30 | 1 | 未知 | 未知 | cancelled |
| v4 · 显式 raster 渲染与传感器复用 / 1064188 | click_bell | 90 | 8 | 是 | 否 | infrastructure_error |
| v4 · 显式 raster 渲染与传感器复用 / 1064188 | open_microwave | 220 | 8 | 否 | 否 | decision_budget_exhausted |

每次 `run_vla(instruction, chunks)` 由实际权重预测关节动作，最多 8 个动作块、每块最多 10 步。GPT 收到新图像后再决定。视频是抽样事件回放，原始轨迹保留全部动作。

原生成功判据仅在回合结束后读取。按铃场景曾出现物理成功后 GPT API 失败；我们保留两个字段，完整流程成功不会用物理成功覆盖。

v3 因渲染过慢被显式停止，末态成功未知。v4 改用明确记录的 raster 渲染并复用同一 tick 的传感器。这改变了视觉输入，不能将 v3/v4 作为只改变推理速度的配对消融。

公开 LIBERO π0.5 路径另有传感器/动作接口检查，但使用非模型 fixture；没有计入这里的权重推理结果。

Checkpoint SHA-256: `55e259b11bf839b4d10784da73da5e55ff86e7c90b0e3f49c44513def4abf1c5`
