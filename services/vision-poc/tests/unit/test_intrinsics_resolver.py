"""Tests for the camera-intrinsics resolver (M8 Step 5).

Pure logic — no models, no GPU. Verifies the source priority order and that an
FOV-derived (assumed) result is flagged so confidence can be penalized.
"""

from __future__ import annotations

import math

import pytest

from measurex_vision.geometry import (
    DEFAULT_FALLBACK_FOV_DEG,
    CameraIntrinsics,
    IntrinsicsSource,
    resolve_intrinsics,
)

W, H = 800, 600


def test_explicit_wins_over_everything():
    explicit = CameraIntrinsics(fx=1234.0, fy=1234.0, cx=400.0, cy=300.0)
    r = resolve_intrinsics(
        W, H, explicit=explicit, exif_focal_px=999, depth_focal_px=888, fallback_fov_deg=60
    )
    assert r.source is IntrinsicsSource.EXPLICIT
    assert r.intrinsics is explicit
    assert r.is_assumed is False


def test_priority_order_exif_then_profile_then_depth():
    assert resolve_intrinsics(
        W, H, exif_focal_px=700, device_profile_focal_px=800, depth_focal_px=900
    ).source is IntrinsicsSource.EXIF
    assert resolve_intrinsics(
        W, H, device_profile_focal_px=800, depth_focal_px=900
    ).source is IntrinsicsSource.DEVICE_PROFILE
    assert resolve_intrinsics(W, H, depth_focal_px=900).source is IntrinsicsSource.DEPTH_MODEL


def test_measured_sources_are_not_assumed():
    r = resolve_intrinsics(W, H, depth_focal_px=900)
    assert r.is_assumed is False
    assert r.intrinsics.fx == 900.0
    assert (r.intrinsics.cx, r.intrinsics.cy) == (W / 2.0, H / 2.0)
    assert "assumed_fov_deg" not in r.to_dict()


def test_configured_fov_is_assumed_and_reports_fov():
    r = resolve_intrinsics(W, H, fallback_fov_deg=50.0)
    assert r.source is IntrinsicsSource.CONFIGURED_FOV
    assert r.is_assumed is True
    assert r.assumed_fov_deg == 50.0
    expected = (W / 2.0) / math.tan(math.radians(50.0) / 2.0)
    assert r.intrinsics.fx == pytest.approx(expected)


def test_assumed_default_fov_when_nothing_supplied():
    r = resolve_intrinsics(W, H)
    assert r.source is IntrinsicsSource.ASSUMED
    assert r.is_assumed is True
    assert r.assumed_fov_deg == DEFAULT_FALLBACK_FOV_DEG
    d = r.to_dict()
    assert d["intrinsics_source"] == "assumed"
    assert d["intrinsics_assumed"] is True


def test_non_positive_focals_are_skipped():
    # A zero/None focal is "unknown" and must not win over the FOV fallback.
    r = resolve_intrinsics(W, H, exif_focal_px=0.0, depth_focal_px=None, fallback_fov_deg=60)
    assert r.source is IntrinsicsSource.CONFIGURED_FOV


# --- M8 fallback-FOV orientation fix -----------------------------------------


def _long_axis_focal(long_side: int) -> float:
    return (long_side / 2.0) / math.tan(math.radians(DEFAULT_FALLBACK_FOV_DEG) / 2.0)


def test_default_fov_landscape_uses_long_axis():
    # A: 1280x960 landscape — the 65-deg long-axis default keys off 1280.
    r = resolve_intrinsics(1280, 960)
    assert r.source is IntrinsicsSource.ASSUMED
    assert r.intrinsics.fx == pytest.approx(_long_axis_focal(1280))
    d = r.to_dict()
    assert d["assumed_fov_axis"] == "long_image_axis"
    assert d["image_orientation"] == "landscape"


def test_default_fov_portrait_matches_landscape_focal():
    # B: 960x1280 portrait — same camera/FOV must give the SAME focal_px as A
    # (the critical regression: rotating the image must not change focal).
    landscape = resolve_intrinsics(1280, 960)
    portrait = resolve_intrinsics(960, 1280)
    assert portrait.intrinsics.fx == pytest.approx(landscape.intrinsics.fx)
    assert portrait.intrinsics.fx == pytest.approx(_long_axis_focal(1280))
    assert portrait.intrinsics.fx == pytest.approx(1005, abs=1.0)  # ~1005 px, not 753
    assert portrait.to_dict()["image_orientation"] == "portrait"


def test_explicit_intrinsics_unchanged_in_portrait():
    # C: supplied intrinsics are returned verbatim regardless of orientation.
    explicit = CameraIntrinsics(fx=1111.0, fy=2222.0, cx=480.0, cy=640.0)
    r = resolve_intrinsics(960, 1280, explicit=explicit)
    assert r.intrinsics is explicit
    assert r.source is IntrinsicsSource.EXPLICIT


def test_configured_fov_is_horizontal_and_orientation_dependent():
    # D: --fov-deg keeps its documented HORIZONTAL (across-width) semantics, so it
    # is orientation-dependent by design — distinct from the long-axis default.
    land = resolve_intrinsics(1280, 960, fallback_fov_deg=65.0)
    port = resolve_intrinsics(960, 1280, fallback_fov_deg=65.0)
    assert land.source is port.source is IntrinsicsSource.CONFIGURED_FOV
    assert land.intrinsics.fx == pytest.approx((1280 / 2.0) / math.tan(math.radians(65.0) / 2.0))
    assert port.intrinsics.fx == pytest.approx((960 / 2.0) / math.tan(math.radians(65.0) / 2.0))
    assert land.intrinsics.fx != pytest.approx(port.intrinsics.fx)
    assert land.to_dict()["assumed_fov_axis"] == "horizontal"
