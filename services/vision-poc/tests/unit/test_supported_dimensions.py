"""Cuboid-on-a-floor: recover L/W/H from a support plane + box fit."""

from __future__ import annotations

import pytest

from measurex_vision.geometry import (
    extract_supported_dimensions,
    fit_plane_ransac,
    oriented_up,
    segment_object_points,
)

BOXES_MM = [(400, 300, 200), (600, 400, 350), (1200, 800, 600)]


@pytest.mark.parametrize("box_mm", BOXES_MM)
def test_recover_lwh_on_floor(box_mm, box_on_floor):
    length_mm, width_mm, height_mm = box_mm
    cloud = box_on_floor(length_mm, width_mm, height_mm, tilt_deg=7.0, yaw_deg=20.0)

    plane = fit_plane_ransac(cloud, threshold_m=0.01, seed=3)
    up = oriented_up(plane, cloud)
    obj = segment_object_points(cloud, plane, up)
    assert obj.shape[0] > 50

    dims = extract_supported_dimensions(obj, plane, up)
    assert dims.length_mm >= dims.width_mm
    # ~15 mm tolerance: floor-band removal + 2 cm point spacing.
    assert abs(dims.length_mm - length_mm) <= 15
    assert abs(dims.width_mm - width_mm) <= 15
    assert abs(dims.height_mm - height_mm) <= 15
