# RSI Lab 实测记录

**状态：完整实验已结束。**

[交互式实验台](https://pm1255.github.io/embodied-harness/rsi/experiment-v1/) · [冻结 benchmark](experiment-v1/benchmark.json) · [系统设计](../rsi-design.md) · [边界探索与停滞判据](../frontier-evolution.md) · [π0.5 工具诊断](pi05/README.md)

这是冻结 GPT 权重的非参数改进实验：任务生成、失败总结、记忆检索和技能组合，不是基础模型权重训练。使用 AiXor 报告为 `gpt-6-sol` 的模型；没有独立验证上游身份。

## 独立测试

| 配置 | 成功 / 已完成回合 | Wilson 95% 区间 | GPT 次数 / 回合 | 技能调用 | 基础设施错误 |
|---|---:|---:|---:|---:|---:|
| 基础工具 | 1/12 | 1.5%–35.4% | 5.75 | 0 | 3 |
| 基础工具 + 记忆 | 1/12 | 1.5%–35.4% | 5.17 | 0 | 5 |
| 基础工具 + 技能 | 0/12 | 0.0%–24.2% | 5.08 | 30 | 4 |
| 记忆 + 技能 | 0/12 | 0.0%–24.2% | 5.50 | 42 | 3 |

组合组相对基础组：由失败变成功 **0** 个，由成功变失败 **1** 个；精确 McNemar 配对检验 p=1.000。

每组计划 12 个测试回合，来自 6 个自适应选择的原生任务族 × 2 个新场景种子。这是同任务族内的场景迁移，不是新任务族泛化。样本量小，区间没有校正任务族内相关性；不能凭这轮实验宣称优于 ASPIRE、RPent 或 VLA。全部基础设施错误保留在分母中。

## 大模型生成了哪些任务

| 轮次 | 原生任务 | 场景参数 | 希望暴露的短板（模型原文） |
|---:|---|---|---|
| 1 | `push-v3` / 实例 0 | yaw -8°; light ×1.0 | Under a modest left camera yaw and near-normal lighting, performance will fail when visual alignment does not translate into sustained lateral contact with the puck; success should be falsifiable by puck trajectory ending away from the visible target despite contact attempts. |
| 1 | `button-press-v3` / 实例 1 | yaw 10°; light ×0.85 | A rightward camera viewpoint will expose weakness in visual-to-contact depth estimation: the gripper may touch the button without pressing it fully inward. Failure is measured by incomplete button travel or an unpressed final state. |
| 1 | `peg-insert-side-v3` / 实例 2 | yaw -12°; light ×0.78 | This harder manipulation scenario will reveal whether the controller can maintain pose and force alignment through constrained insertion under camera yaw and reduced illumination. Failure is falsified by the peg not becoming fully seated in the socket. |
| 2 | `door-open-v3` / 实例 3 | yaw -6°; light ×1.0 | Under a modest left yaw and normal lighting, the controller will reach the visible handle but fail to establish the continuous contact and motion needed to open the door. Falsifiable criterion: the door remains closed despite a completed approach, or the handle contact/rotation attempt terminates with outside_workspace or target_not_reached. |
| 2 | `drawer-open-v3` / 实例 4 | yaw 8°; light ×0.9 | A rightward viewpoint will expose weak depth estimation and contact persistence: the gripper will approach the drawer front but lose alignment or apply insufficient sustained pull. Falsifiable criterion: the drawer does not visibly open or the pull ends before meaningful drawer travel, with target_not_reached or budget exhaustion as supporting failure data. |
| 2 | `pick-place-v3` / 实例 5 | yaw -10°; light ×0.8 | Under left yaw and reduced but valid illumination, the controller will fail to complete the full grasp-transport-place chain because it cannot verify grasp state and maintain object pose through transport. Falsifiable criterion: the object is not lifted, is dropped during transport, or is not placed at the visible target marker despite attempted grasp and motion. |

物理布局使用 MetaWorld MT1 原生随机化，模型选择实例、视角和光照。没有生成新网格资产，没有改写任务成功判据。第二轮任务依据第一轮开发失败提出。

## 记忆、技能与准入

| 轮次 | 开发基础组 | 开发候选组 | GPT 次数（基础 → 候选） | 结果 |
|---:|---:|---:|---:|---|
| 1 | 0 | 0 | 17 → 22 | 拒绝 |
| 2 | 0 | 0 | 27 → 32 | 拒绝 |

准入针对整个候选包，不能归因到某个单独技能。被拒绝的候选仍进入四组消融实验，但不会被当作正式准入库。测试结果从未返回给任务生成器或记忆总结器。

[第一轮记忆](experiment-v1/cycle-1-MEMORY.md) · [第二轮记忆](experiment-v1/cycle-2-MEMORY.md) · [最终候选和正式准入快照](experiment-v1/benchmark.json)

## 运行记录与限制

页面已记录 72 个回合：探索 6、开发验证 18、独立测试 48。
成对初始传感器检查：12/12 组的四个条件拥有相同初始图像和机器人状态哈希。

每回合最多 8 次 GPT 决策 / 400 控制步。原始协议先封存，设计请求的超时重试另有记录；仿真回合没有静默重试。最初字符串形式的技能生成出现格式错误，原始结果与一次显式结构化修复均保留。

已记录的回合 API 请求总数：**391**。上游未返回使用量的请求：**25**。因此 token 数只能视为已报告用量，不能伪装成完整账单。

原始事件下载包含全部控制步、模型调用和图像哈希；网页视频展示抽样观测，明确标为事件回放而非实时录像。完整原始图像保存在实验归档中。

## 结论

**本轮没有显示组合组比基础组有更高的任务成功数，不能宣称实现了能力突破。**

闭环已经能产生可执行场景、带证据的记忆和参数化技能，并自动记录准入或拒绝。但“循环跑起来”与“机器人能力提高”是两件需要分别验证的事。

本轮记忆多次强调接触、抓取未验证，以及像素投影不可达；候选技能仍主要组合既有运动原语。这些观察支持继续改进接触与抓取工具的方向，但还不能证明增加总结文字就能弥补控制能力。π0.5 的工具集成另列实验，不混入这张 MetaWorld 对照表。

## 进化档案

保留 102 条归档事件，包括两轮候选、拒绝结果、原始设计请求、回合证据与独立工具诊断。
链头 SHA-256：`050d309def97ffc6bd1f70e8812b9cb9e76bd66318e8d0b2175b270ac8b6145f`。
新增边界诊断只使用开发数据；它没有参与本次 v1 的任务选择。自动执行任意生成工具源码仍未实现，源码提案目前只归档。
