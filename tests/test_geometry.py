import numpy as np
import pytest

from embodied_harness.geometry import DepthCache, backproject


def test_known_pinhole_ray_and_world_transform():
    depth = np.ones((5, 5)) * 2
    k = np.array([[2, 0, 2], [0, 2, 2], [0, 0, 1]])
    transform = np.eye(4)
    transform[:3, 3] = [1, 2, 3]
    assert backproject([3, 1], depth, k, transform) == [2, 1, 5]


@pytest.mark.parametrize(
    "pixel,depth", [([-1, 1], 1), ([7, 1], 1), ([1, 1], 0), ([1, 1], float("nan"))]
)
def test_invalid_surface_is_rejected(pixel, depth):
    with pytest.raises(ValueError):
        backproject(pixel, np.full((3, 3), depth), np.eye(3), np.eye(4))


def test_old_camera_snapshot_never_reused_after_motion_or_reset():
    cache = DepthCache()
    cache.begin("ep1:1", 0)
    cache.cameras["front"] = (np.ones((2, 2)), np.eye(3), np.eye(4))
    assert cache.project("ep1:1", 0, "front", [0, 0]) == [0, 0, 1]
    with pytest.raises(ValueError, match="stale"):
        cache.project("ep1:1", 1, "front", [0, 0])
    cache.begin("ep2:1", 0)
    with pytest.raises(ValueError, match="stale"):
        cache.project("ep1:1", 0, "front", [0, 0])
