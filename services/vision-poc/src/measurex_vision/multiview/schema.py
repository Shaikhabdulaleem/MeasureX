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
    INVALID_SUPPORT_PLANE = "invalid_support_plane"
    MASK_MISMATCH = "mask_mismatch"
    RECONSTRUCTION_FAILED = "reconstruction_failed"
    INSUFFICIENT_HULL_SUPPORT = "insufficient_hull_support"
    # Quality gates: a METRIC result fails when geometry is not observable enough.
    UNSTABLE_RECONSTRUCTION = "unstable_reconstruction"
    INSUFFICIENT_SILHOUETTE_CONSISTENCY = "insufficient_silhouette_consistency"
    # Parametric cuboid fit (see cuboid_fit.py): the optimiser converged but the
    # metric dimensions are not identifiable / stable enough to trust.
    CUBOID_FIT_FAILED = "cuboid_fit_failed"
    AMBIGUOUS_CUBOID_FIT = "ambiguous_cuboid_fit"
    UNSTABLE_CUBOID_FIT = "unstable_cuboid_fit"


class MetricReconstructionError(Exception):
    """A typed reconstruction failure carrying a :class:`FailureCode`."""

    def __init__(self, code: FailureCode, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code.value}: {detail}" if detail else code.value)


class ContractError(ValueError):
    """A capture manifest violates the fixed bundle contract (wrong schema
    version, tier, pose convention, units, or a missing/mismatched file). Distinct
    from :class:`MetricReconstructionError`, which is a geometry/observability
    failure of an otherwise well-formed bundle. An ESTIMATE manifest is rejected
    here — it is never silently accepted as METRIC."""


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
    min_usable_views: int = 2              # a voxel must project into >= this many
    # frames before it can belong to the metric hull. A voxel seen by a single
    # camera is unconstrained in depth along that ray, so one-view survivors are
    # not metrically supported. GT-independent (never fit to a test carton).
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
    min_silhouette_consistency: float = 0.6  # min per-frame silhouette agreement
    # Below these, a METRIC result is refused (success=False) rather than returned:
    # weak silhouette consistency or a large leave-one-out spread means the
    # geometry is not observable enough to trust the dimensions.


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


def canonical_support_plane(support_plane: dict[str, Any] | None, up: np.ndarray) -> dict[str, Any] | None:
    """Return the support plane with its normal oriented toward gravity-``up``.

    The same geometric plane has two ``(normal, offset)`` encodings. Downstream
    signed half-space tests ("is this point above the plane?") depend on which one
    they receive, so M9 fixes one convention: **the normal points toward
    gravity-up**. If the supplied normal points the other way, flip both the normal
    and the offset (same plane, opposite labelled side)."""
    if support_plane is None or "normal" not in support_plane or "offset" not in support_plane:
        return support_plane
    n = np.asarray(support_plane["normal"], dtype=float)
    offset = float(support_plane["offset"])
    if float(n @ up) < 0.0:
        n, offset = -n, -offset
    return {**support_plane, "normal": [float(x) for x in n], "offset": offset}


@dataclass(frozen=True)
class CaptureBundle:
    """A validated capture sequence ready for reconstruction."""

    frames: list[ViewFrame]
    gravity_world: np.ndarray            # unit vector; "up" is its negation
    pose_source: str
    support_plane: dict[str, Any] | None = None  # optional {normal, offset} in world metres
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Canonicalise the support-plane normal once, at the single point every
        # bundle passes through, so no downstream consumer has to care about the
        # supplied sign (see canonical_support_plane).
        g = np.asarray(self.gravity_world, dtype=float)
        gn = float(np.linalg.norm(g))
        if self.support_plane is not None and np.isfinite(gn) and gn > 1e-9:
            canon = canonical_support_plane(self.support_plane, -g / gn)
            object.__setattr__(self, "support_plane", canon)


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

    up = -_unit(bundle.gravity_world, FailureCode.INVALID_GRAVITY, "gravity_world")
    _validate_support_plane(bundle.support_plane, up)

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


def _validate_support_plane(support_plane: dict[str, Any] | None, up: np.ndarray) -> None:
    """Validate an optional metric support plane ``{normal, offset}`` (world
    metres). The normal must be a finite, non-zero 3-vector and the offset finite.
    Allowed orientation: the plane is roughly horizontal, so its normal is within
    45° of "up" (either sign) — a carton rests on it. A wildly tilted plane is a
    capture/units bug, not a floor, and is rejected."""
    if support_plane is None:
        return
    if "normal" not in support_plane or "offset" not in support_plane:
        raise MetricReconstructionError(
            FailureCode.INVALID_SUPPORT_PLANE, f"support_plane needs normal+offset, got {support_plane}"
        )
    n = _unit(support_plane["normal"], FailureCode.INVALID_SUPPORT_PLANE, "support_plane.normal")
    offset = support_plane["offset"]
    if not np.isfinite(float(offset)):
        raise MetricReconstructionError(
            FailureCode.INVALID_SUPPORT_PLANE, f"support_plane.offset not finite: {offset}"
        )
    if abs(float(n @ up)) < np.cos(np.radians(45.0)):
        raise MetricReconstructionError(
            FailureCode.INVALID_SUPPORT_PLANE,
            f"support plane normal {n} is >45 deg from gravity-up {up} (not a floor)",
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

    Enforces the fixed bundle contract up front and raises :class:`ContractError`
    on any violation — a wrong schema version/tier/convention/units, a non-list or
    empty ``frames``, or a missing/mismatched image or mask file. An ESTIMATE
    manifest is rejected here, never silently accepted as METRIC. Geometry and
    observability (poses, baseline, coverage, gravity) are checked separately by
    :func:`validate_bundle`, so those stay :class:`MetricReconstructionError`."""
    with open(manifest_path, encoding="utf-8") as fh:
        doc = json.load(fh)

    def _require(key: str, expected: Any) -> None:
        if doc.get(key) != expected:
            raise ContractError(f"{key} must be {expected!r}, got {doc.get(key)!r}")

    _require("schema_version", SCHEMA_VERSION)
    _require("measurement_tier", "metric")
    _require("pose_convention", POSE_CONVENTION)
    _require("units", UNITS)

    doc_frames = doc.get("frames")
    if not isinstance(doc_frames, list) or not doc_frames:
        raise ContractError(f"frames must be a non-empty list, got {type(doc_frames).__name__}")

    base = os.path.dirname(os.path.abspath(manifest_path))
    frames: list[ViewFrame] = []
    for fr in doc_frames:
        k = fr["intrinsics"]
        intr = CameraIntrinsics(fx=float(k["fx"]), fy=float(k["fy"]), cx=float(k["cx"]), cy=float(k["cy"]))
        if "image" in fr and not os.path.exists(os.path.join(base, fr["image"])):
            raise ContractError(f"frame {fr.get('frame_id')}: image {fr['image']!r} does not exist")
        mask_path = os.path.join(base, fr["mask"])
        if not os.path.exists(mask_path):
            raise ContractError(f"frame {fr.get('frame_id')}: mask {fr['mask']!r} does not exist")
        mask = _load_mask(mask_path, int(k["width"]), int(k["height"]))
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
        raise ContractError(f"{path}: mask {arr.shape} != declared ({height}, {width})")
    return arr > 127
