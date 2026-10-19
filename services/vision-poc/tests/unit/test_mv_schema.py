"""M9 strict input validation and typed failures."""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from measurex_vision.geometry.intrinsics import CameraIntrinsics
from measurex_vision.multiview import (
    FailureCode,
    MetricReconstructionError,
    ReconstructionConfig,
    ViewFrame,
    reconstruct_from_provider,
    validate_bundle,
)
from measurex_vision.multiview.pose_provider import ARCoreMetricPoseProvider
from measurex_vision.multiview.synthetic import synthetic_capture

CFG = ReconstructionConfig(min_total_baseline_m=0.05, min_view_coverage_deg=15)


def _good():
    b, _ = synthetic_capture(length_m=0.3, width_m=0.25, height_m=0.2, n_views=6, elevations_deg=(10, 45))
    return b


def _expect(bundle, code, config=CFG):
    with pytest.raises(MetricReconstructionError) as e:
        validate_bundle(bundle, config)
    assert e.value.code == code


def test_valid_bundle_passes():
    validate_bundle(_good(), CFG)


def test_insufficient_frames():
    b = _good()
    b = dataclasses.replace(b, frames=b.frames[:2])
    _expect(b, FailureCode.INSUFFICIENT_FRAMES)


def test_invalid_gravity():
    b = dataclasses.replace(_good(), gravity_world=np.zeros(3))
    _expect(b, FailureCode.INVALID_GRAVITY)


def test_mask_mismatch_empty():
    b = _good()
    f0 = b.frames[0]
    bad = ViewFrame(f0.frame_id, np.zeros_like(f0.mask), f0.intrinsics, f0.T_world_from_camera)
    b = dataclasses.replace(b, frames=[bad, *b.frames[1:]])
    _expect(b, FailureCode.MASK_MISMATCH)


def test_invalid_intrinsics():
    b = _good()
    f0 = b.frames[0]
    bad = ViewFrame(f0.frame_id, f0.mask, CameraIntrinsics(fx=-1, fy=800, cx=f0.width / 2, cy=f0.height / 2), f0.T_world_from_camera)
    b = dataclasses.replace(b, frames=[bad, *b.frames[1:]])
    _expect(b, FailureCode.INVALID_INTRINSICS)


def test_invalid_pose():
    b = _good()
    f0 = b.frames[0]
    bad = ViewFrame(f0.frame_id, f0.mask, f0.intrinsics, np.eye(4) * 2.0)  # det != 1
    b = dataclasses.replace(b, frames=[bad, *b.frames[1:]])
    _expect(b, FailureCode.INVALID_POSE)


def test_insufficient_baseline_identical_views():
    b = _good()
    f0 = b.frames[0]
    dup = [ViewFrame(str(i), f0.mask, f0.intrinsics, f0.T_world_from_camera) for i in range(6)]
    b = dataclasses.replace(b, frames=dup)
    _expect(b, FailureCode.INSUFFICIENT_BASELINE)


def test_insufficient_view_coverage():
    # Real metric baseline but a tiny angular sweep -> coverage fails, not baseline.
    b, _ = synthetic_capture(
        length_m=0.3, width_m=0.25, height_m=0.2, n_views=6,
        elevations_deg=(30,), azimuth_span_deg=3.0, distance_m=3.0,
    )
    cfg = ReconstructionConfig(min_total_baseline_m=0.001, min_view_coverage_deg=20)
    _expect(b, FailureCode.INSUFFICIENT_VIEW_COVERAGE, cfg)


def test_metric_pose_unavailable_provider():
    result = reconstruct_from_provider(ARCoreMetricPoseProvider(), CFG)
    assert result["success"] is False
    assert result["reason"] == FailureCode.METRIC_POSE_UNAVAILABLE.value
