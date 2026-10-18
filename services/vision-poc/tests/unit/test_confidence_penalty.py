"""The assumed-intrinsics confidence penalty (M8 Step 5).

When scale comes from an assumed FOV rather than a measured focal, the lateral
dimensions are a guess, so confidence must drop and must never be hidden.
"""

from __future__ import annotations

from measurex_vision.quality.confidence import HeuristicConfidenceEstimator

# Chosen so the raw score (~0.72) stays below MAX_SCORE — the cap would
# otherwise mask the penalty's exact effect.
_EVIDENCE = {
    "plane_inlier_ratio": 0.7,
    "depth_valid_ratio": 0.7,
    "mask_area_ratio": 0.35,
    "point_count": 1500,
}


def test_assumed_intrinsics_lowers_the_score():
    est = HeuristicConfidenceEstimator()
    measured = est.estimate({**_EVIDENCE, "intrinsics_assumed": False})
    assumed = est.estimate({**_EVIDENCE, "intrinsics_assumed": True})
    assert assumed.score < measured.score
    assert assumed.score == measured.score * HeuristicConfidenceEstimator.ASSUMED_INTRINSICS_PENALTY


def test_missing_flag_is_treated_as_not_assumed():
    est = HeuristicConfidenceEstimator()
    assert est.estimate(_EVIDENCE).score == est.estimate({**_EVIDENCE, "intrinsics_assumed": False}).score
