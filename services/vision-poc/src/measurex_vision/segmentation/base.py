"""Segmenter provider interface — box/candidate -> pixel-accurate mask.

Implementation (SAM 2, with video mask propagation) lands in a later milestone.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class Segmenter(ABC):
    @abstractmethod
    def segment(self, image: np.ndarray, box_xyxy: tuple[float, float, float, float]) -> np.ndarray:
        """Return a boolean (H, W) mask of the shipment selected by ``box_xyxy``."""
