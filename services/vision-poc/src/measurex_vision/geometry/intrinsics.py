"""Pinhole camera intrinsics, forward projection, and scale-source resolution."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

import numpy as np

# Last-resort camera horizontal FOV when nothing better is known. Typical phone
# main camera; experimental until a device benchmark calibrates it.
DEFAULT_FALLBACK_FOV_DEG = 65.0


class IntrinsicsSource(str, Enum):
    """Where the focal/scale came from, best (most trustworthy) first."""

    EXPLICIT = "explicit"              # caller supplied real intrinsics
    EXIF = "exif"                      # focal from image EXIF
    DEVICE_PROFILE = "device_profile"  # known device/camera calibration
    DEPTH_MODEL = "depth_model"        # focal predicted by the depth model (e.g. Depth Pro)
    CONFIGURED_FOV = "configured_fov"  # a configured fallback FOV (assumed scale)
    ASSUMED = "assumed"                # built-in default FOV (assumed scale)


# Sources whose scale is an assumption, not a measurement. Confidence must be
# penalized for these — never hide scale uncertainty (M8 Step 5).
ASSUMED_SOURCES = frozenset({IntrinsicsSource.CONFIGURED_FOV, IntrinsicsSource.ASSUMED})


@dataclass(frozen=True)
class CameraIntrinsics:
    fx: float
    fy: float
    cx: float
    cy: float

    @classmethod
    def from_focal(cls, focal_px: float, width: int, height: int) -> CameraIntrinsics:
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


def _focal_from_hfov(width: int, hfov_deg: float) -> float:
    """Pinhole focal (px) for a horizontal field of view across ``width`` px."""
    if not 0.0 < hfov_deg < 180.0:
        raise ValueError("hfov_deg must be in (0, 180)")
    return (width / 2.0) / math.tan(math.radians(hfov_deg) / 2.0)


@dataclass(frozen=True)
class IntrinsicsResult:
    """Resolved intrinsics plus an honest record of where the scale came from."""

    intrinsics: CameraIntrinsics
    source: IntrinsicsSource
    assumed_fov_deg: float | None = None  # set only when source is FOV-derived

    @property
    def is_assumed(self) -> bool:
        return self.source in ASSUMED_SOURCES

    def to_dict(self) -> dict[str, object]:
        out: dict[str, object] = {
            "intrinsics_source": self.source.value,
            "intrinsics_assumed": self.is_assumed,
            "fx": self.intrinsics.fx,
            "fy": self.intrinsics.fy,
            "cx": self.intrinsics.cx,
            "cy": self.intrinsics.cy,
        }
        if self.assumed_fov_deg is not None:
            out["assumed_fov_deg"] = self.assumed_fov_deg
        return out


def resolve_intrinsics(
    width: int,
    height: int,
    *,
    explicit: CameraIntrinsics | None = None,
    exif_focal_px: float | None = None,
    device_profile_focal_px: float | None = None,
    depth_focal_px: float | None = None,
    fallback_fov_deg: float | None = None,
) -> IntrinsicsResult:
    """Resolve camera intrinsics from the best available scale source.

    Priority (M8 Step 5): caller-supplied intrinsics -> EXIF focal -> device
    profile -> depth-model-predicted focal -> configured fallback FOV -> assumed
    FOV. The result always reports its source; FOV-derived results are flagged
    ``is_assumed`` so the caller can penalize confidence. Scale uncertainty is
    never hidden.

    ``depth_focal_px`` must be passed only when the depth model genuinely
    *predicts* focal (Depth Pro); for an assumed-FOV model (Depth Anything V2)
    the caller passes ``None`` so resolution falls through to the FOV fallback.
    """
    if explicit is not None:
        return IntrinsicsResult(explicit, IntrinsicsSource.EXPLICIT)

    cx, cy = width / 2.0, height / 2.0

    for focal, source in (
        (exif_focal_px, IntrinsicsSource.EXIF),
        (device_profile_focal_px, IntrinsicsSource.DEVICE_PROFILE),
        (depth_focal_px, IntrinsicsSource.DEPTH_MODEL),
    ):
        if focal is not None and focal > 0:
            return IntrinsicsResult(
                CameraIntrinsics(fx=float(focal), fy=float(focal), cx=cx, cy=cy), source
            )

    # No measured scale left — fall back to a field-of-view assumption.
    if fallback_fov_deg is not None and fallback_fov_deg > 0:
        source = IntrinsicsSource.CONFIGURED_FOV
        fov = fallback_fov_deg
    else:
        source = IntrinsicsSource.ASSUMED
        fov = DEFAULT_FALLBACK_FOV_DEG
    focal = _focal_from_hfov(width, fov)
    return IntrinsicsResult(
        CameraIntrinsics(fx=focal, fy=focal, cx=cx, cy=cy), source, assumed_fov_deg=fov
    )
