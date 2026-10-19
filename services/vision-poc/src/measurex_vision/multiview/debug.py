"""Debug artifacts for an M9 run. Text formats (JSON/PLY) have no dependencies;
image artifacts are best-effort via Pillow (dev/seg extra) and skipped if absent.
"""

from __future__ import annotations

import json
import os
from typing import Any

import numpy as np

from . import camera as cam
from .carton import CartonGeometry, horizontal_basis, up_from_gravity
from .schema import CaptureBundle
from .visual_hull import CarveResult


def _write_ply(path: str, points: np.ndarray) -> None:
    pts = np.asarray(points, dtype=float)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(
            "ply\nformat ascii 1.0\n"
            f"element vertex {pts.shape[0]}\n"
            "property float x\nproperty float y\nproperty float z\n"
            "end_header\n"
        )
        fh.writelines(f"{x:.6f} {y:.6f} {z:.6f}\n" for x, y, z in pts)


def write_debug_artifacts(
    out_dir: str,
    bundle: CaptureBundle,
    hull: CarveResult,
    cleaned: np.ndarray,
    geo: CartonGeometry,
    result: dict[str, Any],
) -> None:
    os.makedirs(out_dir, exist_ok=True)

    with open(os.path.join(out_dir, "measurement.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    with open(os.path.join(out_dir, "diagnostics.json"), "w", encoding="utf-8") as fh:
        json.dump(result["diagnostics"], fh, indent=2)

    _write_ply(os.path.join(out_dir, "visual_hull.ply"), cleaned)
    centres = np.array([cam.camera_center(f.T_world_from_camera) for f in bundle.frames])
    _write_ply(os.path.join(out_dir, "camera_trajectory.ply"), centres)

    _best_effort_images(out_dir, bundle, cleaned, geo)


def _best_effort_images(out_dir, bundle, cleaned, geo) -> None:
    try:
        from PIL import Image
    except ImportError:
        return

    # Top-down footprint of the occupied cloud in the gravity-horizontal plane.
    up = up_from_gravity(bundle.gravity_world)
    e1, e2 = horizontal_basis(up)
    xy = np.stack([cleaned @ e1, cleaned @ e2], axis=-1)
    _scatter_png(Image, os.path.join(out_dir, "top_down_footprint.png"), xy)

    # Per-frame silhouette reprojection: mask (dim) vs reprojected hull (bright).
    for f in bundle.frames:
        P = cam.projection_matrix(f.intrinsics, f.T_world_from_camera)
        pix, depth = cam.project_world(P, cleaned)
        u = np.round(pix[:, 0]).astype(np.int64)
        v = np.round(pix[:, 1]).astype(np.int64)
        inb = (depth > 1e-6) & (u >= 0) & (u < f.width) & (v >= 0) & (v < f.height)
        img = np.zeros((f.height, f.width, 3), dtype=np.uint8)
        img[f.mask] = (60, 60, 60)
        img[v[inb], u[inb]] = (255, 80, 0)
        Image.fromarray(img).save(os.path.join(out_dir, f"reproj_{f.frame_id}.png"))


def _scatter_png(Image, path: str, xy: np.ndarray, size: int = 512, pad: int = 16) -> None:
    lo, hi = xy.min(axis=0), xy.max(axis=0)
    span = np.maximum(hi - lo, 1e-6)
    norm = (xy - lo) / span
    px = (pad + norm[:, 0] * (size - 2 * pad)).astype(int)
    py = (pad + (1 - norm[:, 1]) * (size - 2 * pad)).astype(int)
    img = np.full((size, size, 3), 255, dtype=np.uint8)
    img[np.clip(py, 0, size - 1), np.clip(px, 0, size - 1)] = (0, 90, 200)
    Image.fromarray(img).save(path)
