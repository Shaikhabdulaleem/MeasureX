"""Detector selection — keeps model choice out of callers."""

from __future__ import annotations

from typing import Any

from .base import Detector

KNOWN_DETECTORS = ("central_candidate", "grounding_dino")


def get_detector(name: str, *, production: bool = False, **cfg: Any) -> Detector:
    if production:
        from ..models import assert_production_allowed

        assert_production_allowed(name)
    if name == "central_candidate":
        from .central_candidate import CentralCandidateDetector

        return CentralCandidateDetector(**cfg)
    if name == "grounding_dino":
        from .grounding_dino import GroundingDinoDetector

        return GroundingDinoDetector(**cfg)
    raise ValueError(f"unknown detector {name!r}; known: {', '.join(KNOWN_DETECTORS)}")
