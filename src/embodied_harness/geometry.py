"""Explicit camera conventions; never use demonstration target depth."""

from __future__ import annotations

import numpy as np


def backproject(pixel, depth_m, intrinsic, world_from_camera):
    u, v = pixel
    depth_m = np.asarray(depth_m).squeeze()
    if depth_m.ndim != 2 or not (0 <= v < depth_m.shape[0] and 0 <= u < depth_m.shape[1]):
        raise ValueError("Pixel outside depth image")
    z = float(depth_m[v, u])
    if not np.isfinite(z) or z <= 0 or z > 10:
        raise ValueError("Missing or out-of-range surface depth")
    xyz = np.linalg.solve(np.asarray(intrinsic), np.array([u, v, 1.0])) * z
    world = np.asarray(world_from_camera) @ np.r_[xyz, 1.0]
    if not np.isfinite(world).all():
        raise ValueError("Invalid camera calibration")
    return world[:3].tolist()


def mujoco_camera(model, data, camera, width, height):
    """Top-left raster; optical camera axes +X right, +Y down, +Z forward."""
    cid = (
        model.camera_name2id(camera)
        if hasattr(model, "camera_name2id")
        else model.camera(camera).id
    )
    f = height / (2 * np.tan(np.deg2rad(model.cam_fovy[cid]) / 2))
    intrinsic = np.array([[f, 0, width / 2], [0, f, height / 2], [0, 0, 1]])
    transform = np.eye(4)
    transform[:3, :3] = np.asarray(data.cam_xmat[cid]).reshape(3, 3) @ np.diag([1, -1, -1])
    transform[:3, 3] = data.cam_xpos[cid]
    return intrinsic, transform


class DepthCache:
    """Only the latest sensor snapshot is accepted; resets discard all targets."""

    def __init__(self):
        self.observation_id = None
        self.tick = None
        self.cameras = {}

    def begin(self, observation_id, tick):
        self.observation_id, self.tick, self.cameras = observation_id, tick, {}

    def project(self, observation_id, tick, camera, pixel):
        if observation_id != self.observation_id or tick != self.tick:
            raise ValueError("stale_observation: request a new image before projecting a pixel")
        if camera not in self.cameras:
            raise ValueError("Camera has no calibrated depth")
        return backproject(pixel, *self.cameras[camera])


def rotate_rgbd_180(rgb, depth, intrinsic, world_from_camera):
    """Roll a raster and its optical frame together; preserve every world ray."""
    height, width = depth.shape
    K = np.array(intrinsic, dtype=float, copy=True)
    T = np.array(world_from_camera, dtype=float, copy=True)
    # Pixel centers map (u, v) -> (width-1-u, height-1-v).
    K[0, 2], K[1, 2] = width - 1 - K[0, 2], height - 1 - K[1, 2]
    T[:3, :3] = T[:3, :3] @ np.diag([-1, -1, 1])
    return np.ascontiguousarray(rgb[::-1, ::-1]), np.ascontiguousarray(depth[::-1, ::-1]), K, T
