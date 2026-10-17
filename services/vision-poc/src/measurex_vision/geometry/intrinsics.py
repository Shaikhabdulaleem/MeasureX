"""Pinhole camera intrinsics and forward projection."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class CameraIntrinsics:
    fx: float
    fy: float
    cx: float
    cy: float

    @classmethod
    def from_focal(cls, focal_px: float, width: int, height: int) -> "CameraIntrinsics":
        """Build intrinsics from a single focal estimate.

        POC default when only one focal length is predicted: ``fx == fy`` and the
        principal point at the image centre. The caller records this assumption in
        diagnostics (VISION_ENGINE_POC.md §5)."""
        if focal_px <= 0:
            raise ValueError("focal_px must be > 0")
        return cls(fx=float(focal_px), fy=float(focal_px), cx=width / 2.0, cy=height / 2.0)

    def project(self, points_m: np.ndarray) -> np.ndarray:
        """Project camera-frame 3D points (..., 3) in metres to pixels (..., 2).

        Inverse of :func:`pointcloud.backproject`. Requires Z > 0."""
        p = np.asarray(points_m, dtype=float)
        z = p[..., 2]
        if np.any(z <= 0):
            raise ValueError("all points must have Z > 0 to project")
        u = self.fx * p[..., 0] / z + self.cx
        v = self.fy * p[..., 1] / z + self.cy
        return np.stack([u, v], axis=-1)
