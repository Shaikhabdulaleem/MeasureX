"""build_measurement / measure_from_cloud end-to-end (no models)."""

from __future__ import annotations

import numpy as np

from measurex_vision.contracts import (
    ConfidenceLevel,
    FailureCode,
    MeasurementFailure,
    MeasurementSuccess,
)
from measurex_vision.depth.base import DepthResult
from measurex_vision.detection.base import Detection
from measurex_vision.pipeline import MaskedCloud, measure_from_cloud


def _cloud(points: np.ndarray) -> MaskedCloud:
    return MaskedCloud(
        points_m=points,
        mask=np.ones((4, 4), dtype=bool),
        detection=Detection(bbox_xyxy=(0, 0, 1, 1), score=1.0, label="parcel", reason="test"),
        depth=DepthResult(depth_m=np.ones((4, 4)), focal_px=1000.0, valid_ratio=0.9, version="mock"),
    )


def test_measure_from_cloud_success(box_on_floor):
    cloud = _cloud(box_on_floor(600, 400, 350, tilt_deg=6.0, yaw_deg=15.0))
    out = measure_from_cloud(cloud)
    assert isinstance(out, MeasurementSuccess)
    assert abs(out.dimensions.length_mm - 600) <= 15
    assert abs(out.dimensions.width_mm - 400) <= 15
    assert abs(out.dimensions.height_mm - 350) <= 15
    # Never HIGH before benchmark calibration.
    assert out.confidence.level is not ConfidenceLevel.HIGH
    d = out.to_dict()
    assert d["success"] is True
    assert d["method"] == "rgb_ai"
    assert set(d["timing_ms"]) == {"geometry", "total"}
    assert d["timing_ms"]["total"] >= d["timing_ms"]["geometry"]


def test_measure_from_cloud_degenerate():
    # A thin sheet of points on one plane -> no object above the floor.
    rng = np.random.default_rng(0)
    flat = np.column_stack([rng.uniform(-1, 1, 300), rng.uniform(-1, 1, 300), np.zeros(300)])
    out = measure_from_cloud(_cloud(flat))
    assert isinstance(out, MeasurementFailure)
    assert out.failure_code is FailureCode.GEOMETRY_DEGENERATE
