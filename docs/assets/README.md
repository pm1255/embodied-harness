# README evidence assets

`metaworld.gif` and `libero.gif` are annotated playback of the checked-in simulator observations, not generated robot videos. Frames retain the recorded camera orientation. Playback is accelerated and event-based, not real time.

Rebuild from the repository root with Pillow installed:

```bash
pip install -e '.[sim]'
python scripts/render_readme_examples.py
```

The script reads `docs/live-tests/*/events.jsonl`, the referenced RGB images and summaries. It writes the GIFs, final-frame PNGs, a frame-count manifest and `examples/recorded/*.json`. The JSON examples retain exact recorded model arguments; the graphic displays rounded geometry values. Yellow rings appear only when the model's referenced observation and camera match the displayed image. No API call or simulator run is made. Fonts may differ between operating systems.

Historical MetaWorld GIFs rotate the native raster 180° for display, including pixel overlays. The raw recorded model JSON stays in its original coordinates. New runs rotate RGB, depth and calibration together before model inference; see `raster_rotation_deg` in camera records.
