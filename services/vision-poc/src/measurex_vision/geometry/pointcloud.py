"""Back-projection of pixels/depth into a 3D point cloud (camera frame, metres)."""

from __future__ import annotations

import numpy as np

from .intrinsics import CameraIntrinsics


def backproject(u, v, z, intr: CameraIntrinsics) -> np.ndarray:
    """Back-project pixel(s) ``(u, v)`` at depth ``z`` to 3D point(s).

    Scalars or equally shaped arrays. Returns ``(..., 3)``::

        X = (u - cx) * Z / fx
        Y = (v - cy) * Z / fy
        Z = depth
    """
    u = np.asarray(u, dtype=float)
    v = np.asarray(v, dtype=float)
    z = np.asarray(z, dtype=float)
    x = (u - intr.cx) * z / intr.fx
    y = (v - intr.cy) * z / intr.fy
    return np.stack([x, y, z], axis=-1)


def backproject_depth(
    depth_m: np.ndarray,
    intr: CameraIntrinsics,
    mask: np.ndarray | None = None,
) -> np.ndarray:
    """Turn a depth map into an ``(N, 3)`` cloud.

    Pixels that are non-finite or ``<= 0`` are dropped. If ``mask`` (bool, same
    shape) is given, only masked pixels are kept."""
    depth = np.asarray(depth_m, dtype=float)
    if depth.ndim != 2:
        raise ValueError("depth_m must be a 2D (H, W) array")
    h, w = depth.shape
    vs, us = np.mgrid[0:h, 0:w]
    valid = np.isfinite(depth) & (depth > 0)
    if mask is not None:
        mask = np.asarray(mask, dtype=bool)
        if mask.shape != depth.shape:
            raise ValueError("mask shape must match depth_m")
        valid &= mask
    return backproject(us[valid], vs[valid], depth[valid], intr)
