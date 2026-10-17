"""Oriented bounding box from a point cloud."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class OrientedBox:
    center: np.ndarray   # (3,) box centre
    axes: np.ndarray     # (3, 3) unit axis vectors as columns
    extents: np.ndarray  # (3,) full side lengths, aligned with the axis columns


def oriented_box(points_m: np.ndarray) -> OrientedBox:
    """Fit an oriented box to an ``(N, 3)`` cloud via PCA of the point covariance.

    Exact for cuboid surface samples with distinct edge lengths (the synthetic
    test case). shortcut: PCA axes, not a minimum-volume fit — near-equal edge
    lengths are rotationally degenerate and partial/noisy clouds drift. Upgrade
    to Open3D ``get_minimal_oriented_bounding_box`` for real captures.
    """
    p = np.asarray(points_m, dtype=float)
    if p.ndim != 2 or p.shape[1] != 3 or p.shape[0] < 3:
        raise ValueError("points_m must be (N>=3, 3)")

    mean = p.mean(axis=0)
    centered = p - mean
    cov = np.cov(centered, rowvar=False)
    # eigh: symmetric cov -> orthonormal eigenvectors as columns.
    _, axes = np.linalg.eigh(cov)

    projected = centered @ axes
    lo = projected.min(axis=0)
    hi = projected.max(axis=0)
    extents = hi - lo
    center = mean + axes @ ((hi + lo) / 2.0)
    return OrientedBox(center=center, axes=axes, extents=extents)
