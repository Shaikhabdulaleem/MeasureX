"""M2 pipeline: image -> detect -> segment -> gate -> depth -> masked cloud.

Stops at the masked point cloud (box fit + L/W/H are a later milestone). Reuses
the M0 geometry (`backproject_depth`, `CameraIntrinsics`) and M1 depth."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .contracts import Diagnostics, MeasurementFailure
from .depth.base import DepthEstimator, DepthResult
from .detection.base import Detection, Detector
from .geometry import CameraIntrinsics, backproject_depth
from .quality.mask_checks import validate_mask
from .segmentation.base import Segmenter


@dataclass(frozen=True)
class MaskedCloud:
    points_m: np.ndarray       # (N, 3) camera-frame metres
    mask: np.ndarray           # (H, W) bool
    detection: Detection
    depth: DepthResult
    diagnostics: Diagnostics = field(default_factory=Diagnostics)


MaskedCloudResult = MaskedCloud | MeasurementFailure


def build_masked_cloud(
    image: np.ndarray,
    *,
    detector: Detector,
    segmenter: Segmenter,
    depth: DepthEstimator,
) -> MaskedCloudResult:
    """Run the M2 pipeline; return a MaskedCloud or a typed MeasurementFailure."""
    from .contracts import FailureCode

    detections = detector.detect(image)
    if not detections:
        return MeasurementFailure(failure_code=FailureCode.NO_TARGET)
    target = detector.select_target(detections)

    mask = segmenter.segment(image, target.bbox_xyxy)
    gate = validate_mask(mask)
    if gate is not None:
        return MeasurementFailure(failure_code=gate)

    depth_result = depth.estimate(image)
    h, w = depth_result.depth_m.shape
    intr = CameraIntrinsics.from_focal(depth_result.focal_px, w, h)
    points = backproject_depth(depth_result.depth_m, intr, mask=mask)
    if points.shape[0] < 50:  # not enough 3D support to measure anything
        return MeasurementFailure(failure_code=FailureCode.POINTCLOUD_SPARSE)

    diagnostics = Diagnostics(
        extra={
            "mask_area_ratio": float(mask.mean()),
            "point_count": int(points.shape[0]),
            "depth_valid_ratio": depth_result.valid_ratio,
            "focal_px": depth_result.focal_px,
            "detector_reason": target.reason,
        }
    )
    return MaskedCloud(
        points_m=points, mask=mask, detection=target, depth=depth_result, diagnostics=diagnostics
    )
