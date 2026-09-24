# First live API diagnostics — 2026-09-24

These are small engineering tests through AiXor (`https://aixor.cc/v1`), using its advertised `gpt-6-sol` model ID. The upstream model identity was not independently verified. They are **not** an official LIBERO/MetaWorld benchmark or evidence that batching improves success or latency.

| Run | Task predicate | API calls | Control ticks | Wall time | Episode status |
|---|---|---:|---:|---:|---|
| MetaWorld reach-v3, seed 0, one-decision budget | **true** | 1 | 35 | 50.20s | decision budget exhausted, evaluated successful |
| LIBERO spatial task 0, seed 0, batch plan | **false** | 3 | 159 | 107.87s | infrastructure error on third response |

Inspect the [MetaWorld trace](metaworld/index.html) and [LIBERO trace](libero/index.html) by serving this directory. Both include two camera views, exact model tool arguments, pixel-to-world projection and controller samples. Playback is sampled observations, not full-rate video. Provider-internal IDs and attribution metadata were omitted from these public copies; model arguments and outcomes were preserved.

## What actually happened

MetaWorld: the model called `move_to_pixel` with pixel `[154,137]` in `corner`, `approach=surface`. Current RGB-D calibration produced `[-0.03683,0.86508,0.18571]` meters. The servo executed 35 ticks, ending 7.17mm from that surface target. The environment's final task predicate was true. The one-decision budget was selected before this run, after an earlier diagnostic had reached the goal but failed its subsequent API request. There was no model completion verdict and no success-predicate early stop. This is a selected engineering example, not an unbiased success-rate estimate.

LIBERO: the first plan contained four operations. Its first pixel motion completed. The next operation reused the pre-motion observation and was rejected as stale. After a new image, a surface approach stalled with 43.07mm target error. The third API response had failed status and no tool call. The bowl-placement predicate remained false. This exposes a real limitation: pixel surface movement is not a grasp-pose controller, and multiple image-dependent targets cannot currently survive movement in one batch.

The prompt was clarified after these tests to explicitly prohibit reusing pre-motion pixel observations later in a batch. That prompt change has unit validation but **has not been live re-evaluated**. The shipped code also adds explicit single-tool mode so future batch comparisons preserve raw primitive calls.

## All attempts, including failures

[all-attempts.json](all-attempts.json) retains all eight simulator attempts, comprising eleven API requests. Seven attempts ended with infrastructure errors. Five produced no robot motion; two produced motion before a later API failure. The remaining one-decision run satisfied the task predicate. Do not quote “100% success” from this sequence or exclude the reliability problem from a deployment assessment.

Separate protocol diagnostics tested text Responses, text Chat Completions and image-plus-function input. Streaming text and image/function requests returned successfully; non-streaming text timed out. Full robot requests showed timeouts or failed terminal responses in both tested protocols, while some streaming requests completed. This does not isolate a causal protocol/schema fault. One schema-only diagnostic was rejected by the gateway as a short-input probe. No hidden retries were used. Failed requests may still incur provider billing; available token counters are not complete billing records.

## Reproduce selected configurations

Set your own `OPENAI_API_KEY` and `OPENAI_BASE_URL`. Use the compatible simulator environments described in [validation](../validation.md).

```bash
embodied-harness run --env metaworld --config examples/metaworld.json \
  --task 'Move the gripper to the red spherical target marker. This is a reach task; do not grasp the marker.' \
  --model gpt-6-sol --stream --plan-mode single --reasoning-effort low \
  --api-timeout 240 --max-decisions 1 --max-control-ticks 600 --seed 0 \
  --out runs/my-metaworld-check

embodied-harness run --env libero --config examples/libero.json \
  --task 'pick up the black bowl between the plate and the ramekin and place it on the plate' \
  --model gpt-6-sol --stream --plan-mode batch --reasoning-effort low \
  --api-timeout 240 --max-decisions 4 --max-control-ticks 600 --seed 0 \
  --out runs/my-libero-check
```

These tests ran on local macOS simulator environments. Source code and public traces are mirrored to the user's training/evaluation servers; that transfer does not constitute a GPU-cluster evaluation.
