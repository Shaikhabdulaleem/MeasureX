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
