"""Render checkpoint-backed tool diagnostics, keeping native and end-to-end outcomes separate."""
import argparse
import copy
import gzip
import json
from pathlib import Path

from export_rsi import video
from embodied_harness.rsi.core import digest, write_json


STAGES = [
    ('', '1063471', 'v1 · UTF-8 输出失败'),
    ('repaired', '1063602', 'v2 · 推理接口 HTTP 400，原因未确认'),
    ('inference-repaired', '1063988', 'v3 · 实际推理与动作；渲染过慢后显式停止'),
    ('raster', '1064188', 'v4 · 显式 raster 渲染与传感器复用'),
]


def export(source, destination):
    source, destination = Path(source), Path(destination)
    (destination/'media').mkdir(parents=True, exist_ok=True)
    rows = []
    for directory, job_id, stage in STAGES:
        for task in ('click_bell', 'open_microwave'):
            root = source/directory/task
            if not (root/'events.jsonl').exists():
                continue
            events = [json.loads(line) for line in (root/'events.jsonl').read_text().splitlines()]
            summary_path = root/'summary.json'
            summary = json.loads(summary_path.read_text()) if summary_path.exists() else {
                'status':'cancelled' if directory=='inference-repaired' else 'incomplete',
                'success':None, 'environment_success':None,
                'api_calls':sum(e['kind']=='model_request' for e in events),
                'control_ticks':sum(e['kind']=='control_tick' for e in events)}
            identity = (directory or 'initial')+'-'+task
            media = destination/'media'/identity
            timeline = video(events, root, media.with_suffix('.mp4'))
            public = copy.deepcopy(events)
            for e in public:
                if e['kind']=='model_response':
                    e['payload'].pop('response_id', None)
                    (e['payload'].get('usage') or {}).pop('attribution', None)
                    for call in e['payload'].get('calls', []):
                        call.pop('id', None)
                        call.pop('call_id', None)
            with gzip.open(media.with_suffix('.jsonl.gz'), 'wt', encoding='utf-8') as stream:
                for e in public:
                    stream.write(json.dumps(e,ensure_ascii=False)+'\n')
            rows.append({'id':identity,'job_id':job_id,'task':task,'stage':stage,'summary':summary,
                         'timeline':timeline,'video':f'media/{identity}.mp4',
                         'trace':f'media/{identity}.jsonl.gz','raw_trace_sha256':digest(events),
                         'public_trace_sha256':digest(public)})
    data={'rows':rows, 'checkpoint_sha256':'55e259b11bf839b4d10784da73da5e55ff86e7c90b0e3f49c44513def4abf1c5',
          'contract':'robotwin_aloha_qpos14_v1', 'training_overlap':'unknown',
          'experiment':'Engineering diagnostics on two seed-0 tasks; not a randomized benchmark or RSI gain.'}
    write_json(destination/'data.json',data)
    template=Path(__file__).resolve().parents[1]/'src/embodied_harness/web/policy.html'
    (destination/'index.html').write_text(template.read_text().replace('__DATA__',
        json.dumps(data,ensure_ascii=False).replace('<','\\u003c')),encoding='utf-8')
    table=['# π0.5 工具真实运行记录','','[双视角回放与模型调用](https://pm1255.github.io/embodied-harness/rsi/pi05/)','',
           '用户已有 RoboTwin ALOHA π0.5 权重，训练重叠未知；不是官方 π0.5-LIBERO 基准。'
           '以下是保留全部尝试的工程诊断，后续版本修复不能当成 RSI 模型自主进化收益。','',
           '| 版本 / 作业 | 任务 | 控制步 | API 次数 | 原生物理成功 | 完整流程成功 | 状态 |',
           '|---|---|---:|---:|---|---|---|']
    for r in rows:
        s=r['summary']
        def label(v):
            return '未知' if v is None else ('是' if v else '否')
        table.append(f"| {r['stage']} / {r['job_id']} | {r['task']} | {s['control_ticks']} | {s['api_calls']} | "
                     f"{label(s.get('environment_success'))} | {label(s['success'])} | {s['status']} |")
    table += ['', '每次 `run_vla(instruction, chunks)` 由实际权重预测关节动作，最多 8 个动作块、每块最多 10 步。'
              'GPT 收到新图像后再决定。视频是抽样事件回放，原始轨迹保留全部动作。', '',
              '原生成功判据仅在回合结束后读取。按铃场景曾出现物理成功后 GPT API 失败；'
              '我们保留两个字段，完整流程成功不会用物理成功覆盖。', '',
              'v3 因渲染过慢被显式停止，末态成功未知。v4 改用明确记录的 raster 渲染并复用同一 tick 的传感器。'
              '这改变了视觉输入，不能将 v3/v4 作为只改变推理速度的配对消融。', '',
              '公开 LIBERO π0.5 路径另有传感器/动作接口检查，但使用非模型 fixture；没有计入这里的权重推理结果。', '',
              f"Checkpoint SHA-256: `{data['checkpoint_sha256']}`"]
    (destination/'README.md').write_text('\n'.join(table)+'\n',encoding='utf-8')
    print(json.dumps({'attempted_runs':len(rows)}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source')
    p.add_argument('destination')
    a=p.parse_args()
    export(a.source,a.destination)
