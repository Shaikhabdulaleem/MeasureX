"""Tests for the box-mask segmenter and segmenter registry."""

from __future__ import annotations

import numpy as np

from measurex_vision.segmentation import get_segmenter
from measurex_vision.segmentation.box_mask import BoxMaskSegmenter


def test_box_mask_inside_and_outside():
    image = np.zeros((20, 30, 3), dtype=np.uint8)
    mask = BoxMaskSegmenter().segment(image, (5.0, 4.0, 15.0, 12.0))
    assert mask.shape == (20, 30)
    assert mask.dtype == bool
    assert mask[4:12, 5:15].all()
    assert not mask[0, 0]
    assert mask.sum() == (12 - 4) * (15 - 5)


def test_box_mask_clamps_to_image():
    image = np.zeros((10, 10, 3), dtype=np.uint8)
    mask = BoxMaskSegmenter().segment(image, (-5.0, -5.0, 100.0, 100.0))
    assert mask.all()


def test_registry_returns_box_mask():
    assert isinstance(get_segmenter("box_mask"), BoxMaskSegmenter)
