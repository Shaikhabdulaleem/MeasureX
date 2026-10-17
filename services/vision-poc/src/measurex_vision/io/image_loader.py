"""Image loading for the vision POC."""

from __future__ import annotations

import numpy as np


def load_image(path: str) -> np.ndarray:
    """Load a JPG/PNG as an ``(H, W, 3)`` uint8 RGB array."""
    from PIL import Image

    with Image.open(path) as img:
        return np.asarray(img.convert("RGB"), dtype=np.uint8)
