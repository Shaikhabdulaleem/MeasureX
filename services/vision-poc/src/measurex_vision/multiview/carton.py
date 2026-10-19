"""Gravity-fixed carton geometry from a metric visual-hull cloud.

Replaces M8's unconstrained PCA/OBB (banned for M9, see the ADR). Gravity is the
authoritative vertical: height is the extent along it; L/W come from a robust 2D
oriented footprint (convex hull + minimum-area rectangle) of the points projected
onto the horizontal plane. Nothing here reads a known carton size, and no
percentile is chosen to fit a particular box.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from ..contracts import Dimensions
from ..geometry.dimensions import metres_to_dimensions


@dataclass(frozen=True)
class CartonGeometry:
    dimensions: Dimensions
    length_m: float
    width_m: float
    height_m: float


def up_from_gravity(gravity_world: np.ndarray) -> np.ndarray:
    """Unit "up" = the negated, normalised gravity vector."""
    g = np.asarray(gravity_world, dtype=float)
    return -g / np.linalg.norm(g)


def horizontal_basis(up: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Two orthonormal axes spanning the plane perpendicular to ``up``."""
    up = up / np.linalg.norm(up)
    seed = np.array([1.0, 0.0, 0.0]) if abs(up[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    e1 = seed - (seed @ up) * up
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(up, e1)
    return e1, e2


def largest_component(points_m: np.ndarray, voxel_m: float) -> np.ndarray:
    """Keep the largest 6-connected voxel component; drop isolated outlier voxels.

    Points are voxel centres on a regular grid, so adjacency is exact via integer
    grid indices. On a clean convex hull this returns everything; it only matters
    when a stray mask lets through a detached blob."""
    pts = np.asarray(points_m, dtype=float)
    if pts.shape[0] == 0:
        return pts
    origin = pts.min(axis=0)
    idx = np.round((pts - origin) / voxel_m).astype(np.int64)
    key_to_row = {tuple(k): i for i, k in enumerate(idx)}
    occupied = set(key_to_row)
    seen: set[tuple[int, int, int]] = set()
    neighbours = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]
    best: list[int] = []
    for start in occupied:
        if start in seen:
            continue
        comp: list[int] = []
        q = deque([start])
        seen.add(start)
        while q:
            c = q.popleft()
            comp.append(key_to_row[c])
            for dx, dy, dz in neighbours:
                nb = (c[0] + dx, c[1] + dy, c[2] + dz)
                if nb in occupied and nb not in seen:
                    seen.add(nb)
                    q.append(nb)
        if len(comp) > len(best):
            best = comp
    return pts[best]


def _convex_hull_2d(pts: np.ndarray) -> np.ndarray:
    """CCW convex hull vertices of 2D points via Andrew's monotone chain."""
    p = np.unique(pts, axis=0)
    if p.shape[0] <= 2:
        return p
    p = p[np.lexsort((p[:, 1], p[:, 0]))]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[np.ndarray] = []
    for q in p:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], q) <= 0:
            lower.pop()
        lower.append(q)
    upper: list[np.ndarray] = []
    for q in p[::-1]:
        while len(upper) >= 2 and cross(upper[-2], upper[-1], q) <= 0:
            upper.pop()
        upper.append(q)
    return np.array(lower[:-1] + upper[:-1])


def min_area_rect(pts2d: np.ndarray) -> tuple[float, float]:
    """Side lengths ``(long, short)`` of the minimum-area enclosing rectangle.

    Rotating calipers over the convex-hull edges: the optimal rectangle is aligned
    with one hull edge, so each edge is tried as an axis and the smallest-area box
    wins. Principled and orientation-free — no axis-aligned or GT-fit assumption."""
    hull = _convex_hull_2d(pts2d)
    if hull.shape[0] < 3:
        span = pts2d.max(axis=0) - pts2d.min(axis=0)
        return float(max(span)), float(min(span))
    best_area = np.inf
    best = (0.0, 0.0)
    n = hull.shape[0]
    for i in range(n):
        edge = hull[(i + 1) % n] - hull[i]
        norm = np.linalg.norm(edge)
        if norm < 1e-12:
            continue
        ex = edge / norm
        ey = np.array([-ex[1], ex[0]])
        proj_x = hull @ ex
        proj_y = hull @ ey
        dx = proj_x.max() - proj_x.min()
        dy = proj_y.max() - proj_y.min()
        area = dx * dy
        if area < best_area:
            best_area = area
            best = (float(max(dx, dy)), float(min(dx, dy)))
    return best


def carton_dimensions(
    points_m: np.ndarray,
    gravity_world: np.ndarray,
    voxel_m: float,
    support_plane: dict | None = None,
) -> CartonGeometry:
    """L/W/H from a visual-hull cloud with gravity as the fixed vertical.

    Gravity is authoritative for the vertical direction. L/W are the
    minimum-area footprint sides of the points projected onto the horizontal
    plane. Height is the vertical extent.

    **Support plane (optional, Phase 7).** A carton sits on a table, so no camera
    sees its underside and an above-only visual hull cannot cap the bottom face.
    When the capture provides a metric support plane (``{"normal", "offset"}``,
    world metres), voxels below it are rejected and height is the extent *above*
    the plane — physically the carton height. Metric scale still comes from the
    poses, never from the plane. Without a support plane, height is the full hull
    extent, which over-reports for above-only captures (a documented limitation).

    Each extent is corrected by the voxel discretisation: occupied voxel *centres*
    sit ~half a voxel inside each true face. L/W get ``+voxel`` (both faces inset);
    support-pinned height gets ``+voxel/2`` (only the top face is inset — the
    bottom is the exact plane). GT-independent."""
    pts = np.asarray(points_m, dtype=float)
    if pts.shape[0] < 4:
        raise ValueError("need >= 4 points for carton geometry")
    up = up_from_gravity(gravity_world)
    e1, e2 = horizontal_basis(up)

    if support_plane is not None:
        n = np.asarray(support_plane["normal"], dtype=float)
        n = n / np.linalg.norm(n)
        d = float(support_plane["offset"])
        above = pts @ n + d
        keep = above >= -voxel_m  # tolerate one voxel of discretisation below
        pts = pts[keep]
        if pts.shape[0] < 4:
            raise ValueError("no hull support above the support plane")
        height_m = float((pts @ n + d).max()) + voxel_m / 2.0
    else:
        heights = pts @ up
        height_m = float(heights.max() - heights.min()) + voxel_m

    footprint = np.stack([pts @ e1, pts @ e2], axis=-1)
    long_m, short_m = min_area_rect(footprint)
    length_m, width_m = long_m + voxel_m, short_m + voxel_m

    return CartonGeometry(
        dimensions=metres_to_dimensions(length_m, width_m, height_m),
        length_m=length_m,
        width_m=width_m,
        height_m=height_m,
    )
