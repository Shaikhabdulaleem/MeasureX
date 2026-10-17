"""Mask-quality gating.

Reject masks that can't yield a trustworthy measurement rather than silently
measuring garbage (VISION_ENGINE_POC.md §3, VISION_DECISION.md §7). Pure — no
model/GPU."""

from __future__ import annotations

import numpy as np

from ..contracts import FailureCode


def validate_mask(
    mask: np.ndarray,
    *,
    min_area_ratio: float = 0.02,
    max_area_ratio: float = 0.95,
    max_border_ratio: float = 0.5,
) -> FailureCode | None:
    """Return a FailureCode if the mask is unusable, else None.

    - tiny (< min) or near-full-frame (> max) area  -> SEGMENTATION_UNSTABLE
    - too much image-border contact (> max_border)  -> OBJECT_NOT_FULLY_VISIBLE

    shortcut: no fragmentation / connected-component check yet — add once real
    SAM 2 masks are in hand (needs labeling)."""
    m = np.asarray(mask, dtype=bool)
    if m.ndim != 2:
        raise ValueError("mask must be 2D (H, W)")
    total = m.size
    if total == 0:
        return FailureCode.SEGMENTATION_UNSTABLE

    area_ratio = float(m.sum()) / total
    if area_ratio < min_area_ratio or area_ratio > max_area_ratio:
        return FailureCode.SEGMENTATION_UNSTABLE

    # Fraction of the mask's pixels sitting on the image border: a shipment that
    # runs off the edge isn't fully visible.
    border = np.zeros_like(m)
    border[0, :] = border[-1, :] = border[:, 0] = border[:, -1] = True
    on_border = float((m & border).sum())
    if m.sum() > 0 and on_border / float(m.sum()) > max_border_ratio:
        return FailureCode.OBJECT_NOT_FULLY_VISIBLE

    return None
