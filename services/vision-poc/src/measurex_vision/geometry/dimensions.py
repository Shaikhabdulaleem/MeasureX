"""Axis/orientation normalization and L/W/H extraction."""

from __future__ import annotations

import numpy as np

from ..contracts import Dimensions
from .bounding_box import oriented_box
from .planes import Plane, point_plane_distance

# World up-axis. The real pipeline derives this from the floor/support plane;
# synthetic tests pass it explicitly.
UP = (0.0, 0.0, 1.0)


def normalize_axes_to_lwh(
    extents: np.ndarray,
    axes: np.ndarray,
    up: tuple[float, float, float] = UP,
) -> tuple[float, float, float]:
    """Map three box extents to ``(length, width, height)`` in the same units.

    Height is the extent of the axis most aligned with ``up``; of the two
    horizontal axes, the longer is length and the shorter is width. So
    ``length >= width`` always holds (the MeasureX orientation rule)."""
    extents = np.asarray(extents, dtype=float)
    axes = np.asarray(axes, dtype=float)
    up_v = np.asarray(up, dtype=float)
    up_v = up_v / np.linalg.norm(up_v)

    alignment = np.abs(axes.T @ up_v)  # |cos angle| of each axis with up
    vertical = int(np.argmax(alignment))
    height = extents[vertical]

    horizontal = [i for i in range(3) if i != vertical]
    longer, shorter = sorted(horizontal, key=lambda i: extents[i], reverse=True)
    return float(extents[longer]), float(extents[shorter]), float(height)


def metres_to_dimensions(length_m: float, width_m: float, height_m: float) -> Dimensions:
    """Convert metres to integer millimetres — the one place this crossing happens.

    Rounds to the nearest mm. Billing's ceil-to-cm (PRD §7) is applied
    server-side later, not here."""

    def to_mm(metres: float) -> int:
        return round(metres * 1000.0)

    return Dimensions(
        length_mm=to_mm(length_m),
        width_mm=to_mm(width_m),
        height_mm=to_mm(height_m),
    )


def extract_dimensions(points_m: np.ndarray, up: tuple[float, float, float] = UP) -> Dimensions:
    """Full path: cloud -> oriented box -> normalized L/W/H -> integer mm."""
    box = oriented_box(points_m)
    length_m, width_m, height_m = normalize_axes_to_lwh(box.extents, box.axes, up)
    return metres_to_dimensions(length_m, width_m, height_m)


def segment_object_points(
    points_m: np.ndarray,
    plane: Plane,
    up: np.ndarray,
    *,
    band_m: float = 0.01,
    clip_percentile: float = 99.0,
) -> np.ndarray:
    """Keep points above the floor band; clip gross outliers by height percentile.

    shortcut: percentile clip only — no radius/statistical outlier removal yet;
    upgrade when real SAM 2 masks + Depth Pro clouds are benchmarked."""
    p = np.asarray(points_m, dtype=float)
    up = np.asarray(up, dtype=float)
    # Distance measured along `up` (= +/- the plane normal), so "above" is positive.
    height = point_plane_distance(p, plane) * np.sign(float(up @ plane.normal))
    above = height > band_m
    obj = p[above]
    if obj.shape[0] == 0:
        return obj
    h = height[above]
    cap = np.percentile(h, clip_percentile)
    return obj[h <= cap]


def extract_supported_dimensions(
    points_m: np.ndarray,
    plane: Plane,
    up: np.ndarray,
) -> Dimensions:
    """L/W from the horizontal oriented-box extents; height = max distance of the
    object points above the support plane (honest for a single-view base-on-floor
    capture). Metres -> integer mm at the edge."""
    obj = np.asarray(points_m, dtype=float)
    if obj.shape[0] < 3:
        raise ValueError("need >= 3 object points")
    box = oriented_box(obj)
    length_m, width_m, _ = normalize_axes_to_lwh(box.extents, box.axes, up)
    height_m = float(point_plane_distance(obj, plane).__abs__().max())
    return metres_to_dimensions(length_m, width_m, height_m)
