"""Read-only measurement diagnostics — pure NumPy, no GPU/model.

Everything here only *describes* an already-computed measurement (support plane,
object cloud, oriented box). It never changes a dimension, threshold, axis choice
or confidence value. Kept pure so the M8 real-run diagnostics are unit-testable
without inference (CLAUDE.md "Debuggability")."""

from __future__ import annotations

from typing import Any

import numpy as np

from .bounding_box import oriented_box
from .planes import Plane, point_plane_distance

# Percentiles reported for every distribution below.
_PCTS = (1, 5, 50, 95, 99)


def _percentiles(values: np.ndarray, pcts: tuple[int, ...] = _PCTS) -> dict[str, float | None]:
    v = np.asarray(values, dtype=float).ravel()
    if v.size == 0:
        return {f"p{p:02d}": None for p in pcts}
    return {f"p{p:02d}": float(q) for p, q in zip(pcts, np.percentile(v, pcts))}


def geometry_diagnostics(
    object_points_m: np.ndarray,
    support_points_m: np.ndarray,
    plane: Plane,
    up: np.ndarray,
) -> dict[str, Any]:
    """Numeric geometry diagnostics for a successful measurement.

    Mirrors ``extract_supported_dimensions`` exactly (same deterministic PCA box
    and ``max |plane distance|`` height), so these values describe the reported
    dimensions — they do not recompute or alter them."""
    obj = np.asarray(object_points_m, dtype=float)
    support = np.asarray(support_points_m, dtype=float)
    up = np.asarray(up, dtype=float)
    out: dict[str, Any] = {}

    # Support plane.
    out["support_plane_normal_xyz"] = [float(c) for c in plane.normal]
    out["support_plane_offset_m"] = float(plane.offset)
    out["support_plane_inlier_count"] = int(plane.inlier_mask.sum())
    out["support_plane_inlier_ratio"] = float(plane.inlier_mask.mean())

    # Object / support depth (camera-frame Z, metres).
    obj_z = obj[:, 2]
    out.update({f"object_depth_{k}": v for k, v in _percentiles(obj_z).items()})
    out["object_depth_min"] = float(obj_z.min()) if obj_z.size else None
    out["object_depth_max"] = float(obj_z.max()) if obj_z.size else None
    sup_z = support[:, 2] if support.size else support
    out.update({f"support_depth_{k}": v for k, v in _percentiles(sup_z).items()})

    # Object distance above the support plane (signed along `up`), metres —
    # same measure as segment_object_points uses to keep points above the floor.
    dist_up = point_plane_distance(obj, plane) * np.sign(float(up @ plane.normal))
    out.update({f"object_plane_distance_{k}_m": v for k, v in _percentiles(dist_up).items()})
    out["object_plane_distance_max_m"] = float(dist_up.max()) if dist_up.size else None

    # Oriented-box stage, instrumented (not changed): replicates
    # normalize_axes_to_lwh's axis selection and extract_supported_dimensions'
    # height, read-only.
    box = oriented_box(obj)
    alignment = np.abs(box.axes.T @ (up / np.linalg.norm(up)))
    vertical = int(np.argmax(alignment))
    horizontal = [i for i in range(3) if i != vertical]
    longer, shorter = sorted(horizontal, key=lambda i: box.extents[i], reverse=True)
    out["raw_obb_extents_m"] = [float(e) for e in box.extents]
    out["raw_obb_axes"] = [[float(c) for c in row] for row in box.axes]
    out["up_vector_xyz"] = [float(c) for c in up]
    out["obb_axis_up_alignment"] = [float(a) for a in alignment]
    out["selected_vertical_axis_index"] = vertical
    out["horizontal_extent_length_m"] = float(box.extents[longer])
    out["horizontal_extent_width_m"] = float(box.extents[shorter])
    out["computed_height_m"] = float(np.abs(point_plane_distance(obj, plane)).max())
    return out


def _mask_bbox(mask: np.ndarray) -> list[int] | None:
    ys, xs = np.nonzero(np.asarray(mask, dtype=bool))
    if ys.size == 0:
        return None
    return [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]


def image_space_diagnostics(
    object_mask: np.ndarray,
    detection_bbox_xyxy: tuple[float, float, float, float],
) -> dict[str, Any]:
    """Pixel-space diagnostics: detector bbox, SAM mask bbox, image size."""
    mask = np.asarray(object_mask, dtype=bool)
    h, w = mask.shape
    dx0, dy0, dx1, dy1 = (float(v) for v in detection_bbox_xyxy)
    out: dict[str, Any] = {
        "image_width_px": int(w),
        "image_height_px": int(h),
        "detected_bbox_xyxy": [dx0, dy0, dx1, dy1],
        "detected_bbox_width_px": dx1 - dx0,
        "detected_bbox_height_px": dy1 - dy0,
    }
    mb = _mask_bbox(mask)
    out["sam_mask_bbox_xyxy"] = mb
    out["sam_mask_width_px"] = None if mb is None else mb[2] - mb[0] + 1
    out["sam_mask_height_px"] = None if mb is None else mb[3] - mb[1] + 1
    return out


def support_inlier_pixel_mask(
    depth_m: np.ndarray,
    support_mask: np.ndarray,
    plane: Plane,
) -> np.ndarray:
    """``(H, W)`` bool of support pixels that are RANSAC plane inliers.

    Reconstructs the exact pixel order ``backproject_depth`` produced (row-major
    over finite, positive, support pixels), so ``plane.inlier_mask`` — which is
    indexed over those same support points — scatters back 1:1."""
    depth = np.asarray(depth_m, dtype=float)
    valid = np.isfinite(depth) & (depth > 0) & np.asarray(support_mask, dtype=bool)
    out = np.zeros(depth.shape, dtype=bool)
    out[valid] = plane.inlier_mask
    return out
