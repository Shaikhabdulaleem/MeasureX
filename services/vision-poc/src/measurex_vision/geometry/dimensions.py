"""Axis/orientation normalization and L/W/H extraction."""

from __future__ import annotations

import numpy as np

from ..contracts import Dimensions
from .bounding_box import oriented_box

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
