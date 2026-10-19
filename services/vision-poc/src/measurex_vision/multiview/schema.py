"""The M9 capture-bundle contract and its strict input validation.

A *capture bundle* is a portable, offline multi-frame sequence: RGB frames, their
object masks, per-frame intrinsics and **metric** camera poses. One manifest file
(``capture.json``) describes it. The reconstruction core consumes :class:`ViewFrame`
objects, so it is decoupled from both the file format and any segmentation model —
synthetic tests build ``ViewFrame`` lists in memory with no file I/O.

Pose convention is fixed (see :mod:`.camera`): ``X_world = T_world_from_camera @
X_camera``, translations in metres.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np

from ..geometry.intrinsics import CameraIntrinsics
from . import camera as cam

SCHEMA_VERSION = 1
POSE_CONVENTION = "T_world_from_camera"
UNITS = "meters"


class FailureCode(str, Enum):
    """Typed reasons the metric reconstruction refuses. A METRIC request never
    silently degrades to an estimate — it fails with one of these instead."""

    METRIC_POSE_UNAVAILABLE = "metric_pose_unavailable"
    INVALID_POSE = "invalid_pose"
    INVALID_INTRINSICS = "invalid_intrinsics"
    INSUFFICIENT_FRAMES = "insufficient_frames"
    INSUFFICIENT_BASELINE = "insufficient_baseline"
    INSUFFICIENT_VIEW_COVERAGE = "insufficient_view_coverage"
    INVALID_GRAVITY = "invalid_gravity"
    MASK_MISMATCH = "mask_mismatch"
    RECONSTRUCTION_FAILED = "reconstruction_failed"
    INSUFFICIENT_HULL_SUPPORT = "insufficient_hull_support"


class MetricReconstructionError(Exception):
    """A typed reconstruction failure carrying a :class:`FailureCode`."""

    def __init__(self, code: FailureCode, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code.value}: {detail}" if detail else code.value)


@dataclass(frozen=True)
class ReconstructionConfig:
    """Explicit, GT-free reconstruction parameters. Defaults are chosen from
    geometry/memory reasoning, never tuned to any particular test carton."""

    min_frames: int = 4
    min_total_baseline_m: float = 0.10     # summed camera travel (metres)
    min_view_coverage_deg: float = 20.0    # max pairwise view angle at the object
    consensus: float = 1.0                 # fraction of usable frames a voxel needs
    # 1.0 is the true visual hull (voxel must lie inside every view that sees it).
    # Lower it only for noisy real masks — below 1.0 inflates the hull.
    # Voxel sizes are adaptive: resolution scales with the object so relative
    # accuracy is size-independent. Divisions set voxels-per-span; min_voxel_m is
    # the memory floor. coarse_voxel_m/fine_voxel_m override to a fixed size.
    coarse_divisions: int = 48
    fine_divisions: int = 90
    min_voxel_m: float = 0.0015
    coarse_voxel_m: float | None = None    # explicit override (else adaptive)
    fine_voxel_m: float | None = None      # explicit override (else adaptive)
    max_voxels: int = 24_000_000           # hard memory guard (coarse + fine)
    roi_safety: float = 1.6                # ROI half-extent = bound * safety
    roi_max_half_extent_m: float = 1.5     # absolute cap so bad input cannot explode
    min_occupied_voxels: int = 64
    leave_one_out: bool = True
    leave_one_out_max_runs: int = 6        # cap LOO reconstructions (cost guard)
    max_dim_spread_frac: float = 0.10      # LOO relative spread gate per dimension


@dataclass(frozen=True)
class ViewFrame:
    """One usable view: a boolean object mask plus its metric camera.

    ``mask`` is ``(H, W)`` bool, ``True`` on the object — the same mask
    representation the M8 pipeline uses, so precomputed masks from any source drop
    in unchanged."""

    frame_id: str
    mask: np.ndarray
    intrinsics: CameraIntrinsics
    T_world_from_camera: np.ndarray

    @property
    def height(self) -> int:
        return int(self.mask.shape[0])

    @property
    def width(self) -> int:
        return int(self.mask.shape[1])


@dataclass(frozen=True)
class CaptureBundle:
    """A validated capture sequence ready for reconstruction."""

    frames: list[ViewFrame]
    gravity_world: np.ndarray            # unit vector; "up" is its negation
    pose_source: str
    support_plane: dict[str, Any] | None = None  # optional {normal, offset} in world metres
    meta: dict[str, Any] = field(default_factory=dict)


def _unit(v: np.ndarray, code: FailureCode, what: str) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    n = float(np.linalg.norm(v))
    if v.shape != (3,) or not np.isfinite(n) or n < 1e-6:
        raise MetricReconstructionError(code, f"{what} is not a valid 3-vector: {v}")
    return v / n


def validate_bundle(bundle: CaptureBundle, config: ReconstructionConfig) -> None:
    """Run every pose/intrinsics/mask/gravity/frame-count/observability check that
    does not need carving. Raises :class:`MetricReconstructionError` on the first
    failure. Geometry-dependent checks (baseline, view coverage) run against the
    object locus estimated from the central rays."""
    frames = bundle.frames
    if len(frames) < config.min_frames:
        raise MetricReconstructionError(
            FailureCode.INSUFFICIENT_FRAMES,
            f"{len(frames)} frame(s) < required {config.min_frames}",
        )

    _unit(bundle.gravity_world, FailureCode.INVALID_GRAVITY, "gravity_world")

    for f in frames:
        if f.mask.ndim != 2 or f.mask.dtype != np.bool_:
            raise MetricReconstructionError(
                FailureCode.MASK_MISMATCH, f"frame {f.frame_id}: mask must be 2D bool"
            )
        try:
            cam.validate_intrinsics(f.intrinsics, f.width, f.height)
        except cam.InvalidIntrinsics as e:
            raise MetricReconstructionError(FailureCode.INVALID_INTRINSICS, str(e)) from e
        try:
            cam.validate_pose(f.T_world_from_camera)
        except cam.InvalidPose as e:
            raise MetricReconstructionError(FailureCode.INVALID_POSE, str(e)) from e
        if not f.mask.any():
            raise MetricReconstructionError(
                FailureCode.MASK_MISMATCH, f"frame {f.frame_id}: empty mask"
            )

    # Observability: meaningful metric baseline and viewpoint diversity.
    poses = [f.T_world_from_camera for f in frames]
    total_baseline = sum(
        cam.baseline(poses[i], poses[i + 1]) for i in range(len(poses) - 1)
    )
    if total_baseline < config.min_total_baseline_m:
        raise MetricReconstructionError(
            FailureCode.INSUFFICIENT_BASELINE,
            f"total camera travel {total_baseline * 1000:.0f} mm "
            f"< required {config.min_total_baseline_m * 1000:.0f} mm",
        )

    locus = _object_locus(frames)
    max_angle = max(
        (
            cam.view_angle(poses[i], poses[j], locus)
            for i in range(len(poses))
            for j in range(i + 1, len(poses))
        ),
        default=0.0,
    )
    if max_angle < config.min_view_coverage_deg:
        raise MetricReconstructionError(
            FailureCode.INSUFFICIENT_VIEW_COVERAGE,
            f"max view angle {max_angle:.1f} deg < required "
            f"{config.min_view_coverage_deg:.1f} deg",
        )


def _object_locus(frames: list[ViewFrame]) -> np.ndarray:
    """World point nearest the central (mask-centroid) rays of all frames."""
    origins, dirs = [], []
    for f in frames:
        ys, xs = np.nonzero(f.mask)
        o, d = cam.pixel_ray(f.intrinsics, f.T_world_from_camera, xs.mean(), ys.mean())
        origins.append(o)
        dirs.append(d)
    try:
        return cam.nearest_point_to_rays(np.array(origins), np.array(dirs))
    except np.linalg.LinAlgError as e:
        raise MetricReconstructionError(
            FailureCode.INSUFFICIENT_VIEW_COVERAGE, "central rays are parallel"
        ) from e


# ---------------------------------------------------------------------------
# Offline manifest I/O (capture.json). Masks load lazily via Pillow (dev extra);
# the reconstruction core itself needs no image library.
# ---------------------------------------------------------------------------

def load_bundle(manifest_path: str) -> CaptureBundle:
    """Load and parse a ``capture.json`` manifest into a :class:`CaptureBundle`.

    Does not run :func:`validate_bundle` — the caller does, so validation failures
    stay typed. Rejects the wrong pose convention / units up front (that is a
    contract error, not a measurement failure)."""
    with open(manifest_path, encoding="utf-8") as fh:
        doc = json.load(fh)
    if doc.get("pose_convention") != POSE_CONVENTION:
        raise ValueError(f"pose_convention must be {POSE_CONVENTION!r}, got {doc.get('pose_convention')!r}")
    if doc.get("units") != UNITS:
        raise ValueError(f"units must be {UNITS!r}, got {doc.get('units')!r}")

    base = os.path.dirname(os.path.abspath(manifest_path))
    frames: list[ViewFrame] = []
    for fr in doc["frames"]:
        k = fr["intrinsics"]
        intr = CameraIntrinsics(fx=float(k["fx"]), fy=float(k["fy"]), cx=float(k["cx"]), cy=float(k["cy"]))
        mask = _load_mask(os.path.join(base, fr["mask"]), int(k["width"]), int(k["height"]))
        frames.append(
            ViewFrame(
                frame_id=str(fr["frame_id"]),
                mask=mask,
                intrinsics=intr,
                T_world_from_camera=np.asarray(fr["T_world_from_camera"], dtype=float),
            )
        )
    gravity = np.asarray(doc.get("gravity_world", [0.0, 1.0, 0.0]), dtype=float)
    return CaptureBundle(
        frames=frames,
        gravity_world=gravity,
        pose_source=str(doc.get("pose_source", "external_metric_pose")),
        support_plane=doc.get("support_plane"),
        meta={"schema_version": doc.get("schema_version"), "measurement_tier": doc.get("measurement_tier")},
    )


def _load_mask(path: str, width: int, height: int) -> np.ndarray:
    from PIL import Image  # dev/seg extra; never needed for in-memory synthetic tests

    with Image.open(path) as img:
        arr = np.asarray(img.convert("L"))
    if arr.shape != (height, width):
        raise MetricReconstructionError(
            FailureCode.MASK_MISMATCH,
            f"{path}: mask {arr.shape} != declared ({height}, {width})",
        )
    return arr > 127
