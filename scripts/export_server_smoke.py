"""Publish the separate server-integration check without calling it model evolution."""

import argparse
import html
import json
from pathlib import Path
import shutil

from embodied_harness.trace import export_viewer
from export_rsi import video


def export(campaign, destination):
    campaign, destination = Path(campaign), Path(destination)
    protocol = json.loads((campaign / "protocol.json").read_text())
    result = json.loads((campaign / "results.json").read_text())
    cases = {case["id"]: case for case in protocol["cases"]}
    if not result["completed"] or len(result["rows"]) != len(cases):
        raise ValueError("Preserve all planned integration attempts, including failures")
    if {row["case_id"] for row in result["rows"]} != set(cases):
        raise ValueError("Unexpected or missing integration case")
    destination.mkdir(parents=True, exist_ok=True)
    cards, rows = [], []
    for original in result["rows"]:
        identity = original["case_id"] + "--candidate"
        source, output = campaign / identity, destination / identity
        events = [json.loads(line) for line in (source / "events.jsonl").read_text().splitlines()]
        summary = json.loads((source / "summary.json").read_text())
        if summary != original["summary"]:
            raise ValueError("Summary changed")
        if summary["success"] and not any(e["kind"] == "environment_terminal" for e in events):
            raise ValueError("Missing native success event")
        binding = next(e["payload"] for e in events if e["kind"] == "candidate_identity")
        if binding["candidate_sha256"] != protocol["candidate_sha256"]:
            raise ValueError("Bundle changed")
        shutil.copytree(source, output, dirs_exist_ok=True)
        export_viewer(output)
        timeline = video(events, output, output / "replay.mp4")
        calls = [e["payload"]["step"] for e in events if e["kind"] == "tool_start"]
        rejected = sum(e["kind"] == "plan_rejected" for e in events)
        vla = [e for e in events if e["kind"] == "vla_prediction"]
        if any(e["payload"]["model"]["checkpoint_sha256"] != protocol["checkpoint_sha256"] for e in vla):
            raise ValueError("Unexpected policy checkpoint")
        row = dict(original, schema_rejections=rejected, vla_predictions=len(vla),
                   tool_calls=calls, timeline=timeline,
                   video=identity + "/replay.mp4", trace_viewer=identity + "/")
        rows.append(row)
        task = html.escape(cases[original["case_id"]]["instruction"])
        outcome = "原生成功" if summary["success"] else html.escape(summary["status"])
        cards.append(f'''<section><h2>{task}</h2><p>{outcome} ·
执行器记录 {summary['api_calls']} 次 API 调用 · {summary['control_ticks']} 个控制步 ·
{len(vla)} 次 VLA 动作块推理 · {rejected} 次参数拒绝</p>
<video controls playsinline preload="metadata" src="{identity}/replay.mp4"></video>
<p>双视角抽样事件回放，每秒 3 个事件，非实时录像。
<a href="{identity}/">打开完整观测、工具与控制事件</a></p>
<details open><summary>模型实际选择的工具及参数</summary>
<pre>{html.escape(json.dumps(calls, ensure_ascii=False, indent=2))}</pre></details></section>''')
    data = {"protocol": protocol, "rows": rows, "model_revision_changed": False,
            "engineering_validation_only": True}
    (destination / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>服务器端链路验证 · Embodied Harness</title>
<style>body{background:#0b1420;color:#dfebf4;font:16px/1.7 system-ui;margin:0}
main{max-width:1100px;margin:auto;padding:30px}section{background:#142233;border:1px solid #29435a;
border-radius:14px;padding:22px;margin:24px 0}a{color:#70e2c5}video{width:100%}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;background:#09111b;padding:16px}
p{color:#b0c3d3}h1{font-size:34px}h2{font-size:22px}</style><main>
<a href="../">三轮模型进化</a> · <a href="../matched-reference/">同状态三组对照</a> · <a href="data.json">数据</a>
<h1>服务器上的 GPT 服务 → harness → π0.5 → 仿真</h1>
<p>独立工程验证：沿用第三版冻结记忆、skill 与程序，改用服务器端决策服务，并开启预算内参数纠错。
两项原任务使用状态 9；每项最多 6 次决策、960 个控制步。任务是在看到扩展实验的问题后选取的。
它不是第四轮模型改进，也不是与旧链路的配对性能比较，任务难度没有增加。</p>
<p>参数纠错开关启用不代表本次触发了纠错；下面逐项报告实际拒绝次数。所有成功与失败均保留。
API key 保存在服务器私有配置目录，不进入公开归档；GPU 工作者通过目录协议收取模型决策。</p>
''' + "".join(cards) + '</main></html>'
    (destination / "index.html").write_text(page)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign")
    parser.add_argument("destination")
    args = parser.parse_args()
    export(args.campaign, args.destination)
