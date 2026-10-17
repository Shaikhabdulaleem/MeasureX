"""Tests for image loading."""

from __future__ import annotations

import numpy as np
from PIL import Image

from measurex_vision.io import load_image


def test_load_image_returns_rgb_uint8(tmp_path):
    path = tmp_path / "tiny.png"
    Image.fromarray(np.full((6, 9, 3), 128, dtype=np.uint8)).save(path)

    arr = load_image(str(path))

    assert arr.shape == (6, 9, 3)
    assert arr.dtype == np.uint8


def test_load_image_converts_grayscale_to_rgb(tmp_path):
    path = tmp_path / "gray.png"
    Image.fromarray(np.full((4, 4), 200, dtype=np.uint8), mode="L").save(path)

    arr = load_image(str(path))

    assert arr.shape == (4, 4, 3)
    assert arr.dtype == np.uint8
