"""Segmenter selection — keeps model choice out of callers."""

from __future__ import annotations

from typing import Any

from .base import Segmenter

KNOWN_SEGMENTERS = ("box_mask", "sam2")


def get_segmenter(name: str, **cfg: Any) -> Segmenter:
    if name == "box_mask":
        from .box_mask import BoxMaskSegmenter

        return BoxMaskSegmenter(**cfg)
    if name == "sam2":
        from .sam2 import Sam2Segmenter

        return Sam2Segmenter(**cfg)
    raise ValueError(f"unknown segmenter {name!r}; known: {', '.join(KNOWN_SEGMENTERS)}")
