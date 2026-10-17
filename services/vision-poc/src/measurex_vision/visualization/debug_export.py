"""Depth debug artifacts — no model/GPU, fully testable.

Numeric output alone can't diagnose a bad measurement, so every ``--debug`` run
saves inspectable artifacts (VISION_ENGINE_POC.md "Debug artifacts")."""

from __future__ import annotations

import json
import os

import numpy as np

from ..depth.base import DepthResult

# A small viridis-like colormap (anchors at 0, .25, .5, .75, 1) so we need no
# matplotlib. Values are 0..255 RGB.
_ANCHORS = np.array(
    [
        [68, 1, 84],
        [59, 82, 139],
        [33, 145, 140],
        [94, 201, 98],
        [253, 231, 37],
    ],
    dtype=float,
)


def colorize_depth(depth_m: np.ndarray) -> np.ndarray:
    """Map a metre depth map to an ``(H, W, 3)`` uint8 image.

    Valid pixels are normalized across their own min..max; invalid pixels
    (non-finite or ``<= 0``) render black."""
    depth = np.asarray(depth_m, dtype=float)
    valid = np.isfinite(depth) & (depth > 0)
    out = np.zeros((*depth.shape, 3), dtype=np.uint8)
    if not valid.any():
        return out

    lo = depth[valid].min()
    hi = depth[valid].max()
    norm = np.zeros_like(depth)
    norm[valid] = 0.0 if hi == lo else (depth[valid] - lo) / (hi - lo)

    stops = np.linspace(0.0, 1.0, len(_ANCHORS))
    for channel in range(3):
        out[..., channel] = np.where(
            valid, np.interp(norm, stops, _ANCHORS[:, channel]).astype(np.uint8), 0
        )
    return out


def save_depth_artifacts(
    out_dir: str,
    image: np.ndarray,
    depth: DepthResult,
    mask: np.ndarray | None = None,
) -> dict[str, str]:
    """Write the depth debug artifacts into ``out_dir``; return the paths written."""
    from PIL import Image

    os.makedirs(out_dir, exist_ok=True)
    paths: dict[str, str] = {}

    def _png(name: str, arr: np.ndarray) -> None:
        p = os.path.join(out_dir, name)
        Image.fromarray(arr).save(p)
        paths[name] = p

    def _npy(name: str, arr: np.ndarray) -> None:
        p = os.path.join(out_dir, name)
        np.save(p, arr)
        paths[name] = p

    _png("image.png", np.asarray(image, dtype=np.uint8))
    _png("depth_color.png", colorize_depth(depth.depth_m))
    _npy("depth_raw.npy", depth.depth_m)

    if mask is not None:
        masked = np.where(np.asarray(mask, dtype=bool), depth.depth_m, np.nan)
        _npy("depth_masked.npy", masked)
        _png("depth_masked_color.png", colorize_depth(masked))

    diagnostics = {
        "focal_px": depth.focal_px,
        "valid_ratio": depth.valid_ratio,
        "version": depth.version,
        "depth_shape": list(depth.depth_m.shape),
    }
    diag_path = os.path.join(out_dir, "diagnostics.json")
    with open(diag_path, "w", encoding="utf-8") as fh:
        json.dump(diagnostics, fh, indent=2)
    paths["diagnostics.json"] = diag_path

    return paths
