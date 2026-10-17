"""Tests for RANSAC plane fitting and up-axis orientation."""

from __future__ import annotations

import numpy as np

from measurex_vision.geometry.planes import (
    fit_plane_ransac,
    oriented_up,
    point_plane_distance,
)


def _tilted_plane_points(normal, seed=0, n=500):
    normal = np.asarray(normal, float)
    normal = normal / np.linalg.norm(normal)
    rng = np.random.default_rng(seed)
    # Two in-plane basis vectors.
    a = np.cross(normal, [1, 0, 0])
    if np.linalg.norm(a) < 1e-6:
        a = np.cross(normal, [0, 1, 0])
    a = a / np.linalg.norm(a)
    b = np.cross(normal, a)
    uv = rng.uniform(-1, 1, size=(n, 2))
    pts = uv[:, :1] * a + uv[:, 1:] * b
    pts += rng.normal(scale=0.002, size=pts.shape)  # small noise within threshold
    return pts, normal


def test_fit_plane_recovers_normal():
    pts, normal = _tilted_plane_points([0.1, 0.2, 1.0])
    plane = fit_plane_ransac(pts, threshold_m=0.01, seed=1)
    # Normal recovered up to sign.
    assert abs(abs(float(plane.normal @ normal)) - 1.0) < 1e-2
    assert plane.inlier_mask.mean() > 0.9


def test_oriented_up_points_toward_cloud():
    pts, _ = _tilted_plane_points([0.0, 0.0, 1.0])
    # Add object points clearly on the +Z side.
    obj = np.array([[0.0, 0.0, 0.3], [0.05, 0.0, 0.25]])
    cloud = np.concatenate([pts, obj], axis=0)
    plane = fit_plane_ransac(cloud, threshold_m=0.01, seed=2)
    up = oriented_up(plane, cloud)
    # Object points must be on the positive side along `up`.
    assert np.all(point_plane_distance(obj, plane) * np.sign(up @ plane.normal) > 0)
