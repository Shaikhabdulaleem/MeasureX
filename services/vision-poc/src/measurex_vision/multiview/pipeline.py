"""M9 reconstruction orchestration: capture bundle -> typed metric result.

Validates inputs (typed failures, never a silent downgrade to ESTIMATE), carves a
metric visual hull coarse-to-fine, extracts gravity-fixed L/W/H, scores quality
from geometric observability, and (optionally) writes debug artifacts. Returns the
Phase-14 result shape; on failure returns a typed reason and never fabricated
dimensions.
"""

from __future__ import annotations

import time
from typing import Any

from .carton import carton_dimensions, largest_component
from .quality import assess, leave_one_out_spread, observability_metrics
from .schema import (
    CaptureBundle,
    FailureCode,
    MetricReconstructionError,
    ReconstructionConfig,
    ViewFrame,
    validate_bundle,
)
from .visual_hull import estimate_roi, reconstruct_hull


def _bundle_with(bundle: CaptureBundle, frames: list[ViewFrame]) -> CaptureBundle:
    return CaptureBundle(
        frames=frames,
        gravity_world=bundle.gravity_world,
        pose_source=bundle.pose_source,
        support_plane=bundle.support_plane,
        meta=bundle.meta,
    )


def _reconstruct_dims_m(bundle: CaptureBundle, config: ReconstructionConfig) -> tuple[float, float, float]:
    """L/W/H in metres (no cleanup, no debug) — used by leave-one-out."""
    hull = reconstruct_hull(bundle, config)
    geo = carton_dimensions(hull.points_m, bundle.gravity_world, hull.voxel_size_m, bundle.support_plane)
    return geo.length_m, geo.width_m, geo.height_m


def reconstruct(
    bundle: CaptureBundle,
    config: ReconstructionConfig | None = None,
    *,
    debug_dir: str | None = None,
) -> dict[str, Any]:
    """Full metric reconstruction. Returns the Phase-14 success/failure dict."""
    config = config or ReconstructionConfig()
    frames_total = len(bundle.frames)
    timings: dict[str, float] = {}
    t0 = time.perf_counter()

    try:
        validate_bundle(bundle, config)
        timings["validate_ms"] = (time.perf_counter() - t0) * 1000

        t1 = time.perf_counter()
        centre, half = estimate_roi(bundle, config)
        hull = reconstruct_hull(bundle, config)
        timings["carve_ms"] = (time.perf_counter() - t1) * 1000

        t2 = time.perf_counter()
        cleaned = largest_component(hull.points_m, hull.voxel_size_m)
        geo = carton_dimensions(cleaned, bundle.gravity_world, hull.voxel_size_m, bundle.support_plane)
        timings["geometry_ms"] = (time.perf_counter() - t2) * 1000
    except MetricReconstructionError as e:
        return {
            "success": False,
            "measurement_tier": "metric",
            "reason": e.code.value,
            "detail": e.detail,
            "frames_total": frames_total,
        }

    metrics = observability_metrics(bundle, hull.silhouette_agreement)
    loo: dict[str, Any] = {"runs": 0, "spread_frac": None}
    if config.leave_one_out:
        t3 = time.perf_counter()
        loo = leave_one_out_spread(bundle, config, lambda fs: _reconstruct_dims_m(_bundle_with(bundle, fs), config))
        timings["leave_one_out_ms"] = (time.perf_counter() - t3) * 1000
    quality = assess(metrics, loo, config)

    diagnostics: dict[str, Any] = {
        "pose_source": bundle.pose_source,
        "frames_accepted": frames_total,
        "frames_rejected": [],  # current contract validates all-or-nothing
        "gravity_world": [float(x) for x in bundle.gravity_world],
        "intrinsics_sources": "explicit (capture bundle)",
        "roi_centre_m": [float(x) for x in centre],
        "roi_half_extent_m": float(half),
        "voxel_size_m": hull.voxel_size_m,
        "initial_voxel_count": hull.initial_voxel_count,
        "final_occupied_voxels": int(cleaned.shape[0]),
        "silhouette_agreement": hull.silhouette_agreement,
        "reconstruction_bounds_m": {
            "lo": [float(x) for x in cleaned.min(axis=0)],
            "hi": [float(x) for x in cleaned.max(axis=0)],
        },
        "dims_before_rounding_m": {
            "length": geo.length_m, "width": geo.width_m, "height": geo.height_m,
        },
        "dims_final_mm": geo.dimensions.to_dict(),
        **metrics,
        "leave_one_out": loo,
        "timing_ms": timings,
    }

    result = {
        "success": True,
        "measurement_tier": "metric",
        "method": "multiview_visual_hull",
        "dimensions": geo.dimensions.to_dict(),
        "pose_source": bundle.pose_source,
        "frames_total": frames_total,
        "frames_accepted": frames_total,
        "quality": quality.to_dict(),
        "diagnostics": diagnostics,
    }

    if debug_dir is not None:
        from .debug import write_debug_artifacts

        write_debug_artifacts(debug_dir, bundle, hull, cleaned, geo, result)
    return result


def reconstruct_from_provider(
    provider: object,
    config: ReconstructionConfig | None = None,
    *,
    debug_dir: str | None = None,
) -> dict[str, Any]:
    """Reconstruct via a :class:`~.pose_provider.MetricPoseProvider`.

    If the provider has no metric pose source the request fails with
    ``metric_pose_unavailable`` — never a silent downgrade to the RGB-only
    estimate path."""
    if not provider.metric_pose_available():  # type: ignore[attr-defined]
        return {
            "success": False,
            "measurement_tier": "metric",
            "reason": FailureCode.METRIC_POSE_UNAVAILABLE.value,
            "detail": f"provider {getattr(provider, 'pose_source', '?')} has no metric pose",
        }
    return reconstruct(provider.load(), config, debug_dir=debug_dir)  # type: ignore[attr-defined]
