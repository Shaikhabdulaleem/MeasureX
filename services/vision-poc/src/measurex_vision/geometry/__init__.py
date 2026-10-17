"""Pure geometry layer — no GPU, no model inference, fully unit-testable.

Everything here works in float metres; conversion to integer millimetres
happens only in :func:`dimensions.metres_to_dimensions` at the contract edge.
"""

from .base import GeometryEstimator
from .bounding_box import OrientedBox, oriented_box
from .dimensions import extract_dimensions, metres_to_dimensions, normalize_axes_to_lwh
from .intrinsics import CameraIntrinsics
from .pointcloud import backproject, backproject_depth

__all__ = [
    "CameraIntrinsics",
    "GeometryEstimator",
    "OrientedBox",
    "backproject",
    "backproject_depth",
    "extract_dimensions",
    "metres_to_dimensions",
    "normalize_axes_to_lwh",
    "oriented_box",
]
