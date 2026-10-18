"""Read-only measurement diagnostics (no GPU/model).

These assert the diagnostics *describe* the measurement; a companion assertion
confirms they do not change the reported dimensions."""

from __future__ import annotations

import numpy as np

from measurex_vision.contracts import MeasurementSuccess
from measurex_vision.depth.base import DepthResult
from measurex_vision.detection.base import Detection
from measurex_vision.geometry import (
    fit_plane_ransac,
    oriented_up,
    segment_object_points,
)
from measurex_vision.geometry.diagnostics import (
    geometry_diagnostics,
    image_space_diagnostics,
    support_inlier_pixel_mask,
)
from measurex_vision.pipeline import MaskedCloud, measure_from_cloud

_PCT_KEYS = ("p01", "p05", "p50", "p95", "p99")


def _cloud(object_points: np.ndarray, support_points: np.ndarray) -> MaskedCloud:
    return MaskedCloud(
        object_points_m=object_points,
        support_points_m=support_points,
        mask=np.ones((4, 4), dtype=bool),
        detection=Detection(bbox_xyxy=(0, 0, 1, 1), score=1.0, label="parcel", reason="test"),
        depth=DepthResult(depth_m=np.ones((4, 4)), focal_px=1000.0, valid_ratio=0.9, version="mock"),
    )


def test_geometry_diagnostics_keys_and_values(object_and_support):
    obj_raw, support = object_and_support(600, 400, 350, tilt_deg=6.0, yaw_deg=15.0)
    plane = fit_plane_ransac(support)
    up = oriented_up(plane, obj_raw)
    obj = segment_object_points(obj_raw, plane, up)

    d = geometry_diagnostics(obj, support, plane, up)

    assert len(d["support_plane_normal_xyz"]) == 3
    assert d["support_plane_inlier_count"] == int(plane.inlier_mask.sum())
    assert 0.0 <= d["support_plane_inlier_ratio"] <= 1.0
    for k in _PCT_KEYS:
        assert d[f"object_depth_{k}"] is not None
        assert d[f"support_depth_{k}"] is not None
        assert d[f"object_plane_distance_{k}_m"] is not None
    assert d["object_depth_min"] <= d["object_depth_max"]
    assert len(d["raw_obb_extents_m"]) == 3
    assert np.array(d["raw_obb_axes"]).shape == (3, 3)
    assert d["selected_vertical_axis_index"] in (0, 1, 2)
    assert d["horizontal_extent_length_m"] >= d["horizontal_extent_width_m"]
    # Height diagnostic matches the ~0.35 m carton off the plane.
    assert abs(d["computed_height_m"] - 0.35) < 0.05
    assert d["object_plane_distance_max_m"] > 0.0


def test_image_space_diagnostics():
    mask = np.zeros((40, 60), dtype=bool)
    mask[10:30, 15:45] = True
    d = image_space_diagnostics(mask, (12.0, 8.0, 48.0, 32.0))
    assert d["image_width_px"] == 60
    assert d["image_height_px"] == 40
    assert d["detected_bbox_width_px"] == 36.0
    assert d["detected_bbox_height_px"] == 24.0
    assert d["sam_mask_bbox_xyxy"] == [15, 10, 44, 29]
    assert d["sam_mask_width_px"] == 30
    assert d["sam_mask_height_px"] == 20


def test_image_space_diagnostics_empty_mask():
    d = image_space_diagnostics(np.zeros((8, 8), dtype=bool), (0.0, 0.0, 1.0, 1.0))
    assert d["sam_mask_bbox_xyxy"] is None
    assert d["sam_mask_width_px"] is None


def test_support_inlier_pixel_mask_corresponds_to_plane():
    # A planar support region in a depth map; inlier pixels count must equal the
    # plane's inlier count (1:1 pixel/point correspondence).
    depth = np.full((10, 10), 2.0)
    support_mask = np.zeros((10, 10), dtype=bool)
    support_mask[6:10, :] = True
    from measurex_vision.geometry import backproject_depth
    from measurex_vision.geometry.intrinsics import CameraIntrinsics

    intr = CameraIntrinsics.from_focal(500.0, 10, 10)
    pts = backproject_depth(depth, intr, mask=support_mask)
    plane = fit_plane_ransac(pts)

    px = support_inlier_pixel_mask(depth, support_mask, plane)
    assert px.shape == depth.shape
    assert int(px.sum()) == int(plane.inlier_mask.sum())
    assert not px[~support_mask].any()  # inliers only within the support region


def test_diagnostics_do_not_change_dimensions(object_and_support):
    # Guard: a successful measurement still carries the diagnostics, and the
    # dimensions are the geometry result — diagnostics add keys, nothing else.
    obj, support = object_and_support(600, 400, 350, tilt_deg=6.0, yaw_deg=15.0)
    out = measure_from_cloud(_cloud(obj, support))
    assert isinstance(out, MeasurementSuccess)
    diag = out.to_dict()["diagnostics"]
    assert "support_plane_normal_xyz" in diag
    assert "raw_obb_extents_m" in diag
    assert "detected_bbox_xyxy" in diag
    assert abs(out.dimensions.length_mm - 600) <= 15
