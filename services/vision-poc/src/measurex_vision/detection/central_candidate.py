"""Model-free central-object detector.

A deterministic fallback for controlled POC images where the shipment is the
central, dominant object: return one centred box covering a fraction of the
frame. No model, no GPU — fully testable."""

from __future__ import annotations

import numpy as np

from .base import Detection, Detector


class CentralCandidateDetector(Detector):
    def __init__(self, box_fraction: float = 0.6) -> None:
        if not 0.0 < box_fraction <= 1.0:
            raise ValueError("box_fraction must be in (0, 1]")
        self.box_fraction = box_fraction

    def detect(self, image: np.ndarray) -> list[Detection]:
        h, w = image.shape[:2]
        half = self.box_fraction / 2.0
        cx, cy = w / 2.0, h / 2.0
        bbox = (
            cx - half * w,
            cy - half * h,
            cx + half * w,
            cy + half * h,
        )
        return [Detection(bbox_xyxy=bbox, score=1.0, label="parcel", reason="central_candidate")]

    def select_target(self, detections: list[Detection]) -> Detection:
        if not detections:
            raise ValueError("no detections to select from")
        return detections[0]
