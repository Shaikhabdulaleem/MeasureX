"""Pure geometry layer — no GPU, no model inference, fully unit-testable.

Everything here works in float metres; conversion to integer millimetres
happens only in :func:`dimensions.metres_to_dimensions` at the contract edge.
"""

from .base import GeometryEstimator
from .bounding_box import OrientedBox, oriented_box
from .dimensions import (
    extract_dimensions,
    extract_supported_dimensions,
    metres_to_dimensions,
    normalize_axes_to_lwh,
    segment_object_points,
)
from .intrinsics import CameraIntrinsics
from .planes import Plane, fit_plane_ransac, oriented_up, point_plane_distance
from .pointcloud import backproject, backproject_depth

__all__ = [
    "CameraIntrinsics",
    "GeometryEstimator",
    "OrientedBox",
    "Plane",
    "backproject",
    "backproject_depth",
    "extract_dimensions",
    "extract_supported_dimensions",
    "fit_plane_ransac",
    "metres_to_dimensions",
    "normalize_axes_to_lwh",
    "oriented_box",
    "oriented_up",
    "point_plane_distance",
    "segment_object_points",
]
