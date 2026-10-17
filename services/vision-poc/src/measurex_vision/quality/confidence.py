"""ConfidenceEstimator provider interface — evidence -> calibrated confidence.

Confidence is not model softmax alone: it combines detector score, mask
completeness, valid-depth ratio, point-cloud density, geometry quality and
frame-to-frame spread (VISION_ENGINE_POC.md §9). The concrete estimator and its
thresholds are set from benchmark data in a later milestone.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..contracts import Confidence


class ConfidenceEstimator(ABC):
    @abstractmethod
    def estimate(self, evidence: dict[str, Any]) -> Confidence:
        """Combine the per-stage evidence bag into a single Confidence."""
