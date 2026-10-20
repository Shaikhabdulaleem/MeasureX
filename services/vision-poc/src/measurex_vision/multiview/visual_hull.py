"""Metric visual-hull (space-carving) reconstruction — pure NumPy, CPU-correct.

Given object masks, intrinsics and metric camera poses, carve a world-space voxel
volume: a voxel survives when it projects in front of the camera, inside the image
and inside the object mask for a configurable consensus of the frames that can see
it. Absolute scale comes entirely from the metric camera poses (metres) — no
monocular depth and no reference object. This is the primary M9 geometry because
cartons are weakly textured, where feature triangulation fails but silhouettes do
not.

Correctness before speed: a single coarse-to-fine pair of dense carves, memory
bounded by an explicit voxel cap. GPU/octree optimisation is deliberately out of
scope for the research spike.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import camera as cam
from .schema import (
    CaptureBundle,
    FailureCode,
    MetricReconstructionError,
    ReconstructionConfig,
    ViewFrame,
    _object_locus,
)


@dataclass(frozen=True)
class CarveResult:
    points_m: np.ndarray            # (K, 3) occupied voxel centres, world metres
    voxel_size_m: float
    initial_voxel_count: int
    silhouette_agreement: list[float]  # per-frame fraction of occupied voxels inside its mask


def estimate_roi(bundle: CaptureBundle, config: ReconstructionConfig) -> tuple[np.ndarray, float]:
    """Conservative isotropic ROI ``(centre, half_extent_m)`` from camera geometry.

    Centre is the world point nearest the central rays. The half-extent bounds the
    object from each view's mask solid-angle at that view's distance
    (``distance * tan(angular_radius)``), takes the largest, applies a safety
    factor and an absolute cap. Derived from rays/intrinsics only — never from any
    known carton size."""
    centre = _object_locus(bundle.frames)
    bound = 0.0
    for f in bundle.frames:
        ys, xs = np.nonzero(f.mask)
        radius_px = 0.5 * max(xs.max() - xs.min(), ys.max() - ys.min())
        focal = 0.5 * (f.intrinsics.fx + f.intrinsics.fy)
        distance = float(np.linalg.norm(cam.camera_center(f.T_world_from_camera) - centre))
        bound = max(bound, distance * np.tan(np.arctan(radius_px / focal)))
    half = min(bound * config.roi_safety, config.roi_max_half_extent_m)
    if not np.isfinite(half) or half <= 0:
        raise MetricReconstructionError(FailureCode.RECONSTRUCTION_FAILED, "degenerate ROI")
    return centre, float(half)


def _grid_centres(lo: np.ndarray, hi: np.ndarray, voxel: float, max_voxels: int) -> np.ndarray:
    """Voxel-centre coordinates filling the box ``[lo, hi]`` at spacing ``voxel``."""
    axes = [np.arange(lo[i] + voxel / 2.0, hi[i], voxel) for i in range(3)]
    counts = [max(1, len(a)) for a in axes]
    total = counts[0] * counts[1] * counts[2]
    if total > max_voxels:
        raise MetricReconstructionError(
            FailureCode.RECONSTRUCTION_FAILED,
            f"voxel grid {counts} = {total} exceeds cap {max_voxels}",
        )
    gx, gy, gz = np.meshgrid(*axes, indexing="ij")
    return np.stack([gx.ravel(), gy.ravel(), gz.ravel()], axis=-1)


def _support_filter(centres: np.ndarray, support_plane: dict | None, voxel: float) -> np.ndarray:
    """Drop voxel centres below the support plane (if any), keeping one voxel of
    tolerance. Prunes the downward silhouette cone an above-only capture produces,
    so the fine grid stays small."""
    if support_plane is None:
        return centres
    n = np.asarray(support_plane["normal"], dtype=float)
    n = n / np.linalg.norm(n)
    d = float(support_plane["offset"])
    return centres[centres @ n + d >= -voxel]


def carve(
    frames: list[ViewFrame],
    lo: np.ndarray,
    hi: np.ndarray,
    voxel: float,
    *,
    consensus: float,
    max_voxels: int,
    min_usable_views: int = 1,
    support_plane: dict | None = None,
) -> CarveResult:
    """Carve the box ``[lo, hi]`` against every frame's silhouette.

    For each voxel, a frame is *usable* if the voxel projects in front of the
    camera and inside the image; the voxel *agrees* with that frame if it also
    lands inside the mask. A voxel survives when it is seen by at least
    ``min_usable_views`` frames and ``agree / usable >= consensus`` (so a minority
    of masks with minor errors cannot delete a real voxel, and a voxel constrained
    by only a single ray — unobservable in depth — cannot belong to the hull)."""
    centres = _support_filter(_grid_centres(lo, hi, voxel, max_voxels), support_plane, voxel)
    initial = centres.shape[0]
    if initial == 0:
        return CarveResult(centres, voxel, 0, [0.0 for _ in frames])
    usable = np.zeros(initial, dtype=np.int32)
    agree = np.zeros(initial, dtype=np.int32)

    for f in frames:
        P = cam.projection_matrix(f.intrinsics, f.T_world_from_camera)
        pixels, depth = cam.project_world(P, centres)
        u = np.round(pixels[:, 0]).astype(np.int64)
        v = np.round(pixels[:, 1]).astype(np.int64)
        in_img = (depth > 1e-6) & (u >= 0) & (u < f.width) & (v >= 0) & (v < f.height)
        usable += in_img
        hit = np.zeros(initial, dtype=bool)
        idx = np.nonzero(in_img)[0]
        hit[idx] = f.mask[v[idx], u[idx]]
        agree += hit

    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = np.where(usable > 0, agree / np.maximum(usable, 1), 0.0)
    occupied = (usable >= max(min_usable_views, 1)) & (ratio >= consensus)
    pts = centres[occupied]

    # Per-frame silhouette agreement over the surviving voxels (diagnostic).
    agreement: list[float] = []
    for f in frames:
        if pts.shape[0] == 0:
            agreement.append(0.0)
            continue
        P = cam.projection_matrix(f.intrinsics, f.T_world_from_camera)
        pixels, depth = cam.project_world(P, pts)
        u = np.round(pixels[:, 0]).astype(np.int64)
        v = np.round(pixels[:, 1]).astype(np.int64)
        inb = (depth > 1e-6) & (u >= 0) & (u < f.width) & (v >= 0) & (v < f.height)
        if not inb.any():
            agreement.append(0.0)
            continue
        inside = f.mask[v[inb], u[inb]]
        agreement.append(float(inside.mean()))
    return CarveResult(pts, voxel, initial, agreement)


def reconstruct_hull(bundle: CaptureBundle, config: ReconstructionConfig) -> CarveResult:
    """Coarse-to-fine carve: a coarse pass over the ROI, then a fine pass over the
    tightened occupied bounds. Returns the fine occupied cloud."""
    centre, half = estimate_roi(bundle, config)
    lo = centre - half
    hi = centre + half

    coarse_voxel = config.coarse_voxel_m or max(2 * half / config.coarse_divisions, config.min_voxel_m)
    coarse = carve(
        bundle.frames, lo, hi, coarse_voxel,
        consensus=config.consensus, max_voxels=config.max_voxels,
        min_usable_views=config.min_usable_views,
        support_plane=bundle.support_plane,
    )
    if coarse.points_m.shape[0] < config.min_occupied_voxels:
        raise MetricReconstructionError(
            FailureCode.INSUFFICIENT_HULL_SUPPORT,
            f"coarse carve kept {coarse.points_m.shape[0]} voxel(s) "
            f"< required {config.min_occupied_voxels}",
        )

    flo = coarse.points_m.min(axis=0) - coarse_voxel
    fhi = coarse.points_m.max(axis=0) + coarse_voxel
    span_max = float((fhi - flo).max())
    fine_voxel = config.fine_voxel_m or max(span_max / config.fine_divisions, config.min_voxel_m)
    fine = carve(
        bundle.frames, flo, fhi, fine_voxel,
        consensus=config.consensus, max_voxels=config.max_voxels,
        min_usable_views=config.min_usable_views,
        support_plane=bundle.support_plane,
    )
    if fine.points_m.shape[0] < config.min_occupied_voxels:
        raise MetricReconstructionError(
            FailureCode.INSUFFICIENT_HULL_SUPPORT,
            f"fine carve kept {fine.points_m.shape[0]} voxel(s)",
        )
    return fine
