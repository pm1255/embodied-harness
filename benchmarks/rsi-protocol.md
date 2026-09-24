# RSI scenario benchmark protocol

The complete generated benchmark is published under `docs/rsi/experiment-v1/benchmark.json` after discovery and validation finish. Its `content.cases` is the executable scenario manifest; the outer `sha256` hashes canonical JSON (`sort_keys=True`, Python default separators). The same scheme seals the protocol and memory/skill bundles.

To reproduce an **evaluation**, use the frozen manifest rather than asking the designer to generate replacement tasks. Use the same MetaWorld 3.1.1 / MuJoCo 3.3.0 runtime, canonical task instructions in `rsi.experiment.CATALOG`, task indices, camera/light values, seeds, model configuration and budgets. Model calls are stochastic: same inputs do not promise identical model output. Repeating an episode is a new attempt that must be logged separately.

`python -m embodied_harness.rsi.replay --benchmark docs/rsi/experiment-v1/benchmark.json --output runs/rsi-reproduction --model MODEL --base-url URL`

This command only replays the four frozen ablation arms. It never calls the task designer, updates memory, selects new skills, or uses test outcomes to improve a later arm. Run the full discovery protocol separately if testing whether the curriculum can be regenerated.

The original benchmark uses 6 selected native task families × 2 held-out scene seeds × 4 arms = 48 test episodes. The 24 discovery/validation episodes are not test performance. Candidate and approved bundles are distinguished. A rejected candidate is still a legitimate experimental treatment, not a production-approved skill library.

Do not equate lower call count with improvement when an agent gives up early. Report native success and failures first, calls and wall time second. Failed API responses may omit usage: reported token totals are lower bounds when that happens.
