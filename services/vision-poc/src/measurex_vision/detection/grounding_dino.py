"""Grounding DINO open-vocabulary detector (optional).

Apache-2.0 (confirm the exact checkpoint at adoption — MODELS.md). torch and the
model package are imported lazily so importing this module needs neither.
"""

from __future__ import annotations

import os

import numpy as np

from .base import Detection, Detector

DEFAULT_PROMPT = "box . carton . parcel . package . pallet . bag . furniture"


class GroundingDinoDetector(Detector):
    def __init__(
        self,
        checkpoint_path: str | None = None,
        prompt: str = DEFAULT_PROMPT,
        box_threshold: float = 0.3,
    ) -> None:
        self.checkpoint_path = checkpoint_path or os.environ.get("MEASUREX_GDINO_CHECKPOINT")
        self.prompt = prompt
        self.box_threshold = box_threshold
        self._model = None

    def _load(self) -> None:  # pragma: no cover - needs weights + torch
        if self._model is not None:
            return
        raise NotImplementedError(
            "GroundingDinoDetector inference requires the `seg` extra and a checkpoint; "
            "wire the model load here when adopting it (see MODELS.md)."
        )

    def detect(self, image: np.ndarray) -> list[Detection]:  # pragma: no cover
        self._load()
        raise NotImplementedError

    def select_target(self, detections: list[Detection]) -> Detection:
        if not detections:
            raise ValueError("no detections to select from")
        # Highest score wins; equal top scores are ambiguous -> caller should
        # surface MULTIPLE_TARGETS (VISION_ENGINE_POC.md §2).
        return max(detections, key=lambda d: d.score)
