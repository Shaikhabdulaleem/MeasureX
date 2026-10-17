"""Detector provider interface — find the intended shipment in an RGB frame.

Implementations (Grounding DINO, a central-object fallback) land in later
milestones; the pipeline depends only on this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Detection:
    bbox_xyxy: tuple[float, float, float, float]
    score: float
    label: str
    reason: str  # why this candidate was produced / selected


class Detector(ABC):
    @abstractmethod
    def detect(self, image: np.ndarray) -> list[Detection]:
        """Return candidate shipment detections for an (H, W, 3) RGB image."""

    @abstractmethod
    def select_target(self, detections: list[Detection]) -> Detection:
        """Pick the single intended shipment.

        Must not silently choose between two similarly strong targets — signal
        ``FailureCode.MULTIPLE_TARGETS`` upstream instead (VISION_ENGINE_POC.md
        §2)."""
