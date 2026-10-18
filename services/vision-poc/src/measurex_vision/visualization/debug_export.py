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


def overlay_mask(
    image: np.ndarray,
    mask: np.ndarray,
    bbox_xyxy: tuple[float, float, float, float] | None = None,
) -> np.ndarray:
    """Blend a green mask tint onto the image and draw the detection box."""
    out = np.asarray(image, dtype=np.uint8).copy()
    m = np.asarray(mask, dtype=bool)
    tint = np.array([0, 255, 0], dtype=np.uint8)
    out[m] = (0.5 * out[m] + 0.5 * tint).astype(np.uint8)
    if bbox_xyxy is not None:
        h, w = out.shape[:2]
        x0, y0, x1, y1 = (round(v) for v in bbox_xyxy)
        x0, x1 = max(0, x0), min(w - 1, x1)
        y0, y1 = max(0, y0), min(h - 1, y1)
        if x1 > x0 and y1 > y0:
            out[y0, x0:x1] = tint
            out[y1, x0:x1] = tint
            out[y0:y1, x0] = tint
            out[y0:y1, x1] = tint
    return out


def _blend(out: np.ndarray, region: np.ndarray, color: tuple[int, int, int]) -> None:
    """Blend ``color`` at 50% over the ``region`` pixels of ``out`` in place."""
    r = np.asarray(region, dtype=bool)
    tint = np.array(color, dtype=np.uint8)
    out[r] = (0.5 * out[r] + 0.5 * tint).astype(np.uint8)


def overlay_support_region(
    image: np.ndarray,
    object_mask: np.ndarray,
    support_mask: np.ndarray,
) -> np.ndarray:
    """A: original image with the object/SAM region (green) and support-candidate
    region (orange) tinted so they are visually distinguishable."""
    out = np.asarray(image, dtype=np.uint8).copy()
    _blend(out, support_mask, (255, 140, 0))  # support candidates — orange
    _blend(out, object_mask, (0, 255, 0))     # object/SAM region — green (on top)
    return out


def overlay_support_plane_inliers(
    image: np.ndarray,
    object_mask: np.ndarray,
    support_mask: np.ndarray,
    inlier_mask: np.ndarray,
) -> np.ndarray:
    """B: within the support region, RANSAC plane inliers (blue) vs support
    outliers (red); object pixels in green. Distinguishes which support pixels
    the floor plane was actually fitted to."""
    out = np.asarray(image, dtype=np.uint8).copy()
    sup = np.asarray(support_mask, dtype=bool)
    inl = np.asarray(inlier_mask, dtype=bool)
    _blend(out, sup & ~inl, (255, 0, 0))   # support candidate outliers — red
    _blend(out, inl, (0, 80, 255))         # plane inliers — blue
    _blend(out, object_mask, (0, 255, 0))  # object pixels — green
    return out


def save_cloud_artifacts(
    out_dir: str,
    image: np.ndarray,
    mask: np.ndarray,
    points: np.ndarray,
    bbox_xyxy: tuple[float, float, float, float] | None = None,
    diagnostics: dict | None = None,
) -> dict[str, str]:
    """Write mask overlay, raw mask, point cloud, and cloud diagnostics."""
    from PIL import Image

    os.makedirs(out_dir, exist_ok=True)
    paths: dict[str, str] = {}

    overlay = overlay_mask(image, mask, bbox_xyxy)
    overlay_path = os.path.join(out_dir, "mask_overlay.png")
    Image.fromarray(overlay).save(overlay_path)
    paths["mask_overlay.png"] = overlay_path

    mask_path = os.path.join(out_dir, "mask.npy")
    np.save(mask_path, np.asarray(mask, dtype=bool))
    paths["mask.npy"] = mask_path

    points_path = os.path.join(out_dir, "points.npy")
    np.save(points_path, np.asarray(points, dtype=float))
    paths["points.npy"] = points_path

    diag = dict(diagnostics or {})
    diag.setdefault("point_count", int(np.asarray(points).shape[0]))
    diag_path = os.path.join(out_dir, "cloud_diagnostics.json")
    with open(diag_path, "w", encoding="utf-8") as fh:
        json.dump(diag, fh, indent=2)
    paths["cloud_diagnostics.json"] = diag_path

    return paths
