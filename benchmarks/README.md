# Reproducible manifests

Each case freezes environment config, task instruction, seed and case ID. The runner isolates simulator processes, keeps all failed attempts, applies a wall-time limit, and refuses to overwrite any run directory. API credentials are inherited from the environment and not saved in manifests.

```bash
python scripts/run_benchmark.py --manifest benchmarks/basic-20-live.json \
  --runtimes /path/to/runtimes.json --out runs/basic-20 \
  --mode run --workers 2 --timeout 400 --model YOUR_MODEL \
  --stream --max-decisions 3 --max-control-ticks 360 --plan-mode single
```

Example runtime map (use absolute paths; simulator dependencies remain separate):

```json
{
  "metaworld": {"python": "/envs/metaworld/bin/python"},
  "libero": {
    "python": "/envs/libero/bin/python",
    "env": {"PYTHONPATH": "/src/LIBERO:/src/embodied-harness/src", "LIBERO_CONFIG_PATH": "/config/libero"}
  }
}
```

| Manifest | Coverage | Meaning |
|---|---|---|
| `libero-all-smoke.json` | 130 tasks across Spatial, Object, Goal, Long/10 and 90; official initial state 0 | Interface sweep, including the 90-task training suite; not a held-out success score |
| `metaworld-all-smoke.json` | All 50 task types, each MT1-generated instance 0, seed 0 | Interface sweep; not official MT50 evaluation |
| `basic-20-live.json` | 10 MetaWorld task types + 10 LIBERO Spatial tasks | Short GPT pilot with fixed budget; not a leaderboard result |
| `robocasa-robotwin-smoke.json` | Three cases each | Prepared integration manifest; do not claim passed without results |

A smoke pass requires images, real control ticks, a successful motion tool and a final trace. A task success requires a valid model episode and the simulator's final success predicate. They are different metrics. `run` exit status indicates process/integration health, not that the task was solved. An API-failed attempt remains in the all-attempts denominator.

For official evaluations, use each benchmark's prescribed split, initial-state counts, horizon and aggregation, and record runtime versions and source commit. The checked-in short pilot does not meet those protocols.
