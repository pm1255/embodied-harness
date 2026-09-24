"""Publish all cases from a completed benchmark, with dual-view recorded GIFs.

No resampling of robot motion, synthetic frames, or success-only selection.
Only provider metadata/IDs are omitted. Arguments and execution evidence stay exact.
"""

from __future__ import annotations
import argparse
import html
import json
from pathlib import Path
import shutil
from PIL import Image, ImageDraw, ImageFont, ImageOps
from embodied_harness.trace import export_viewer


def public_event(e):
    if e["kind"] == "model_response":
        p = e["payload"]
        p.pop("response_id", None)
        p["usage"].pop("attribution", None)
        p["calls"] = [
            {k: c[k] for k in ("name", "arguments", "type", "status") if k in c}
            for c in p.get("calls", [])
        ]
    return e


def gif(events, source, output):
    frames, durations = [], []
    obs, call, geometry, result = None, None, None, None
    ticks = 0
    smoke = any(
        e["kind"] == "episode_start" and e["payload"].get("planner") == "SmokePlanner"
        for e in events
    )
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 12)
    except OSError:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 12)
    for e in events:
        p, kind = e["payload"], e["kind"]
        if kind == "control_tick":
            ticks += 1
            if p.get("target_m") is not None:
                geometry = {"target_m": p["target_m"]}
        if kind == "observation":
            obs = p
        if kind == "tool_start" and smoke:
            call = [{"name": p["step"]["tool"], "arguments": json.dumps(p["step"]["arguments"])}]
        if kind == "model_response":
            call = p.get("calls", [])
            result = None
            geometry = None
        if kind == "geometry":
            geometry = p
        if kind == "tool_end":
            result = p
        if obs is None or kind not in (
            "observation",
            "model_response",
            "geometry",
            "tool_end",
            "episode_end",
        ):
            continue
        im = Image.new("RGB", (520, 370), "#09131b")
        d = ImageDraw.Draw(im)
        views = obs["frames"]
        if any(f["name"] == "head_camera" for f in views):
            views = sorted(views, key=lambda f: 0 if f["name"] == "head_camera" else 1)
        for i, f in enumerate(views[:2]):
            with Image.open(source / f["image_path"]) as image:
                im.paste(
                    ImageOps.pad(image.convert("RGB"), (256, 256), color="#09131b"), (i * 264, 22)
                )
            d.text((i * 264 + 5, 4), f["name"], fill="#91a9b4", font=font)
            if call:
                a = json.loads(call[-1]["arguments"])
                if (
                    a.get("observation_id") == obs["id"]
                    and a.get("camera") == f["name"]
                    and "pixel" in a
                ):
                    u, v = a["pixel"]
                    x, y = i * 264 + u * 256 / f["width"], 22 + v * 256 / f["height"]
                    d.ellipse((x - 5, y - 5, x + 5, y + 5), outline="#ffd185", width=2)

        name = ", ".join(c["name"] for c in call) if call else "awaiting response"
        d.text(
            (8, 284),
            ("SMOKE TOOL (no model): " if smoke else "MODEL: ") + name,
            fill="#66e1bc",
            font=font,
        )
        args = json.loads(call[-1]["arguments"]) if call else {}
        detail = str({k: v for k, v in args.items() if k != "observation_id"})
        d.text((8, 302), detail[:82], fill="#e5f1f4", font=font)
        target = geometry.get("target_m") if geometry else None
        d.text(
            (8, 320),
            "HARNESS world target: " + str([round(v, 3) for v in target] if target else None),
            fill="#e5f1f4",
            font=font,
        )
        status = result.get("error_code") or result.get("status") if result else "pending"
        d.text(
            (8, 338),
            f"{ticks} control ticks | {status} | trace event {e['seq']}",
            fill="#ffd185",
            font=font,
        )
        frames.append(im)
        durations.append(650 if kind == "observation" else 1000)
    if frames:
        durations[-1] = 2500
        frames[0].save(
            output,
            save_all=True,
            append_images=frames[1:],
            duration=durations,
            loop=0,
            optimize=True,
        )
    return len(frames)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("run")
    p.add_argument("destination")
    args = p.parse_args()
    src, dest = Path(args.run), Path(args.destination)
    report = json.loads((src / "report.json").read_text())
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("report.json", "manifest.json", "protocol.json"):
        shutil.copy2(src / name, dest / name)
    rows = []
    cards = []
    options = []
    for r in report["results"]:
        cid = r["id"]
        case = dest / cid
        case.mkdir(exist_ok=True)
        trace = src / cid / "trace"
        events = []
        path = trace / "events.jsonl"
        if path.exists():
            events = [public_event(json.loads(line)) for line in path.read_text().splitlines()]
            (case / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
            if (trace / "summary.json").exists():
                shutil.copy2(trace / "summary.json", case / "summary.json")
            for e in events:
                if e["kind"] == "observation":
                    for f in e["payload"]["frames"]:
                        target = case / f["image_path"]
                        target.parent.mkdir(exist_ok=True)
                        shutil.copy2(trace / f["image_path"], target)
            export_viewer(case)
        count = gif(events, case, case / "replay.gif")
        outcome = (
            "SUCCESS"
            if r["task_success"]
            else "ERROR"
            if r["summary"].get("status") == "infrastructure_error" or r["returncode"] != 0
            else "NOT SOLVED"
        )
        rows.append(
            f"| [{cid}]({cid}/index.html) | {outcome} | {r['summary'].get('api_calls', 0)} | {r['summary'].get('control_ticks', 0)} |"
        )
        title = html.escape(cid + " · " + outcome)
        options.append(f'<option value="{cid}/index.html">{title}</option>')
        if count:
            cards.append(
                f"### {cid}\n\n{outcome} · {r['summary'].get('api_calls', 0)} API calls · [raw trace]({cid}/events.jsonl)\n\n![Dual-view recorded execution]({cid}/replay.gif)\n"
            )
    (dest / "README.md").write_text(
        "# Twenty-task GPT pilot\n\nAll 20 planned attempts, including failures. Three model decisions / 360 control ticks per task. Seed 0; LIBERO official initial state 0. Single-tool mode, gpt-6-sol via AiXor. This is a short pilot, not an official benchmark result. GIFs are accelerated observation playback; no interpolated frames. Provider routing metadata omitted; model arguments and tool results preserved.\n\n[Interactive 20-task selector](index.html) · [machine-readable report](report.json)\n\n| Task | Outcome | API calls | Control ticks |\n|---|---|---:|---:|\n"
        + "\n".join(rows)
        + "\n\n"
        + "\n".join(cards)
    )
    (dest / "index.html").write_text(
        """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>20-task GPT pilot</title><style>body{margin:0;background:#09131b;color:#e5f1f4;font:15px system-ui}header{padding:20px 4vw}h1{margin:0 0 8px}p{color:#91a9b4}select{padding:12px;background:#10222d;color:#66e1bc;border:1px solid #3c6476;width:min(900px,100%)}iframe{width:100%;height:100vh;border:0}a{color:#66e1bc}</style><header><h1>20 tasks · actual GPT outputs and robot execution</h1><p>Fixed 3-decision pilot, not an official benchmark score. Both failures and successes are included. Each replay shows two cameras, model calls, pixel projection and measured motion.</p><select id="task" aria-label="Choose task">"""
        + "".join(options)
        + """</select> <a href="report.json">All results</a></header><iframe id="replay" title="Selected task trace"></iframe><script>const s=document.getElementById('task'),f=document.getElementById('replay');s.onchange=()=>{f.src=s.value};s.onchange();</script></html>"""
    )


if __name__ == "__main__":
    main()
