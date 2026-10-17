"""Tests for the experimental heuristic confidence."""

from __future__ import annotations

from measurex_vision.contracts import ConfidenceLevel
from measurex_vision.quality.confidence import HeuristicConfidenceEstimator

GOOD = {
    "plane_inlier_ratio": 0.9,
    "depth_valid_ratio": 0.95,
    "mask_area_ratio": 0.35,
    "point_count": 5000,
}
BAD = {
    "plane_inlier_ratio": 0.1,
    "depth_valid_ratio": 0.2,
    "mask_area_ratio": 0.9,
    "point_count": 60,
}


def test_good_beats_bad():
    est = HeuristicConfidenceEstimator()
    assert est.estimate(GOOD).score > est.estimate(BAD).score


def test_never_high():
    est = HeuristicConfidenceEstimator()
    assert est.estimate(GOOD).level is not ConfidenceLevel.HIGH
    assert est.estimate(GOOD).score <= HeuristicConfidenceEstimator.MAX_SCORE


def test_score_in_range():
    est = HeuristicConfidenceEstimator()
    for ev in (GOOD, BAD, {}):
        c = est.estimate(ev)
        assert 0.0 <= c.score <= 1.0
        assert c.level in {ConfidenceLevel.LOW, ConfidenceLevel.MEDIUM}
