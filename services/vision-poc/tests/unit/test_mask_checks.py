"""Tests for mask-quality gating."""

from __future__ import annotations

import numpy as np

from measurex_vision.contracts import FailureCode
from measurex_vision.quality.mask_checks import validate_mask


def _centred_mask(h=100, w=100, frac=0.4):
    m = np.zeros((h, w), dtype=bool)
    bh, bw = int(h * frac), int(w * frac)
    y0, x0 = (h - bh) // 2, (w - bw) // 2
    m[y0 : y0 + bh, x0 : x0 + bw] = True
    return m


def test_good_mask_passes():
    assert validate_mask(_centred_mask()) is None


def test_tiny_mask_rejected():
    m = np.zeros((100, 100), dtype=bool)
    m[0:3, 0:3] = True
    assert validate_mask(m) is FailureCode.SEGMENTATION_UNSTABLE


def test_full_frame_mask_rejected():
    m = np.ones((100, 100), dtype=bool)
    assert validate_mask(m) is FailureCode.SEGMENTATION_UNSTABLE


def test_border_contact_rejected():
    # A strip glued to the top edge: every pixel sits on the image border.
    m = np.zeros((100, 100), dtype=bool)
    m[0:1, :] = True
    assert validate_mask(m, min_area_ratio=0.0) is FailureCode.OBJECT_NOT_FULLY_VISIBLE
