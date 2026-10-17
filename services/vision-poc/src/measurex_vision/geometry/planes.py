"""Support/floor-plane estimation — pure NumPy RANSAC.

The up-axis for a single-view capture comes from the floor the shipment sits on.
Kept dependency-free so it runs in CI; Open3D's segment_plane is an optional
later swap behind this module."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Plane:
    normal: np.ndarray   # (3,) unit normal
    offset: float        # d in normal·x + d = 0
    inlier_mask: np.ndarray  # (N,) bool


def point_plane_distance(points: np.ndarray, plane: Plane) -> np.ndarray:
    """Signed perpendicular distance of each point to the plane (metres)."""
    p = np.asarray(points, dtype=float)
    return p @ plane.normal + plane.offset


def _plane_from_points(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> tuple[np.ndarray, float] | None:
    normal = np.cross(b - a, c - a)
    norm = np.linalg.norm(normal)
    if norm < 1e-12:  # collinear sample
        return None
    normal = normal / norm
    return normal, float(-normal @ a)


def fit_plane_ransac(
    points: np.ndarray,
    *,
    threshold_m: float = 0.01,
    iterations: int = 200,
    seed: int = 0,
) -> Plane:
    """Fit the dominant plane by RANSAC, then least-squares refit on its inliers.

    shortcut: picks the plane with the most inliers and assumes it is the floor.
    A large flat object face can out-vote a small floor; disambiguating floor
    from face needs a gravity prior (IMU / camera-down direction) — add one
    before trusting this on arbitrary captures."""
    p = np.asarray(points, dtype=float)
    if p.ndim != 2 or p.shape[1] != 3 or p.shape[0] < 3:
        raise ValueError("points must be (N>=3, 3)")

    rng = np.random.default_rng(seed)
    best_normal: np.ndarray | None = None
    best_offset = 0.0
    best_count = -1
    n = p.shape[0]

    for _ in range(iterations):
        idx = rng.choice(n, size=3, replace=False)
        plane = _plane_from_points(p[idx[0]], p[idx[1]], p[idx[2]])
        if plane is None:
            continue
        normal, offset = plane
        dist = np.abs(p @ normal + offset)
        count = int((dist < threshold_m).sum())
        if count > best_count:
            best_count, best_normal, best_offset = count, normal, offset

    if best_normal is None:
        raise ValueError("RANSAC failed to find a plane")

    # Least-squares refit on the inliers for a stable normal.
    inliers = np.abs(p @ best_normal + best_offset) < threshold_m
    pts = p[inliers]
    centroid = pts.mean(axis=0)
    _, _, vh = np.linalg.svd(pts - centroid)
    normal = vh[-1]
    normal = normal / np.linalg.norm(normal)
    offset = float(-normal @ centroid)
    inlier_mask = np.abs(p @ normal + offset) < threshold_m
    return Plane(normal=normal, offset=offset, inlier_mask=inlier_mask)


def oriented_up(plane: Plane, points: np.ndarray) -> np.ndarray:
    """Plane normal flipped to point from the plane toward the cloud centroid
    (i.e. "up" off the floor)."""
    centroid = np.asarray(points, dtype=float).mean(axis=0)
    normal = plane.normal / np.linalg.norm(plane.normal)
    if (centroid @ normal + plane.offset) < 0:
        normal = -normal
    return normal
