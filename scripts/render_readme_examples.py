"""Build GitHub-visible GIFs and exact JSON examples from checked-in real traces.

Requires Pillow (the sim extra). No generated/interpolated robot images or new API calls.
Run from any directory: python scripts/render_readme_examples.py
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
BG, PANEL, INK, MUTED, MINT, AMBER = (
    "#09131b",
    "#10222d",
    "#e5f1f4",
    "#91a9b4",
    "#66e1bc",
    "#ffd185",
)


def font(size):
    for name in ("DejaVuSans.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def render(label):
    src = ROOT / "docs/live-tests" / label
    events = [json.loads(line) for line in (src / "events.jsonl").read_text().splitlines()]
    summary = json.loads((src / "summary.json").read_text())
    observation, call, geometry, result = None, None, None, None
    ticks = calls = 0
    frames, durations, examples = [], [], []
    interesting = {"observation", "model_response", "geometry", "tool_end", "episode_end"}
    for event in events:
        kind, data = event["kind"], event["payload"]
        if kind == "model_request":
            calls += 1
        if kind == "control_tick":
            ticks += 1
        if kind == "observation":
            observation = data
        elif kind == "model_response":
            result = None
            for raw in data.get("calls", []):
                args = json.loads(raw["arguments"])
                examples.append({"event_seq": event["seq"], "name": raw["name"], "arguments": args})
                call = (
                    args["steps"][0]
                    if raw["name"] == "submit_plan"
                    else {"tool": raw["name"], "arguments": args}
                )
        elif kind == "geometry":
            geometry = data
        elif kind == "tool_end":
            result = data
        if kind not in interesting or observation is None:
            continue
        im = Image.new("RGB", (800, 664), BG)
        d = ImageDraw.Draw(im)
        d.text((24, 18), f"{label.upper()} / REAL GPT TOOL EXECUTION", font=font(23), fill=INK)
        final = "TRUE" if summary["environment_success"] else "FALSE"
        d.text(
            (24, 54),
            f"Final task predicate: {final} | {summary['api_calls']} API calls | "
            f"{summary['control_ticks']} control ticks",
            font=font(17),
            fill=MINT,
        )
        for i, camera in enumerate(observation["frames"][:2]):
            x, y = 24 + i * 388, 112
            with Image.open(src / camera["image_path"]) as original:
                image = original.convert("RGB")
                historical_rotation = label == "metaworld" and not camera.get("raster_rotation_deg")
                if historical_rotation:
                    image = image.transpose(Image.Transpose.ROTATE_180)
                image = image.resize((364, 364), Image.Resampling.NEAREST)
            im.paste(image, (x, y))
            d.text((x, 86), camera["name"], font=font(17), fill=MUTED)
            if call:
                a = call["arguments"]
                if (
                    a.get("observation_id") == observation["id"]
                    and a.get("camera") == camera["name"]
                ):
                    px, py = a["pixel"]
                    if historical_rotation:
                        px, py = camera["width"] - 1 - px, camera["height"] - 1 - py
                    xx = x + px * 364 / camera["width"]
                    yy = y + py * 364 / camera["height"]
                    d.ellipse((xx - 8, yy - 8, xx + 8, yy + 8), outline=AMBER, width=3)
        d.rounded_rectangle((24, 490, 776, 626), radius=10, fill=PANEL)
        if call:
            a = call["arguments"]
            args = f"pixel={a['pixel']}, {a['approach']}" if "pixel" in a else str(a)
            model = f"MODEL  {call['tool']}({args})"
        else:
            model = "MODEL  Awaiting first decision"
        d.text((38, 501), model, font=font(17), fill=MINT)
        xyz = ", ".join(f"{v:.5f}" for v in geometry["target_m"]) if geometry else "pending"
        d.text((38, 531), f"RGB-D  World target (m): [{xyz}]", font=font(17), fill=INK)
        state = result.get("error_code") or result["status"] if result else "in progress"
        if kind == "episode_end":
            state = summary["status"]
        d.text(
            (38, 560),
            f"EXECUTION  {ticks} ticks | {calls} API requests | {state}",
            font=font(16),
            fill=AMBER,
        )
        d.text(
            (38, 590),
            f"Trace event {event['seq']}: {kind} | sensor t={observation['timestamp_s']:.2f}s",
            font=font(15),
            fill=MUTED,
        )
        d.text(
            (24, 637),
            "Recorded frames; display rotated 180 deg; JSON keeps original pixels."
            if label == "metaworld"
            else "Recorded observations; accelerated playback. No frame interpolation.",
            font=font(16),
            fill=MUTED,
        )
        frames.append(im)
        durations.append(1000 if kind in ("model_response", "tool_end") else 450)
    durations[0], durations[-1] = 1600, 3200
    dest = ROOT / "docs/assets"
    dest.mkdir(exist_ok=True)
    frames[0].save(
        dest / f"{label}.gif",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=2,
    )
    frames[-1].save(dest / f"{label}-result.png")
    (ROOT / "examples/recorded" / f"{label}.json").write_text(
        json.dumps(
            {
                "source": f"docs/live-tests/{label}/events.jsonl",
                "note": "Exact recorded model arguments; observation IDs belong to this episode only.",
                "model_calls": examples,
                "geometry_events": [e["payload"] for e in events if e["kind"] == "geometry"],
                "tool_results": [e["payload"] for e in events if e["kind"] == "tool_end"],
                "summary": summary,
            },
            indent=2,
        )
        + "\n"
    )
    return {
        "source_events": len(events),
        "gif_frames": len(frames),
        "observations": sum(e["kind"] == "observation" for e in events),
    }


if __name__ == "__main__":
    counts = {label: render(label) for label in ("metaworld", "libero")}
    (ROOT / "docs/assets/manifest.json").write_text(json.dumps(counts, indent=2) + "\n")
    print(json.dumps(counts))
