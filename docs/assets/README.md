# README evidence assets

`metaworld.gif` and `libero.gif` are annotated playback of the checked-in simulator observations, not generated robot videos. Frames retain the recorded camera orientation. Playback is accelerated and event-based, not real time.

Rebuild from the repository root with Pillow installed:

```bash
pip install -e '.[sim]'
python scripts/render_readme_examples.py
```

The script reads `docs/live-tests/*/events.jsonl`, the referenced RGB images and summaries. It writes the GIFs, final-frame PNGs, a frame-count manifest and `examples/recorded/*.json`. The JSON examples retain exact recorded model arguments; the graphic displays rounded geometry values. Yellow rings appear only when the model's referenced observation and camera match the displayed image. No API call or simulator run is made. Fonts may differ between operating systems.
