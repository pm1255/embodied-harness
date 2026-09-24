# Embodied Harness

**让 GPT 在需要决策时推理，让执行过程可以逐步检查。**

[English](README.md) · [架构](docs/architecture.md) · [环境接入](docs/adapters.md) · [验证状态](docs/validation.md)

这是一个 GPT 优先的机器人执行框架。GPT 一次生成包含多个工具操作的短计划，执行器根据反馈执行；遇到失败、前置条件不满足或计划结束，再把新观测交回模型。

首版包括：可中断计划执行、GPT 图像与工具调用、四种仿真环境的适配路径、双视角执行记录网页、离线演示、测试与 CI。

> **当前是 v0.1 工程预览。** 离线演示没有调用 GPT，也不是物理仿真。仿真器冒烟测试只验证接口和控制，不代表任务成功率。GPT 端到端性能、RoboCasa / RoboTwin 资产环境和真机测试的状态，见验证文档。项目不宣称已经支持任意抓取、避障或双臂任务。

## 无需 API、GPU 或模型权重即可体验

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
embodied-harness demo --out runs/batch
embodied-harness view runs/batch
```

打开命令打印的网址，可以查看双视角观测、每次工具输入与结果、实际 TCP 路径和事件记录。

```bash
# 每个工具分别决策的对照
embodied-harness demo --per-tool --out runs/per-tool
# 故障示例：中止后续操作
embodied-harness demo --fault-after 12 --out runs/failure
embodied-harness report runs
```

两种成功演示执行相同动作，确定性决策次数为 4 次与 2 次（含最后结束决策），GPT 调用都为 0。这个结果只说明执行机制，没有证明 GPT 性能提升。

## 连接 GPT 和真实仿真器

```bash
pip install -e '.[metaworld]'
embodied-harness smoke --env metaworld --config examples/metaworld.json
export OPENAI_API_KEY='你的密钥'
export OPENAI_MODEL='你的账号可访问的GPT模型ID'
embodied-harness run --env metaworld --config examples/metaworld.json \
  --task 'Move the gripper to the visible target' --out runs/gpt-metaworld
```

模型与 API 权限由使用者配置；框架不会复用 ChatGPT/Codex 登录凭证。LIBERO、RoboCasa、RoboTwin 使用独立的环境安装方式，见 [接入文档](docs/adapters.md)。

## 首版工具的真实能力

- `move_relative`：按机器人坐标轴移动 2、5 或 10cm，局部闭环控制，保持当前姿态。
- `move_to_pixel`：从当前相机深度反投影可见表面点，移动到该点或其上方 8cm。它不估计空中点的深度，也不生成抓取姿态。
- `set_gripper`：夹爪开合命令。完成命令不等于抓到了物体。

当前不包含碰撞规划和通用抓取模型。可以通过插件加入经过验证的 MoveIt、视觉伺服或 VLA 技能。没有后端能力的工具不会出现在模型的工具表里。

**模型看到的内容**：当前图片、机器人自身状态、工具描述、近期执行结果。

**模型看不到的内容**：环境任务成功判据、物体真值状态、未来末端深度、专家动作和参考轨迹。

输出记录区分模型判断、工具完成和环境成功。运动后继续使用旧图片的像素会被拒绝，避免错误地把旧坐标当成新观测。

## 项目定位

我们希望减少每个任务所需的手写代码，以及不必要的大模型调用。是否提高成功率、降低总耗时，需要用真实任务评测验证。

参考并致谢 [RPent](https://github.com/RLinf/RPent)。本项目独立编写，聚焦较小的执行内核，不声称超越 RPent。四个环境适配器不是四套已经完成的 benchmark。

当前执行器只能在控制步边界协作式取消；它不能代替硬件急停、实时控制器或碰撞检查。

Apache-2.0 开源。仓库不包含模型权重、私有数据、服务器配置或实验录屏。欢迎贡献环境实测、经过验证的技能和失败复现。
