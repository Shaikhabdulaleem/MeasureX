"""M2 pipeline: image -> detect -> segment -> gate -> depth -> masked cloud.

Stops at the masked point cloud (box fit + L/W/H are a later milestone). Reuses
the M0 geometry (`backproject_depth`, `CameraIntrinsics`) and M1 depth."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .contracts import (
    Diagnostics,
    MeasurementFailure,
    MeasurementResult,
    MeasurementSuccess,
)
from .depth.base import DepthEstimator, DepthResult
from .detection.base import Detection, Detector
from .geometry import (
    CameraIntrinsics,
    backproject_depth,
    extract_supported_dimensions,
    fit_plane_ransac,
    oriented_up,
    segment_object_points,
)
from .quality.confidence import ConfidenceEstimator, HeuristicConfidenceEstimator
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


# Minimum object points below which a box fit isn't trustworthy.
_MIN_OBJECT_POINTS = 30


def build_measurement(
    image: np.ndarray,
    *,
    detector: Detector,
    segmenter: Segmenter,
    depth: DepthEstimator,
    confidence: ConfidenceEstimator | None = None,
) -> MeasurementResult:
    """Full M3 path: masked cloud -> support plane -> object -> L/W/H + confidence."""
    cloud = build_masked_cloud(image, detector=detector, segmenter=segmenter, depth=depth)
    if isinstance(cloud, MeasurementFailure):
        return cloud
    return measure_from_cloud(cloud, confidence=confidence)


def measure_from_cloud(
    cloud: MaskedCloud,
    *,
    confidence: ConfidenceEstimator | None = None,
) -> MeasurementResult:
    """Fit the support plane and box to an already-built masked cloud.

    Separate from build_measurement so a --debug run can reuse one cloud for both
    the artifacts and the measurement (no double inference)."""
    from .contracts import FailureCode

    try:
        plane = fit_plane_ransac(cloud.points_m)
        up = oriented_up(plane, cloud.points_m)
        obj = segment_object_points(cloud.points_m, plane, up)
        if obj.shape[0] < _MIN_OBJECT_POINTS:
            return MeasurementFailure(failure_code=FailureCode.GEOMETRY_DEGENERATE)
        dimensions = extract_supported_dimensions(obj, plane, up)
    except (ValueError, np.linalg.LinAlgError):
        return MeasurementFailure(failure_code=FailureCode.GEOMETRY_DEGENERATE)

    evidence = {
        **cloud.diagnostics.extra,
        "plane_inlier_ratio": float(plane.inlier_mask.mean()),
        "object_point_count": int(obj.shape[0]),
    }
    estimator = confidence or HeuristicConfidenceEstimator()
    conf = estimator.estimate(evidence)

    return MeasurementSuccess(
        dimensions=dimensions,
        confidence=conf,
        diagnostics=Diagnostics(
            assumptions=["fx=fy, principal point at image centre"],
            extra=evidence,
        ),
        model_versions={"depth": cloud.depth.version},
    )
