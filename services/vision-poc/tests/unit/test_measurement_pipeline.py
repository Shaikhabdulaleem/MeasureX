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


def _cloud(object_points: np.ndarray, support_points: np.ndarray) -> MaskedCloud:
    return MaskedCloud(
        object_points_m=object_points,
        support_points_m=support_points,
        mask=np.ones((4, 4), dtype=bool),
        detection=Detection(bbox_xyxy=(0, 0, 1, 1), score=1.0, label="parcel", reason="test"),
        depth=DepthResult(depth_m=np.ones((4, 4)), focal_px=1000.0, valid_ratio=0.9, version="mock"),
    )


def test_measure_from_cloud_success(object_and_support):
    # A: cuboid on a horizontal support plane.
    obj, support = object_and_support(600, 400, 350, tilt_deg=6.0, yaw_deg=15.0)
    out = measure_from_cloud(_cloud(obj, support))
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
    assert "support_plane_inlier_ratio" in d["diagnostics"]


def test_measure_from_cloud_tilted_support(object_and_support):
    # E: steeply tilted support plane still recovers height off that plane.
    obj, support = object_and_support(400, 300, 200, tilt_deg=15.0, yaw_deg=30.0)
    out = measure_from_cloud(_cloud(obj, support))
    assert isinstance(out, MeasurementSuccess)
    assert abs(out.dimensions.height_mm - 200) <= 20


def test_object_face_not_eligible_as_support(object_and_support):
    # B + the key regression: the object's planar faces have FAR more points
    # than the small visible floor. Because the support plane is fitted from the
    # separate support cloud, a carton face can never win and be read as "floor".
    obj, support = object_and_support(600, 400, 350, tilt_deg=6.0, yaw_deg=15.0)
    obj = np.repeat(obj, 5, axis=0)  # dwarf the support cloud in point count
    support_small = support[:: max(1, support.shape[0] // 400)]
    out = measure_from_cloud(_cloud(obj, support_small))
    assert isinstance(out, MeasurementSuccess)
    assert abs(out.dimensions.length_mm - 600) <= 20
    assert abs(out.dimensions.width_mm - 400) <= 20
    assert abs(out.dimensions.height_mm - 350) <= 20


def test_support_plane_not_found_when_support_sparse(object_and_support):
    # C: no trustworthy support candidate -> typed failure, no fabricated dims.
    obj, _ = object_and_support(600, 400, 350)
    out = measure_from_cloud(_cloud(obj, np.empty((0, 3), dtype=float)))
    assert isinstance(out, MeasurementFailure)
    assert out.failure_code is FailureCode.SUPPORT_PLANE_NOT_FOUND


def test_measure_from_cloud_degenerate(object_and_support):
    # Object points lie on the support plane itself -> nothing above the floor.
    _, support = object_and_support(600, 400, 350)
    out = measure_from_cloud(_cloud(support[:300].copy(), support))
    assert isinstance(out, MeasurementFailure)
    assert out.failure_code is FailureCode.GEOMETRY_DEGENERATE
