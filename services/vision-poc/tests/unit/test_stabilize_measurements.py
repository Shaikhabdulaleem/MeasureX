"""Tests for pipeline.stabilize_measurements (pure over per-frame results)."""

from __future__ import annotations

from measurex_vision.contracts import (
    Confidence,
    Dimensions,
    FailureCode,
    MeasurementFailure,
    MeasurementSuccess,
)
from measurex_vision.pipeline import stabilize_measurements


def _ok(l, w, h, score=0.7):
    return MeasurementSuccess(
        dimensions=Dimensions(l, w, h), confidence=Confidence.from_score(score)
    )


def _fail():
    return MeasurementFailure(failure_code=FailureCode.GEOMETRY_DEGENERATE)


def test_stabilizes_consistent_frames():
    results = [_ok(600, 400, 350), _ok(602, 399, 351), _ok(598, 401, 349), _fail()]
    out = stabilize_measurements(results)
    assert isinstance(out, MeasurementSuccess)
    assert out.dimensions == Dimensions(600, 400, 350)
    d = out.to_dict()["diagnostics"]
    assert d["frame_count"] == 3
    assert d["frames_ok"] == 3
    assert d["frames_total"] == 4
    assert set(d["dimension_spread_mm"]) == {"length", "width", "height"}


def test_too_few_successes_fails():
    out = stabilize_measurements([_ok(600, 400, 350), _fail(), _fail()])
    assert isinstance(out, MeasurementFailure)
    assert out.failure_code is FailureCode.TEMPORAL_INSTABILITY


def test_high_spread_fails():
    results = [_ok(600, 400, 350), _ok(800, 500, 450), _ok(400, 300, 250)]
    out = stabilize_measurements(results, max_spread_ratio=0.1)
    assert isinstance(out, MeasurementFailure)
    assert out.failure_code is FailureCode.TEMPORAL_INSTABILITY


def test_confidence_never_high():
    results = [_ok(600, 400, 350, score=0.99) for _ in range(5)]
    out = stabilize_measurements(results)
    assert isinstance(out, MeasurementSuccess)
    assert out.confidence.level.value != "high"
