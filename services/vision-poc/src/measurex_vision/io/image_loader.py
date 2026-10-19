"""Image loading for the vision POC."""

from __future__ import annotations

import numpy as np


def load_image(path: str) -> np.ndarray:
    """Load a JPG/PNG as an ``(H, W, 3)`` uint8 RGB array."""
    from PIL import Image

    with Image.open(path) as img:
        return np.asarray(img.convert("RGB"), dtype=np.uint8)


def exif_focal_px(path: str) -> float | None:
    """Return the horizontal focal length in pixels from EXIF, or None.

    Uses the 35 mm-equivalent focal length (EXIF tag 41989), which already folds
    in the sensor crop, scaled to the actual image width: a 35 mm frame is 36 mm
    wide, so ``focal_px = f35 / 36 * width``. Returns None when the tag is absent
    or unreadable — the resolver then falls through to its FOV fallback."""
    try:
        from PIL import Image

        with Image.open(path) as img:
            exif = img.getexif()
            f35 = exif.get(41989)  # FocalLengthIn35mmFilm
            width = img.size[0]
        if not f35 or width <= 0:
            return None
        return float(f35) / 36.0 * width
    except (OSError, ValueError, TypeError):
        return None
