"""Model-free box-mask segmenter.

A deterministic fallback (mask = True inside the bbox) so the full pipeline runs
without SAM 2 — used for CI and controlled-POC smoke tests."""

from __future__ import annotations

import numpy as np

from .base import Segmenter


class BoxMaskSegmenter(Segmenter):
    def segment(self, image: np.ndarray, box_xyxy: tuple[float, float, float, float]) -> np.ndarray:
        h, w = image.shape[:2]
        x0, y0, x1, y1 = box_xyxy
        # Clamp to the image and round inward to whole pixels.
        x0 = max(0, round(x0))
        y0 = max(0, round(y0))
        x1 = min(w, round(x1))
        y1 = min(h, round(y1))
        mask = np.zeros((h, w), dtype=bool)
        if x1 > x0 and y1 > y0:
            mask[y0:y1, x0:x1] = True
        return mask
