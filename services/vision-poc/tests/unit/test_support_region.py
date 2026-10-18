"""Support-region selector: an apron of scene pixels below/around the object,
with the object itself removed."""

from __future__ import annotations

import numpy as np

from measurex_vision.quality.support_region import support_region_mask


def _object_mask() -> np.ndarray:
    m = np.zeros((100, 100), dtype=bool)
    m[20:60, 30:70] = True  # bbox rows 20..59, cols 30..69
    return m


def test_support_region_is_disjoint_from_object():
    # D: support points must not come from the object mask.
    mask = _object_mask()
    support = support_region_mask(mask, min_pixels=50)
    assert support is not None
    assert not np.any(support & mask)
    assert support.sum() > 0


def test_support_region_excludes_the_wall_above_the_object():
    mask = _object_mask()
    support = support_region_mask(mask, band_top_frac=0.5, min_pixels=50)
    rows = np.nonzero(support)[0]
    # Nothing above the lower half of the object (top=20, box_h=40).
    assert rows.min() >= 20 + 20


def test_support_region_insufficient_area_returns_none():
    # C: object fills the frame -> no apron room -> typed-failure signal.
    assert support_region_mask(np.ones((40, 40), dtype=bool), min_pixels=200) is None


def test_support_region_empty_mask_returns_none():
    assert support_region_mask(np.zeros((10, 10), dtype=bool)) is None
