"""Conservative support-region selector (image space).

The support plane (floor/table) must be fitted from scene points that are **not**
the shipment, or a large planar carton face gets mistaken for the floor. This
picks a band of scene pixels around and below the object's base — with the
object mask removed — as support-plane candidates. Pure and model-free, so it is
unit-testable without a GPU or depth model.

shortcut: a rectangular apron below/around the object bbox; no morphological
dilation or depth-aware ground detection. Upgrade to a gravity/IMU prior or a
learned ground segmenter once real warehouse captures are benchmarked.
"""

from __future__ import annotations

import numpy as np


def support_region_mask(
    object_mask: np.ndarray,
    *,
    margin_frac: float = 0.5,
    band_top_frac: float = 0.5,
    min_pixels: int = 200,
) -> np.ndarray | None:
    """Scene pixels that can represent the support surface under the object.

    ``object_mask`` is the shipment's boolean mask ``(H, W)``. The region is the
    object bbox grown by ``margin_frac`` of its size on each side, limited to the
    rows from ``band_top_frac`` down the bbox to the bottom of the grown box (so
    the wall/background above the object is excluded), with every object pixel
    removed. Returns the boolean support mask, or ``None`` when fewer than
    ``min_pixels`` candidate pixels remain (no trustworthy support surface)."""
    mask = np.asarray(object_mask, dtype=bool)
    if mask.ndim != 2:
        raise ValueError("object_mask must be a 2D (H, W) array")
    ys, xs = np.nonzero(mask)
    if ys.size == 0:
        return None
    h, w = mask.shape
    top, bottom = int(ys.min()), int(ys.max())
    left, right = int(xs.min()), int(xs.max())
    box_h = bottom - top + 1
    box_w = right - left + 1

    y1 = min(h - 1, bottom + round(margin_frac * box_h))
    x0 = max(0, left - round(margin_frac * box_w))
    x1 = min(w - 1, right + round(margin_frac * box_w))
    band_top = min(y1, top + round(band_top_frac * box_h))

    region = np.zeros_like(mask)
    region[band_top : y1 + 1, x0 : x1 + 1] = True
    region &= ~mask
    if int(region.sum()) < min_pixels:
        return None
    return region
