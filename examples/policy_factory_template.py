"""Adapt an existing policy to the strict RoboTwin bridge.

Copy this module into your deployment and supply your trained policy's input and
normalization adapter. This template is deliberately not an executable model:
no random/constant actions are substituted when a checkpoint is absent.

See docs/rsi-design.md for the actual checkpoint-backed integration and evidence.
"""


def create():
    raise NotImplementedError(
        "Provide a checkpoint-backed factory returning .metadata and .infer(message). "
        "metadata requires model, checkpoint_sha256, contract='robotwin_aloha_qpos14_v1'. "
        "message contains camera_slots (0=head,1=left,2=right uint8 RGB), state (qpos14), "
        "instruction, case_id, seed, query. Return {'actions': Hx14 absolute native qpos}. "
        "H is 1..50, grippers are channels 6 and 13, robot joints use radians. "
        "Use the checkpoint's training-time normalization and image transforms."
    )
