"""Image/video measurement pipeline for the MeasureX vision POC.

Still images flow through detection, segmentation, depth, support-plane
geometry and confidence scoring. Videos measure sampled frames and robustly
stabilize their integer-mm dimensions. Per-stage timings feed the M5 benchmark.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from time import perf_counter

import numpy as np

from .contracts import (
    Confidence,
    ConfidenceLevel,
    Diagnostics,
    MeasurementFailure,
    MeasurementResult,
    MeasurementSuccess,
)
from .depth.base import DepthEstimator, DepthResult
from .detection.base import Detection, Detector
from .detection.select import classify_target
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
from .temporal.robust import RobustTemporalStabilizer
from .temporal.stabilizer import TemporalStabilizer


@dataclass(frozen=True)
class MaskedCloud:
    points_m: np.ndarray       # (N, 3) camera-frame metres
    mask: np.ndarray           # (H, W) bool
    detection: Detection
    depth: DepthResult
    diagnostics: Diagnostics = field(default_factory=Diagnostics)
    timing_ms: dict[str, float] = field(default_factory=dict)


MaskedCloudResult = MaskedCloud | MeasurementFailure


def _release(provider: object) -> None:
    """Free a provider's model if it supports it (low-memory mode)."""
    release = getattr(provider, "release", None)
    if callable(release):
        release()


def build_masked_cloud(
    image: np.ndarray,
    *,
    detector: Detector,
    segmenter: Segmenter,
    depth: DepthEstimator,
    release_models: bool = False,
) -> MaskedCloudResult:
    """Run the M2 pipeline; return a MaskedCloud or a typed MeasurementFailure.

    ``release_models`` frees each model right after its stage so only one lives at
    a time — needed to fit GDINO + SAM 2 + Depth Pro on a small GPU."""
    from .contracts import FailureCode

    stage_started = perf_counter()
    detections = detector.detect(image)
    kind, target = classify_target(detections)
    if kind == "multiple":
        return MeasurementFailure(failure_code=FailureCode.MULTIPLE_TARGETS)
    if kind == "none" or target is None:
        return MeasurementFailure(failure_code=FailureCode.NO_TARGET)
    if release_models:
        _release(detector)
    detection_ms = (perf_counter() - stage_started) * 1000.0

    stage_started = perf_counter()
    mask = segmenter.segment(image, target.bbox_xyxy)
    if release_models:
        _release(segmenter)
    gate = validate_mask(mask)
    if gate is not None:
        return MeasurementFailure(failure_code=gate)
    segmentation_ms = (perf_counter() - stage_started) * 1000.0

    stage_started = perf_counter()
    depth_result = depth.estimate(image)
    if release_models:
        _release(depth)
    depth_ms = (perf_counter() - stage_started) * 1000.0
    stage_started = perf_counter()
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
        points_m=points,
        mask=mask,
        detection=target,
        depth=depth_result,
        diagnostics=diagnostics,
        timing_ms={
            "detection": detection_ms,
            "segmentation": segmentation_ms,
            "depth": depth_ms,
            "pointcloud": (perf_counter() - stage_started) * 1000.0,
        },
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
    release_models: bool = False,
) -> MeasurementResult:
    """Full M3 path: masked cloud -> support plane -> object -> L/W/H + confidence."""
    started = perf_counter()
    cloud = build_masked_cloud(
        image, detector=detector, segmenter=segmenter, depth=depth, release_models=release_models
    )
    if isinstance(cloud, MeasurementFailure):
        return cloud
    outcome = measure_from_cloud(cloud, confidence=confidence)
    if isinstance(outcome, MeasurementSuccess):
        return replace(
            outcome,
            timing_ms={**outcome.timing_ms, "total": (perf_counter() - started) * 1000.0},
        )
    return outcome


def measure_from_cloud(
    cloud: MaskedCloud,
    *,
    confidence: ConfidenceEstimator | None = None,
) -> MeasurementResult:
    """Fit the support plane and box to an already-built masked cloud.

    Separate from build_measurement so a --debug run can reuse one cloud for both
    the artifacts and the measurement (no double inference)."""
    from .contracts import FailureCode

    stage_started = perf_counter()
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
    timing_ms = {
        **cloud.timing_ms,
        "geometry": (perf_counter() - stage_started) * 1000.0,
    }
    timing_ms["total"] = sum(timing_ms.values())

    return MeasurementSuccess(
        dimensions=dimensions,
        confidence=conf,
        diagnostics=Diagnostics(
            assumptions=["fx=fy, principal point at image centre"],
            extra=evidence,
        ),
        model_versions={"depth": cloud.depth.version},
        timing_ms=timing_ms,
    )


def stabilize_measurements(
    results: list[MeasurementResult],
    *,
    stabilizer: TemporalStabilizer | None = None,
    min_frames: int = 3,
    max_spread_ratio: float = 0.1,
) -> MeasurementResult:
    """Fuse per-frame results into one stabilized measurement.

    Pure over already-computed per-frame results (the CI-tested seam). Too few
    successful frames, or a per-dimension spread too large relative to the
    median, fails as TEMPORAL_INSTABILITY."""
    from .contracts import FailureCode

    successes = [r for r in results if isinstance(r, MeasurementSuccess)]
    if len(successes) < min_frames:
        return MeasurementFailure(
            failure_code=FailureCode.TEMPORAL_INSTABILITY,
            diagnostics=Diagnostics(
                extra={"frames_total": len(results), "frames_ok": len(successes)}
            ),
        )

    stage_started = perf_counter()
    stab = (stabilizer or RobustTemporalStabilizer()).stabilize([s.dimensions for s in successes])
    stabilization_ms = (perf_counter() - stage_started) * 1000.0
    dims = stab.dimensions

    # Spread gate: largest relative spread across L/W/H.
    rel = max(
        stab.spread_mm[name] / max(1, getattr(dims, f"{name}_mm"))
        for name in ("length", "width", "height")
    )
    if rel > max_spread_ratio:
        return MeasurementFailure(
            failure_code=FailureCode.TEMPORAL_INSTABILITY,
            diagnostics=Diagnostics(
                extra={
                    "frames_total": len(results),
                    "frames_ok": len(successes),
                    "dimension_spread_mm": stab.spread_mm,
                }
            ),
        )

    # Confidence: median of per-frame scores, penalized by relative spread, capped.
    scores = sorted(s.confidence.score for s in successes)
    median_score = scores[len(scores) // 2]
    conf = Confidence.from_score(max(0.0, median_score * (1.0 - rel)))
    if conf.level is ConfidenceLevel.HIGH:
        conf = Confidence(score=conf.score, level=ConfidenceLevel.MEDIUM)

    timing_ms: dict[str, float] = {}
    for success in successes:
        for stage, duration in success.timing_ms.items():
            if stage != "total":
                timing_ms[stage] = timing_ms.get(stage, 0.0) + duration
    timing_ms["stabilization"] = stabilization_ms
    timing_ms["total"] = sum(timing_ms.values())

    return MeasurementSuccess(
        dimensions=dims,
        confidence=conf,
        diagnostics=Diagnostics(
            assumptions=["fx=fy, principal point at image centre"],
            extra={
                "frame_count": stab.frame_count,
                "frames_total": len(results),
                "frames_ok": len(successes),
                "dimension_spread_mm": stab.spread_mm,
            },
        ),
        model_versions=successes[0].model_versions,
        timing_ms=timing_ms,
    )


def build_measurement_video(
    frames: list[np.ndarray],
    *,
    detector: Detector,
    segmenter: Segmenter,
    depth: DepthEstimator,
    stabilizer: TemporalStabilizer | None = None,
    confidence: ConfidenceEstimator | None = None,
    release_models: bool = False,
) -> MeasurementResult:
    """Measure each frame (M3) then temporally stabilize."""
    from .contracts import FailureCode

    if not frames:
        return MeasurementFailure(failure_code=FailureCode.NO_TARGET)
    started = perf_counter()
    results = [
        build_measurement(
            f,
            detector=detector,
            segmenter=segmenter,
            depth=depth,
            confidence=confidence,
            release_models=release_models,
        )
        for f in frames
    ]
    outcome = stabilize_measurements(results, stabilizer=stabilizer)
    if isinstance(outcome, MeasurementSuccess):
        return replace(
            outcome,
            timing_ms={**outcome.timing_ms, "total": (perf_counter() - started) * 1000.0},
        )
    return outcome
