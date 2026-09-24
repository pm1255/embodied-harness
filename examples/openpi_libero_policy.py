"""Public-checkpoint π0.5-LIBERO factory for serve_policy_bridge.py.

Run in an official OpenPI environment. OPENPI_CHECKPOINT may point to an existing
local directory; otherwise official download.maybe_download is used. No API key
is needed. Model normalization and transforms remain owned by OpenPI.
"""
import hashlib
import os
from pathlib import Path


def checkpoint_hash(root):
    """Fingerprint relative paths and bytes of the resolved checkpoint tree."""
    result = hashlib.sha256()
    for path in sorted(Path(root).rglob('*')):
        if not path.is_file():
            continue
        result.update(path.relative_to(root).as_posix().encode() + b'\0')
        with path.open('rb') as stream:
            for data in iter(lambda: stream.read(8*1024*1024), b''):
                result.update(data)
        result.update(b'\0')
    return result.hexdigest()


def create():
    from openpi.policies import policy_config
    from openpi.shared import download
    from openpi.training import config
    from openpi_client import image_tools
    checkpoint = download.maybe_download(os.environ.get('OPENPI_CHECKPOINT',
                                                        'gs://openpi-assets/checkpoints/pi05_libero'))
    policy = policy_config.create_trained_policy(config.get_config('pi05_libero'), checkpoint)
    identity = checkpoint_hash(checkpoint)

    class Bridge:
        metadata = {'model':'pi05_libero', 'checkpoint_sha256':identity,
                    'checkpoint_hash_scheme':'sha256-relative-paths-and-file-bytes-v1',
                    'contract':'libero_franka_osc7_v1',
                    'source':'Physical-Intelligence/openpi official pi05_libero checkpoint'}

        def infer(self, message):
            import numpy as np
            images = message['camera_slots']
            payload = {'observation/image': image_tools.convert_to_uint8(
                image_tools.resize_with_pad(images['0'],224,224)),
                'observation/wrist_image': image_tools.convert_to_uint8(
                    image_tools.resize_with_pad(images['1'],224,224)),
                'observation/state':np.asarray(message['state'], dtype=np.float32),
                'prompt':message['instruction']}
            return {'actions':np.asarray(policy.infer(payload)['actions']).tolist()}
    return Bridge()
