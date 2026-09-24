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


def test_upright_rgbd_preserves_world_points_and_aligns_pixels():
    from embodied_harness.geometry import rotate_rgbd_180

    rgb = np.arange(5 * 7 * 3, dtype=np.uint8).reshape(5, 7, 3)
    depth = np.arange(35, dtype=float).reshape(5, 7) / 100 + 0.5
    K = np.array([[130, 0, 3.5], [0, 110, 2.5], [0, 0, 1.0]])
    T = np.eye(4)
    T[:3, 3] = [0.2, -0.8, 0.5]
    new_rgb, new_depth, new_K, new_T = rotate_rgbd_180(rgb, depth, K, T)
    for u, v in [(0, 0), (2, 3), (6, 4)]:
        p = [6 - u, 4 - v]
        np.testing.assert_array_equal(new_rgb[p[1], p[0]], rgb[v, u])
        np.testing.assert_allclose(
            backproject([u, v], depth, K, T), backproject(p, new_depth, new_K, new_T)
        )
    np.testing.assert_allclose(np.linalg.det(new_T[:3, :3]), 1)
