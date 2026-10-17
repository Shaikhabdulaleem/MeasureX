"""Tests for the domain contracts (validation + serialization shapes)."""

from __future__ import annotations

import pytest

from measurex_vision.contracts import (
    Confidence,
    ConfidenceLevel,
    Diagnostics,
    Dimensions,
    FailureCode,
    MeasurementFailure,
    MeasurementSuccess,
)


def test_dimensions_rejects_floats_and_bools():
    with pytest.raises(TypeError):
        Dimensions(length_mm=400.0, width_mm=300, height_mm=200)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Dimensions(length_mm=True, width_mm=1, height_mm=1)  # type: ignore[arg-type]


def test_dimensions_enforces_orientation_and_sign():
    with pytest.raises(ValueError):
        Dimensions(length_mm=300, width_mm=400, height_mm=200)  # length < width
    with pytest.raises(ValueError):
        Dimensions(length_mm=-1, width_mm=0, height_mm=0)


def test_confidence_from_score_levels():
    assert Confidence.from_score(0.95).level is ConfidenceLevel.HIGH
    assert Confidence.from_score(0.70).level is ConfidenceLevel.MEDIUM
    assert Confidence.from_score(0.10).level is ConfidenceLevel.LOW
    with pytest.raises(ValueError):
        Confidence.from_score(1.5)


def test_success_to_dict_shape():
    result = MeasurementSuccess(
        dimensions=Dimensions(1204, 801, 598),
        confidence=Confidence.from_score(0.91),
        diagnostics=Diagnostics(extra={"depth_valid_ratio": 0.93}),
        model_versions={"depth": "depth-pro@x"},
        timing_ms={"total": 120.0},
    )
    d = result.to_dict()
    assert d["success"] is True
    assert d["dimensions"] == {"length_mm": 1204, "width_mm": 801, "height_mm": 598}
    assert d["confidence"] == 0.91
    assert d["confidence_level"] == "high"
    assert d["method"] == "rgb_ai"
    assert d["diagnostics"]["depth_valid_ratio"] == 0.93


def test_failure_fills_default_guidance():
    failure = MeasurementFailure(failure_code=FailureCode.OBJECT_NOT_FULLY_VISIBLE)
    d = failure.to_dict()
    assert d["success"] is False
    assert d["failure_code"] == "object_not_fully_visible"
    assert "visible" in d["user_guidance"].lower()
