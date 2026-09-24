# Contributing

Start with a reproducible problem or a small adapter/tool improvement. The core must remain importable without simulators, model weights, API keys or GPU access.

```bash
pip install -e '.[dev,sim]'
ruff check .
pytest -q
python -m build
```

Use typed public interfaces and update documentation with behavior changes. Add regression tests for validation, execution or geometry changes. Avoid tests that merely repeat implementation details. Simulator checks must state exact dependencies, controller modes and whether an actual environment was exercised.

Never make CI require secrets or paid API calls. Never commit API keys, environment files, private task recordings, weights, datasets or machine-specific paths. Share synthetic/minimal failure cases whenever possible. Do not report mock tests as benchmark results or hide unsupported capabilities behind successful placeholder returns.

For a new tool, supply its schema, implementation, termination behavior, cancellation contract and result evidence. For a new adapter, include a sensor/controller smoke trace and document unsupported features. See [extension contracts](docs/extensions.md).

By submitting a contribution, you agree to license it under the repository's Apache-2.0 license and confirm you have the right to submit it. Third-party code/assets must retain their own notices; do not copy upstream implementation without attribution and license review.
