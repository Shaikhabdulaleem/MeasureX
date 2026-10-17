"""End-to-end M2 pipeline with model-free providers + a mock depth estimator."""

from __future__ import annotations

import numpy as np

from measurex_vision.contracts import FailureCode, MeasurementFailure
from measurex_vision.detection.central_candidate import CentralCandidateDetector
from measurex_vision.pipeline import MaskedCloud, build_masked_cloud
from measurex_vision.segmentation.box_mask import BoxMaskSegmenter


def test_build_masked_cloud_success(mock_estimator):
    image = np.zeros((60, 80, 3), dtype=np.uint8)
    out = build_masked_cloud(
        image,
        detector=CentralCandidateDetector(box_fraction=0.6),
        segmenter=BoxMaskSegmenter(),
        depth=mock_estimator,
    )
    assert isinstance(out, MaskedCloud)
    assert out.points_m.ndim == 2 and out.points_m.shape[1] == 3
    assert out.points_m.shape[0] > 50
    # 0.6 box over the frame -> ~0.36 mask area.
    assert 0.3 < out.diagnostics.extra["mask_area_ratio"] < 0.4
    assert out.diagnostics.extra["point_count"] == out.points_m.shape[0]
    assert set(out.timing_ms) == {"detection", "segmentation", "depth", "pointcloud"}
    assert all(value >= 0 for value in out.timing_ms.values())


def test_build_masked_cloud_gated_mask(mock_estimator):
    image = np.zeros((60, 80, 3), dtype=np.uint8)
    out = build_masked_cloud(
        image,
        detector=CentralCandidateDetector(box_fraction=0.1),  # ~1% area -> too tiny
        segmenter=BoxMaskSegmenter(),
        depth=mock_estimator,
    )
    assert isinstance(out, MeasurementFailure)
    assert out.failure_code is FailureCode.SEGMENTATION_UNSTABLE
