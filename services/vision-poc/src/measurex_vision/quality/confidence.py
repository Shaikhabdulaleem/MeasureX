"""ConfidenceEstimator provider interface — evidence -> calibrated confidence.

Confidence is not model softmax alone: it combines detector score, mask
completeness, valid-depth ratio, point-cloud density, geometry quality and
frame-to-frame spread (VISION_ENGINE_POC.md §9). The concrete estimator and its
thresholds are set from benchmark data in a later milestone.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..contracts import Confidence, ConfidenceLevel


class ConfidenceEstimator(ABC):
    @abstractmethod
    def estimate(self, evidence: dict[str, Any]) -> Confidence:
        """Combine the per-stage evidence bag into a single Confidence."""


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


class HeuristicConfidenceEstimator(ConfidenceEstimator):
    """A first, **uncalibrated** confidence from cheap geometric evidence.

    Deliberately capped below HIGH: camera-only scale is estimated, and nothing
    is "high confidence" until a warehouse benchmark says so (VISION_DECISION.md
    §3, VISION_ENGINE_POC.md §9). Weights are placeholders, not tuned."""

    MAX_SCORE = 0.84  # stays within MEDIUM until benchmark calibration
    # Multiplier when scale comes from an assumed FOV rather than a measured
    # focal — the lateral (L/W) scale is then a guess (M8 Step 5).
    ASSUMED_INTRINSICS_PENALTY = 0.7

    def estimate(self, evidence: dict[str, Any]) -> Confidence:
        plane_inlier_ratio = _clamp01(float(evidence.get("plane_inlier_ratio", 0.0)))
        depth_valid_ratio = _clamp01(float(evidence.get("depth_valid_ratio", 0.0)))
        mask_area_ratio = _clamp01(float(evidence.get("mask_area_ratio", 0.0)))
        point_count = float(evidence.get("point_count", 0))

        # More object points -> more support, saturating around a few thousand.
        density = _clamp01(point_count / 3000.0)
        # A healthy mask isn't a sliver or near the whole frame.
        mask_quality = _clamp01(1.0 - abs(mask_area_ratio - 0.35) / 0.35)

        score = (
            0.30 * plane_inlier_ratio
            + 0.30 * depth_valid_ratio
            + 0.20 * density
            + 0.20 * mask_quality
        )
        if evidence.get("intrinsics_assumed"):
            score *= self.ASSUMED_INTRINSICS_PENALTY
        score = min(self.MAX_SCORE, score)
        conf = Confidence.from_score(score)
        # Never report HIGH yet, whatever the arithmetic.
        if conf.level is ConfidenceLevel.HIGH:
            conf = Confidence(score=conf.score, level=ConfidenceLevel.MEDIUM)
        return conf
