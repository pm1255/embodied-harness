"""Write factual experiment tables from exported evidence; never fabricate gains."""
import argparse
from collections import Counter
import json
from pathlib import Path


def report(source, target):
    data = json.loads(Path(source).read_text())
    target = Path(target)
    rows = data['rows']
    stats = data['statistics']
    names = {'baseline':'基础工具', 'memory':'基础工具 + 记忆', 'skills':'基础工具 + 技能', 'combined':'记忆 + 技能'}
    lines = ['# RSI Lab 实测记录', '',
             '**状态：'+('完整实验已结束。' if data['complete'] else '实验进行中；下列结果尚不完整，不能作为最终结论。')+'**', '',
             '[交互式实验台](https://pm1255.github.io/embodied-harness/rsi/experiment-v1/) · '
             '[冻结 benchmark](experiment-v1/benchmark.json) · [系统设计](../rsi-design.md)', '',
             '这是冻结 GPT 权重的非参数改进实验：任务生成、失败总结、记忆检索和技能组合，不是基础模型权重训练。'
             '使用 AiXor 报告为 `gpt-6-sol` 的模型；没有独立验证上游身份。', '',
             '## 独立测试', '',
             '| 配置 | 成功 / 已完成回合 | Wilson 95% 区间 | GPT 次数 / 回合 | 技能调用 | 基础设施错误 |',
             '|---|---:|---:|---:|---:|---:|']
    for arm in stats['arms']:
        n=arm['n']
        interval='–'.join(f'{x*100:.1f}%' for x in arm['wilson95']) if n else '未完成'
        calls=f"{arm['api_calls']/n:.2f}" if n else '—'
        lines.append(f"| {names[arm['arm']]} | {arm['successes']}/{n} | {interval} | {calls} | {arm['skill_calls']} | {arm['infrastructure_errors']} |")
    paired=stats['paired_combined_baseline']
    lines += ['', f"组合组相对基础组：由失败变成功 **{paired['wins']}** 个，由成功变失败 **{paired['losses']}** 个；"
              f"精确 McNemar 配对检验 p={paired['exact_mcnemar_p']:.3f}。", '',
              '每组计划 12 个测试回合，来自 6 个自适应选择的原生任务族 × 2 个新场景种子。'
              '这是同任务族内的场景迁移，不是新任务族泛化。样本量小，区间没有校正任务族内相关性；'
              '不能凭这轮实验宣称优于 ASPIRE、RPent 或 VLA。全部基础设施错误保留在分母中。', '',
              '## 大模型生成了哪些任务', '',
              '| 轮次 | 原生任务 | 场景参数 | 希望暴露的短板（模型原文） |', '|---:|---|---|---|']
    for case in data['cases']:
        lines.append(f"| {case['cycle']} | `{case['task']}` / 实例 {case['task_index']} | yaw {case['scene']['camera_yaw_deg']}°; light ×{case['scene']['light_scale']} | {case['hypothesis'].replace('|','/')} |")
    lines += ['', '物理布局使用 MetaWorld MT1 原生随机化，模型选择实例、视角和光照。'
              '没有生成新网格资产，没有改写任务成功判据。第二轮任务依据第一轮开发失败提出。', '',
              '## 记忆、技能与准入', '', '| 轮次 | 开发基础组 | 开发候选组 | GPT 次数（基础 → 候选） | 结果 |',
              '|---:|---:|---:|---:|---|']
    for cycle in data['cycles']:
        gate=cycle['gate']
        lines.append(f"| {cycle['cycle']} | {gate['baseline_successes']} | {gate['candidate_successes']} | {gate['baseline_calls']} → {gate['candidate_calls']} | {'准入' if gate['accepted'] else '拒绝'} |")
    lines += ['', '准入针对整个候选包，不能归因到某个单独技能。被拒绝的候选仍进入四组消融实验，但不会被当作正式准入库。'
              '测试结果从未返回给任务生成器或记忆总结器。', '',
              '[第一轮记忆](experiment-v1/cycle-1-MEMORY.md) · [第二轮记忆](experiment-v1/cycle-2-MEMORY.md) · '
              '[最终候选和正式准入快照](experiment-v1/benchmark.json)', '', '## 运行记录与限制', '']
    phases=Counter(row['split'] for row in rows)
    lines.append(f"页面已记录 {len(rows)} 个回合：探索 {phases['discovery']}、开发验证 {phases['validation']}、独立测试 {phases['heldout']}。")
    reset=data.get('paired_reset_audit',{})
    lines.append(f"成对初始传感器检查：{sum(v['identical'] for v in reset.values())}/{len(reset)} 组的四个条件拥有相同初始图像和机器人状态哈希。")
    lines += ['', '每回合最多 8 次 GPT 决策 / 400 控制步。原始协议先封存，设计请求的超时重试另有记录；'
              '仿真回合没有静默重试。最初字符串形式的技能生成出现格式错误，原始结果与一次显式结构化修复均保留。', '',
              f"已记录的回合 API 请求总数：**{sum(r['result'].get('api_calls',0) for r in rows)}**。"
              f"上游未返回使用量的请求：**{sum(r.get('usage_missing_calls',0) for r in rows)}**。"
              '因此 token 数只能视为已报告用量，不能伪装成完整账单。', '',
              '原始事件下载包含全部控制步、模型调用和图像哈希；网页视频展示抽样观测，明确标为事件回放而非实时录像。'
              '完整原始图像保存在实验归档中。', '', '## 结论', '']
    if not data['complete']:
        lines.append('等待预定测试结束后填写；当前不声称能力提升。')
    else:
        base=next(x for x in stats['arms'] if x['arm']=='baseline')
        combined=next(x for x in stats['arms'] if x['arm']=='combined')
        if combined['successes']<=base['successes']:
            lines.append('**本轮没有显示组合组比基础组有更高的任务成功数，不能宣称实现了能力突破。**')
        else:
            lines.append(f"组合组成功数从 {base['successes']}/{base['n']} 增至 {combined['successes']}/{combined['n']}；"
                         '这只是本轮样本内的观察，仍需扩大种子与任务族并控制基础设施错误，才能确认稳定提升。')
        lines += ['', '闭环已经能产生可执行场景、带证据的记忆和参数化技能，并自动记录准入或拒绝。'
                  '但“循环跑起来”与“机器人能力提高”是两件需要分别验证的事。', '',
                  '本轮记忆多次强调接触、抓取未验证，以及像素投影不可达；候选技能仍主要组合既有运动原语。'
                  '这些观察支持继续改进接触与抓取工具的方向，但还不能证明增加总结文字就能弥补控制能力。'
                  'π0.5 的工具集成另列实验，不混入这张 MetaWorld 对照表。']
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('data')
    p.add_argument('output')
    a=p.parse_args()
    report(a.data,a.output)
