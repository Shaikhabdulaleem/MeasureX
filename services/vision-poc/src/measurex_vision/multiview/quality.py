"""M9 metric quality — derived from geometric observability, not a model score.

A reconstruction is trustworthy only when the geometry is well observed: enough
metric baseline, enough viewpoint diversity, enough contributing frames, high
silhouette agreement, and dimensions that stay stable when any one frame is
dropped (leave-one-out). The old monocular confidence value is never reused as
proof of metric accuracy.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from . import camera as cam
from .schema import (
    CaptureBundle,
    FailureCode,
    MetricReconstructionError,
    ReconstructionConfig,
    ViewFrame,
    _object_locus,
)


@dataclass(frozen=True)
class MetricQuality:
    level: str                      # "high" | "medium" | "low"
    observable: bool                # passed the hard observability gates
    metrics: dict[str, Any] = field(default_factory=dict)
    leave_one_out: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "observable": self.observable,
            "metrics": self.metrics,
            "leave_one_out": self.leave_one_out,
        }


def observability_metrics(bundle: CaptureBundle, silhouette_agreement: list[float]) -> dict[str, Any]:
    """Pose-only observability evidence (baselines, view coverage, silhouettes)."""
    poses = [f.T_world_from_camera for f in bundle.frames]
    steps = [cam.baseline(poses[i], poses[i + 1]) for i in range(len(poses) - 1)]
    locus = _object_locus(bundle.frames)
    angles = [
        cam.view_angle(poses[i], poses[j], locus)
        for i in range(len(poses))
        for j in range(i + 1, len(poses))
    ]
    return {
        "frames_accepted": len(bundle.frames),
        "baseline_min_mm": float(np.min(steps) * 1000) if steps else 0.0,
        "baseline_median_mm": float(np.median(steps) * 1000) if steps else 0.0,
        "baseline_max_mm": float(np.max(steps) * 1000) if steps else 0.0,
        "total_baseline_mm": float(np.sum(steps) * 1000) if steps else 0.0,
        "max_view_angle_deg": float(max(angles)) if angles else 0.0,
        "silhouette_agreement_min": float(min(silhouette_agreement)) if silhouette_agreement else 0.0,
        "silhouette_agreement_mean": float(np.mean(silhouette_agreement)) if silhouette_agreement else 0.0,
    }


def leave_one_out_spread(
    bundle: CaptureBundle,
    config: ReconstructionConfig,
    reconstruct_dims: Callable[[list[ViewFrame]], tuple[float, float, float]],
) -> dict[str, Any]:
    """Reconstruct L/W/H repeatedly, each time omitting one accepted frame, and
    report the relative spread per dimension. High spread == the result leans on a
    single view, i.e. weakly observed."""
    runs: list[tuple[float, float, float]] = []
    n = len(bundle.frames)
    # Drop at most ``leave_one_out_max_runs`` frames, spread evenly, to bound cost.
    drop = np.unique(np.linspace(0, n - 1, min(config.leave_one_out_max_runs, n)).astype(int))
    for i in drop:
        subset = bundle.frames[:i] + bundle.frames[i + 1 :]
        if len(subset) < config.min_frames:
            continue
        try:
            runs.append(reconstruct_dims(subset))
        except MetricReconstructionError:
            continue  # a dropped frame breaking observability is itself signal
    if len(runs) < 2:
        return {"runs": len(runs), "spread_frac": None}
    arr = np.array(runs)  # (R, 3) length/width/height metres
    spans = arr.max(axis=0) - arr.min(axis=0)
    means = arr.mean(axis=0)
    frac = spans / np.maximum(means, 1e-9)
    return {
        "runs": len(runs),
        "spread_frac": {"length": float(frac[0]), "width": float(frac[1]), "height": float(frac[2])},
        "spread_frac_max": float(frac.max()),
    }


def gate_failure(
    metrics: dict[str, Any],
    loo: dict[str, Any],
    config: ReconstructionConfig,
) -> FailureCode | None:
    """The typed failure a METRIC result must return when the geometry is not
    observable enough, or ``None`` when the quality gates pass.

    Frame-count / baseline / view-coverage gates are enforced earlier (in
    :func:`~.schema.validate_bundle`); here we gate on the two evidence sources
    that need the carved hull: per-frame silhouette consistency and leave-one-out
    dimension stability. A result that fails either is refused, never returned as a
    successful metric measurement. Thresholds are object-independent (never fit to
    a test carton)."""
    if metrics["silhouette_agreement_min"] < config.min_silhouette_consistency:
        return FailureCode.INSUFFICIENT_SILHOUETTE_CONSISTENCY
    spread_max = loo.get("spread_frac_max")
    if spread_max is not None and spread_max > config.max_dim_spread_frac:
        return FailureCode.UNSTABLE_RECONSTRUCTION
    return None


def assess(
    metrics: dict[str, Any],
    loo: dict[str, Any],
    config: ReconstructionConfig,
) -> MetricQuality:
    """Fold observability + stability into a coarse level. Thresholds are explicit
    and object-independent (never fit to a test carton)."""
    observable = (
        metrics["frames_accepted"] >= config.min_frames
        and metrics["total_baseline_mm"] >= config.min_total_baseline_m * 1000
        and metrics["max_view_angle_deg"] >= config.min_view_coverage_deg
    )
    spread_max = loo.get("spread_frac_max")
    sil = metrics["silhouette_agreement_min"]

    if (
        observable
        and metrics["max_view_angle_deg"] >= 45.0
        and sil >= 0.9
        and spread_max is not None
        and spread_max <= 0.03
    ):
        level = "high"
    elif observable and (spread_max is None or spread_max <= config.max_dim_spread_frac):
        level = "medium"
    else:
        level = "low"
    return MetricQuality(level=level, observable=observable, metrics=metrics, leave_one_out=loo)
