"""Official OpenPI PyTorch LIBERO transforms behind our bounded policy endpoint.

Requires an operator-installed OpenPI runtime, its matching transformers patches,
and a LIBERO checkpoint with normalization statistics. No downloaded Python code
is executed by this module. Model weights are loaded through safetensors.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
from types import SimpleNamespace


def file_sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def create():
    print(json.dumps({"stage": "importing_policy_dependencies"}), flush=True)
    import jax
    import numpy as np
    import sentencepiece
    import torch
    from openpi import transforms
    from openpi.models import model as model_api, pi0_config, tokenizer
    from openpi.policies.libero_policy import LiberoInputs, LiberoOutputs
    from openpi.shared.normalize import load

    checkpoint = Path(os.environ["OPENPI_CHECKPOINT"])
    stats = Path(os.environ["OPENPI_NORM_STATS"])
    vocab = Path(os.environ["OPENPI_TOKENIZER"])
    print(json.dumps({"stage": "verifying_checkpoint"}), flush=True)
    actual_hash = file_sha256(checkpoint / "model.safetensors")
    if actual_hash != os.environ["VLA_CHECKPOINT_SHA256"]:
        raise ValueError("Checkpoint SHA256 mismatch")
    # Match the published pi05_libero OpenPI preset. Record this explicitly so
    # it is not conflated with other loaders or RPent's reported evaluations.
    config = pi0_config.Pi0Config(
        pi05=True, action_horizon=10, discrete_state_input=False, pytorch_compile_mode=None
    )
    print(json.dumps({"stage": "loading_model_parameters"}), flush=True)
    model = config.load_pytorch(
        SimpleNamespace(model=config), str(checkpoint / "model.safetensors")
    )
    model.paligemma_with_expert.to_bfloat16_for_selected_params("bfloat16")
    model = model.cuda().eval()
    print(json.dumps({"stage": "model_on_cuda"}), flush=True)
    # Use the official tokenize method with an already verified local vocabulary.
    tok = tokenizer.PaligemmaTokenizer.__new__(tokenizer.PaligemmaTokenizer)
    tok._max_len = config.max_token_len
    tok._tokenizer = sentencepiece.SentencePieceProcessor(model_proto=vocab.read_bytes())
    norm = load(stats.parent)
    inputs = transforms.compose(
        [
            LiberoInputs(config.model_type),
            transforms.Normalize(norm, use_quantiles=True),
            transforms.ResizeImages(224, 224),
            transforms.TokenizePrompt(tok, discrete_state_input=config.discrete_state_input),
            transforms.PadStatesAndActions(config.action_dim),
        ]
    )
    outputs = transforms.compose(
        [transforms.Unnormalize(norm, use_quantiles=True), LiberoOutputs()]
    )

    class Bridge:
        metadata = {
            "model": "RLinf-Pi05-LIBERO-130-fullshot-SFT",
            "contract": "libero_franka_osc7_v1",
            "checkpoint_sha256": actual_hash,
            "norm_stats_sha256": file_sha256(stats),
            "tokenizer_sha256": file_sha256(vocab),
            "loader": "OpenPI PI0Pytorch",
            "action_horizon": 10,
            "execute_horizon": 5,
            "denoising_steps": 10,
            "discrete_state_input": False,
            "quantile_normalization": True,
            "postprocess": "clip_normalized_OSC_to_minus1_plus1_and_binarize_gripper",
            "training_overlap": "LIBERO-130 fullshot SFT; standard LIBERO is in-domain",
            "upstream_benchmark_reproduction": False,
            "runtime_versions": {
                name: importlib.metadata.version(name)
                for name in ("torch", "transformers", "jax", "flax", "safetensors", "sentencepiece")
            },
        }

        @torch.inference_mode()
        def infer(self, message):
            data = inputs(
                {
                    "observation/state": np.asarray(message["state"], dtype=np.float32),
                    "observation/image": message["camera_slots"]["0"],
                    "observation/wrist_image": message["camera_slots"]["1"],
                    "prompt": message["instruction"],
                }
            )
            batch = jax.tree.map(lambda v: torch.from_numpy(np.array(v)).cuda()[None], data)
            # Paired, reset-specific noise; the GPT planner has no access to it.
            key = f"{message['case_id']}:{message['seed']}:{message['query']}".encode()
            generator = torch.Generator(device="cpu").manual_seed(
                int.from_bytes(hashlib.sha256(key).digest()[:8], "little") % (2**63)
            )
            noise = torch.randn((1, 10, 32), generator=generator).cuda()
            actions = model.sample_actions(
                "cuda", model_api.Observation.from_dict(batch), noise=noise, num_steps=10
            )
            values = outputs(
                {"state": batch["state"][0].cpu().numpy(), "actions": actions[0].cpu().numpy()}
            )["actions"][:5]
            if not np.isfinite(values).all():
                raise ValueError("Nonfinite policy action")
            normalized = np.clip(values, -1, 1)
            normalized[:, -1] = np.where(values[:, -1] >= 0, 1.0, -1.0)
            return {
                "actions": normalized.tolist(),
                "diagnostics": {
                    "raw_min": float(values.min()),
                    "raw_max": float(values.max()),
                    "clipped_values": int(np.sum(np.abs(values) > 1)),
                    "gripper_binarized": True,
                },
            }

    return Bridge()
