"""Tests for RobustTemporalStabilizer."""

from __future__ import annotations

from measurex_vision.contracts import Dimensions
from measurex_vision.temporal import RobustTemporalStabilizer


def test_median_of_jittered_frames():
    frames = [
        Dimensions(600, 400, 350),
        Dimensions(602, 399, 351),
        Dimensions(598, 401, 349),
    ]
    out = RobustTemporalStabilizer().stabilize(frames)
    assert out.dimensions == Dimensions(600, 400, 350)
    assert out.frame_count == 3
    assert out.spread_mm["length"] == 4  # 602 - 598


def test_wild_frame_rejected():
    frames = [Dimensions(600, 400, 350)] * 6 + [Dimensions(2000, 1500, 900)]
    out = RobustTemporalStabilizer().stabilize(frames)
    assert out.dimensions == Dimensions(600, 400, 350)
    assert out.frame_count == 6  # the outlier dropped


def test_orientation_preserved():
    # Near-square inputs (each already L >= W); result must keep L >= W.
    frames = [Dimensions(500, 498, 200), Dimensions(502, 500, 201), Dimensions(501, 499, 199)]
    out = RobustTemporalStabilizer(mad_k=10.0).stabilize(frames)
    assert out.dimensions.length_mm >= out.dimensions.width_mm
