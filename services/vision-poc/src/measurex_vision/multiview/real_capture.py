"""M9 real-device capture: raw-bundle contract, validation, frame selection, fit
orchestration and (ground-truth-only) evaluation.

The Android capture app is a **data-capture instrument**: it records real RGB
frames, metric ARCore camera poses, per-frame intrinsics, gravity and an optional
support plane, but computes **no** dimensions. It cannot run segmentation, so it
writes a ``raw_capture.json`` (``capture_type == "m9_real_raw"``) *without* masks —
distinct from the strict ``capture.json`` (``measurement_tier == "metric"``) that
:mod:`.schema` consumes, which the offline preparation step produces once masks
exist.

This module holds the pure, GT-free offline logic that the ``scripts/m9_*`` CLIs
wrap: raw parsing + validation, azimuth-based 8-frame selection, and the 7-DOF /
6-DOF fit run. Ground truth enters **only** :func:`evaluate_runs` — never the raw
validator, the selector, the preparation step or the fitter. Pose convention is the
one fixed convention (see :mod:`.camera`): ``X_world = T_world_from_camera @
X_camera``, OpenCV camera axes (+X right, +Y down, +Z forward), metres.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..geometry.intrinsics import CameraIntrinsics
from . import camera as cam
from .carton import horizontal_basis, up_from_gravity
from .cuboid_fit import fit_cuboid, image_quantization_uncertainty
from .schema import ReconstructionConfig, load_bundle

RAW_SCHEMA_VERSION = 1
RAW_CAPTURE_TYPE = "m9_real_raw"
POSE_CONVENTION = "T_world_from_camera"
CAMERA_CONVENTION = "opencv_x_right_y_down_z_forward"
UNITS = "meters"

# Candidate-pool and selection targets (geometry-driven, never fit to a carton).
MIN_CANDIDATE_FRAMES = 12
MIN_VIEW_COVERAGE_DEG = 120.0
SELECT_FRAMES = 8
# A paired frame/image timestamp must describe the same camera observation. ARCore
# delivers the CPU image for the frame it came from, so the delta is ~0; allow a
# small slack for clock representation, well under one 30 FPS interval (33 ms).
MAX_TIMESTAMP_DELTA_NS = 5_000_000  # 5 ms


class RawCaptureError(ValueError):
    """A ``raw_capture.json`` violates the raw-bundle contract (wrong schema
    version / capture type / convention / units, or a malformed frame)."""


@dataclass(frozen=True)
class RawFrame:
    frame_id: str
    frame_timestamp_ns: int
    image_timestamp_ns: int
    image: str
    intrinsics: dict[str, float]
    T_world_from_camera: np.ndarray
    tracking_state: str
    guidance_angle_deg: float | None = None
    camera_distance_to_target_m: float | None = None

    @property
    def timestamp_delta_ns(self) -> int:
        return int(self.frame_timestamp_ns) - int(self.image_timestamp_ns)

    def camera_intrinsics(self) -> CameraIntrinsics:
        k = self.intrinsics
        return CameraIntrinsics(fx=float(k["fx"]), fy=float(k["fy"]), cx=float(k["cx"]), cy=float(k["cy"]))


@dataclass(frozen=True)
class RawCapture:
    pose_source: str
    gravity_world: np.ndarray
    frames: list[RawFrame]
    guidance_target_world: np.ndarray | None = None
    support_plane: dict[str, Any] | None = None
    device: dict[str, Any] = field(default_factory=dict)
    doc: dict[str, Any] = field(default_factory=dict)


def load_raw_capture(path: str) -> RawCapture:
    """Parse and structurally validate a ``raw_capture.json`` manifest.

    Enforces the raw-bundle contract (schema version, capture type, pose/camera
    convention, units, a non-empty frame list, required per-frame keys) and raises
    :class:`RawCaptureError` on any violation. Geometry/observability checks live in
    :func:`validate_raw_capture`."""
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)

    def _require(key: str, expected: Any) -> None:
        if doc.get(key) != expected:
            raise RawCaptureError(f"{key} must be {expected!r}, got {doc.get(key)!r}")

    _require("schema_version", RAW_SCHEMA_VERSION)
    _require("capture_type", RAW_CAPTURE_TYPE)
    _require("pose_convention", POSE_CONVENTION)
    _require("camera_convention", CAMERA_CONVENTION)
    _require("units", UNITS)

    doc_frames = doc.get("frames")
    if not isinstance(doc_frames, list) or not doc_frames:
        raise RawCaptureError(f"frames must be a non-empty list, got {type(doc_frames).__name__}")

    frames: list[RawFrame] = []
    for fr in doc_frames:
        try:
            intr = fr["intrinsics"]
            for k in ("fx", "fy", "cx", "cy", "width", "height"):
                if k not in intr:
                    raise RawCaptureError(f"frame {fr.get('frame_id')}: intrinsics missing {k!r}")
            T = np.asarray(fr["T_world_from_camera"], dtype=float)
            if T.shape != (4, 4):
                raise RawCaptureError(f"frame {fr.get('frame_id')}: T_world_from_camera must be 4x4")
            frames.append(
                RawFrame(
                    frame_id=str(fr["frame_id"]),
                    frame_timestamp_ns=int(fr["frame_timestamp_ns"]),
                    image_timestamp_ns=int(fr["image_timestamp_ns"]),
                    image=str(fr["image"]),
                    intrinsics={k: float(intr[k]) for k in ("fx", "fy", "cx", "cy", "width", "height")},
                    T_world_from_camera=T,
                    tracking_state=str(fr.get("tracking_state", "")),
                    guidance_angle_deg=_opt_float(fr.get("guidance_angle_deg")),
                    camera_distance_to_target_m=_opt_float(fr.get("camera_distance_to_target_m")),
                )
            )
        except (KeyError, TypeError, ValueError) as e:
            if isinstance(e, RawCaptureError):
                raise
            raise RawCaptureError(f"frame {fr.get('frame_id')}: malformed ({e})") from e

    gt = doc.get("guidance_target_world")
    return RawCapture(
        pose_source=str(doc.get("pose_source", "arcore")),
        gravity_world=np.asarray(doc.get("gravity_world", [0.0, -1.0, 0.0]), dtype=float),
        frames=frames,
        guidance_target_world=np.asarray(gt, dtype=float) if gt is not None else None,
        support_plane=doc.get("support_plane"),
        device=doc.get("device", {}),
        doc=doc,
    )


def _opt_float(v: Any) -> float | None:
    return None if v is None else float(v)


# ---------------------------------------------------------------------------
# Azimuth geometry (gravity-up). Shared by validation and selection.
# ---------------------------------------------------------------------------

def _up(gravity_world: np.ndarray) -> np.ndarray:
    """Gravity-up unit vector: M9 up is the negation of ``gravity_world`` (the
    direction gravity points). In the normal ARCore world (+Y up) gravity_world is
    ``[0, -1, 0]`` and up is ``[0, +1, 0]``."""
    return up_from_gravity(np.asarray(gravity_world, dtype=float))


def object_target(raw: RawCapture) -> np.ndarray:
    """The world point used as the azimuth pivot: the exported guidance target when
    present, else the mean camera centre (never ground truth)."""
    if raw.guidance_target_world is not None:
        return np.asarray(raw.guidance_target_world, dtype=float)
    centres = np.array([cam.camera_center(f.T_world_from_camera) for f in raw.frames])
    return centres.mean(axis=0)


def frame_azimuths_deg(raw: RawCapture) -> dict[str, float]:
    """Azimuth (degrees, [-180, 180]) of each camera centre around the target in the
    horizontal plane defined by gravity-up — the viewpoint position on the sweep."""
    up = _up(raw.gravity_world)
    a, b = horizontal_basis(up)
    target = object_target(raw)
    out: dict[str, float] = {}
    for f in raw.frames:
        c = cam.camera_center(f.T_world_from_camera)
        d = c - target
        d = d - (d @ up) * up  # project onto the horizontal plane
        out[f.frame_id] = float(np.degrees(np.arctan2(d @ b, d @ a)))
    return out


def coverage_deg(azimuths: list[float]) -> float:
    """Angular extent (degrees) spanned by a set of azimuths on the circle: the
    contiguous arc that contains them all, i.e. ``360 - largest_gap``. A full ring
    gives ~360; a 120 deg front sweep gives ~120."""
    if len(azimuths) < 2:
        return 0.0
    s = sorted((a % 360.0) for a in azimuths)
    gaps = [s[i + 1] - s[i] for i in range(len(s) - 1)]
    gaps.append(360.0 - s[-1] + s[0])  # wrap-around gap
    return 360.0 - max(gaps)


# ---------------------------------------------------------------------------
# Raw validation (GT-free). Produces an explicit diagnostics report.
# ---------------------------------------------------------------------------

def validate_raw_capture(raw: RawCapture, base_dir: str) -> dict[str, Any]:
    """Validate raw geometry before any segmentation: schema already parsed, this
    checks images exist, poses are finite proper rigid transforms, image /
    intrinsics dimensions agree, timestamps are paired, tracking is TRACKING,
    gravity is valid, the candidate baseline and view coverage clear the research
    minimums, and the optional support plane is a valid gravity-up floor.

    Returns a diagnostics dict with ``ok`` and a list of named check results. Does
    **not** run segmentation — an invalid raw geometry must stop the pipeline."""
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    # Poses finite + proper rotation.
    pose_fail = []
    for f in raw.frames:
        try:
            cam.validate_pose(f.T_world_from_camera)
        except cam.InvalidPose as e:
            pose_fail.append(f"{f.frame_id}: {e}")
    add("poses_valid", not pose_fail, "; ".join(pose_fail))

    # Intrinsics finite + principal point plausible.
    intr_fail = []
    for f in raw.frames:
        try:
            cam.validate_intrinsics(
                f.camera_intrinsics(), int(f.intrinsics["width"]), int(f.intrinsics["height"])
            )
        except cam.InvalidIntrinsics as e:
            intr_fail.append(f"{f.frame_id}: {e}")
    add("intrinsics_valid", not intr_fail, "; ".join(intr_fail))

    # Images exist and (if readable) match the declared intrinsics dimensions.
    img_fail, dim_fail = [], []
    for f in raw.frames:
        p = os.path.join(base_dir, f.image)
        if not os.path.exists(p):
            img_fail.append(f"{f.frame_id}: {f.image} missing")
            continue
        wh = _image_size(p)
        if wh is not None and wh != (int(f.intrinsics["width"]), int(f.intrinsics["height"])):
            dim_fail.append(f"{f.frame_id}: image {wh} != intrinsics "
                            f"({int(f.intrinsics['width'])}, {int(f.intrinsics['height'])})")
    add("images_exist", not img_fail, "; ".join(img_fail))
    add("image_intrinsics_dims_agree", not dim_fail, "; ".join(dim_fail))

    # Timestamp pairing: each image must come from its frame observation.
    ts_fail = [
        f"{f.frame_id}: delta {f.timestamp_delta_ns} ns"
        for f in raw.frames
        if abs(f.timestamp_delta_ns) > MAX_TIMESTAMP_DELTA_NS
    ]
    add("timestamps_paired", not ts_fail, "; ".join(ts_fail))

    # Tracking must be TRACKING for every saved candidate.
    track_fail = [f.frame_id for f in raw.frames if f.tracking_state.upper() != "TRACKING"]
    add("tracking_all_tracking", not track_fail, f"non-tracking: {track_fail}")

    # Gravity a valid, roughly-unit non-zero vector.
    g = np.asarray(raw.gravity_world, dtype=float)
    gn = float(np.linalg.norm(g))
    add("gravity_valid", g.shape == (3,) and np.isfinite(gn) and gn > 1e-6, f"|g|={gn:.4f}")

    # Candidate pool size.
    add("candidate_count", len(raw.frames) >= MIN_CANDIDATE_FRAMES,
        f"{len(raw.frames)} candidate(s), need >= {MIN_CANDIDATE_FRAMES}")

    # Candidate baseline (summed camera travel, metres).
    poses = [f.T_world_from_camera for f in raw.frames]
    total_baseline = sum(cam.baseline(poses[i], poses[i + 1]) for i in range(len(poses) - 1))
    add("candidate_baseline", total_baseline >= ReconstructionConfig().min_total_baseline_m,
        f"{total_baseline * 1000:.0f} mm travel")

    # Candidate view coverage (azimuth arc around the target).
    cov = coverage_deg(list(frame_azimuths_deg(raw).values()))
    add("candidate_view_coverage", cov >= MIN_VIEW_COVERAGE_DEG,
        f"{cov:.0f} deg, need >= {MIN_VIEW_COVERAGE_DEG:.0f} deg")

    # Optional support plane: valid gravity-up floor when present.
    sp_ok, sp_detail = _validate_support_plane(raw.support_plane, _up(raw.gravity_world))
    add("support_plane_valid", sp_ok, sp_detail)

    ok = all(c["ok"] for c in checks)
    return {
        "ok": ok,
        "pose_source": raw.pose_source,
        "candidate_frames": len(raw.frames),
        "total_baseline_mm": total_baseline * 1000.0,
        "view_coverage_deg": cov,
        "support_plane_present": raw.support_plane is not None,
        "checks": checks,
    }


def _validate_support_plane(sp: dict[str, Any] | None, up: np.ndarray) -> tuple[bool, str]:
    if sp is None:
        return True, "no support plane (optional)"
    if "normal" not in sp or "offset" not in sp:
        return False, f"support_plane needs normal+offset, got {sp}"
    n = np.asarray(sp["normal"], dtype=float)
    norm = float(np.linalg.norm(n))
    if n.shape != (3,) or not np.isfinite(norm) or norm < 1e-6 or not np.isfinite(float(sp["offset"])):
        return False, f"support_plane normal/offset not finite: {sp}"
    cos = float((n / norm) @ up)
    if abs(cos) < np.cos(np.radians(45.0)):
        return False, f"support plane normal {list(n)} is >45 deg from gravity-up {list(up)}"
    return True, f"floor normal·up={cos:.3f}"


def _image_size(path: str) -> tuple[int, int] | None:
    """``(width, height)`` of an image, or None if Pillow is unavailable."""
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow is a dev/seg extra
        return None
    with Image.open(path) as img:
        return (img.width, img.height)


# ---------------------------------------------------------------------------
# 8-frame selection (GT-free): evenly spaced across the best contiguous arc.
# ---------------------------------------------------------------------------

def select_frames(raw: RawCapture, n: int = SELECT_FRAMES) -> dict[str, Any]:
    """Select ``n`` frames from the candidate pool for the strict capture, using
    only the exported guidance target and the metric camera centres — never the
    resulting dimensions.

    Keeps TRACKING candidates, orders them around the target by azimuth, takes the
    best contiguous ``>= MIN_VIEW_COVERAGE_DEG`` arc (the complement of the largest
    azimuth gap), picks ``n`` approximately evenly spaced positions across it, and
    returns the selection in **chronological** sweep order with its coverage,
    adjacent angular separations, baseline and camera-target distances."""
    usable = [f for f in raw.frames if f.tracking_state.upper() == "TRACKING"]
    az = frame_azimuths_deg(raw)
    if len(usable) < n:
        return {"ok": False, "reason": f"only {len(usable)} TRACKING candidate(s) < {n}",
                "selected_frame_ids": [], "coverage_deg": 0.0}

    # Order around the circle starting just after the largest gap → the contiguous
    # sweep. Unwrap azimuths so adjacent differences are the real angular steps.
    ordered = sorted(usable, key=lambda f: az[f.frame_id] % 360.0)
    circ = [az[f.frame_id] % 360.0 for f in ordered]
    gaps = [(circ[(i + 1) % len(circ)] - circ[i]) % 360.0 for i in range(len(circ))]
    start = (int(np.argmax(gaps)) + 1) % len(ordered)
    arc = ordered[start:] + ordered[:start]
    unwrapped = _unwrap_from(arc, az)
    cov = unwrapped[-1] - unwrapped[0]

    # Evenly spaced target azimuths across the arc; nearest unused candidate each.
    targets = np.linspace(unwrapped[0], unwrapped[-1], n)
    chosen_idx: list[int] = []
    for t in targets:
        order = np.argsort([abs(u - t) for u in unwrapped])
        for j in order:
            if j not in chosen_idx:
                chosen_idx.append(int(j))
                break
    selected = [arc[j] for j in sorted(chosen_idx, key=lambda j: _chrono_key(arc[j]))]

    sel_az = [az[f.frame_id] for f in selected]
    poses = [f.T_world_from_camera for f in selected]
    seps = _adjacent_separations(selected, az)
    target = object_target(raw)
    return {
        "ok": len(selected) == n and cov >= MIN_VIEW_COVERAGE_DEG,
        "reason": "" if cov >= MIN_VIEW_COVERAGE_DEG else f"best arc {cov:.0f} deg < {MIN_VIEW_COVERAGE_DEG:.0f}",
        "selected_frame_ids": [f.frame_id for f in selected],
        "coverage_deg": float(cov),
        "azimuths_deg": [float(a) for a in sel_az],
        "adjacent_separations_deg": seps,
        "total_baseline_mm": float(
            sum(cam.baseline(poses[i], poses[i + 1]) for i in range(len(poses) - 1)) * 1000.0
        ),
        "camera_target_distances_m": [
            float(np.linalg.norm(cam.camera_center(f.T_world_from_camera) - target)) for f in selected
        ],
    }


def _unwrap_from(arc: list[RawFrame], az: dict[str, float]) -> list[float]:
    """Unwrap the arc's azimuths into a monotone increasing sequence (each step is
    the real forward angular gap), starting from the first frame's raw azimuth."""
    vals = [az[arc[0].frame_id]]
    for i in range(1, len(arc)):
        step = (az[arc[i].frame_id] % 360.0 - az[arc[i - 1].frame_id] % 360.0) % 360.0
        vals.append(vals[-1] + step)
    return vals


def _adjacent_separations(selected: list[RawFrame], az: dict[str, float]) -> list[float]:
    s = sorted(az[f.frame_id] % 360.0 for f in selected)
    return [float(s[i + 1] - s[i]) for i in range(len(s) - 1)]


def _chrono_key(f: RawFrame) -> int:
    return int(f.frame_timestamp_ns)


# ---------------------------------------------------------------------------
# Fit run (GT-free): 7-DOF free fit, 6-DOF support-plane fit, quantisation.
# ---------------------------------------------------------------------------

def run_capture(manifest_path: str, config: ReconstructionConfig | None = None) -> dict[str, Any]:
    """Run the M9 cuboid fit on a prepared strict ``capture.json``.

    Produces **both** results independently and never chooses between them from
    accuracy (ground truth is not available here):

    * ``free_7dof`` — the 7-DOF free cuboid fit (always run);
    * ``support_6dof`` — the 6-DOF support-plane fit (only when the bundle carries a
      valid support plane, else ``None``);
    * ``quantization`` — the image-space quantisation uncertainty of the 7-DOF fit.
    """
    bundle = load_bundle(manifest_path)
    free = fit_cuboid(bundle, config=config, on_plane=False)
    support = fit_cuboid(bundle, config=config, on_plane=True) if bundle.support_plane is not None else None
    quant = image_quantization_uncertainty(bundle, config=config, on_plane=False)
    return {
        "manifest": manifest_path,
        "support_plane_present": bundle.support_plane is not None,
        "free_7dof": free,
        "support_6dof": support,
        "quantization": quant,
    }


# ---------------------------------------------------------------------------
# Evaluation (ground truth read ONLY here).
# ---------------------------------------------------------------------------

_DIMS = ("length_mm", "width_mm", "height_mm")


def _score_one(result: dict[str, Any] | None, gt: dict[str, int]) -> dict[str, Any]:
    """Score a single fit result against GT. Ground truth is used nowhere except
    here, in the evaluator."""
    if result is None:
        return {"present": False}
    if not result.get("success"):
        return {"present": True, "accepted": False, "reason": result.get("reason"),
                "debug_dimensions_mm": result.get("debug_dimensions_mm")}
    pred = result["dimensions"]
    abs_err = {k: abs(pred[k] - gt[k]) for k in _DIMS}
    pct_err = {k: 100.0 * abs_err[k] / gt[k] for k in _DIMS}
    vol_pred = float(np.prod([pred[k] for k in _DIMS]))
    vol_gt = float(np.prod([gt[k] for k in _DIMS]))
    return {
        "present": True,
        "accepted": True,
        "pred_mm": pred,
        "abs_err_mm": abs_err,
        "pct_err": pct_err,
        "max_pct_err": max(pct_err.values()),
        "volume_pct_err": 100.0 * abs(vol_pred - vol_gt) / vol_gt,
    }


def evaluate_runs(run_results: list[dict[str, Any]], gt: dict[str, int]) -> dict[str, Any]:
    """Compare GT-free run outputs for N independent sweeps to tape-measured ground
    truth. Reports per-sweep errors, cross-sweep repeatability per dimension, a
    6-DOF vs 7-DOF comparison, and the predeclared first-research-gate verdict.

    ``gt`` is the only ground-truth input in the whole pipeline and reaches no
    fitting code — it is consumed here to score already-computed predictions."""
    per_sweep = []
    for i, r in enumerate(run_results):
        per_sweep.append({
            "sweep": i + 1,
            "manifest": r.get("manifest"),
            "free_7dof": _score_one(r.get("free_7dof"), gt),
            "support_6dof": _score_one(r.get("support_6dof"), gt),
        })

    free_stats = _repeatability([s["free_7dof"] for s in per_sweep])
    support_stats = _repeatability([s["support_6dof"] for s in per_sweep])
    gate = _research_gate(free_stats, support_stats)
    return {
        "gt_mm": {k: gt[k] for k in _DIMS},
        "sweeps": per_sweep,
        "repeatability": {"free_7dof": free_stats, "support_6dof": support_stats},
        "dof_comparison": _dof_comparison(free_stats, support_stats),
        "research_gate": gate,
    }


def _repeatability(scores: list[dict[str, Any]]) -> dict[str, Any]:
    """Cross-sweep statistics over the *accepted* sweeps for one DOF configuration:
    per-dimension median / max error, prediction range, std and repeatability
    (range / mean)."""
    ok = [s for s in scores if s.get("accepted")]
    out: dict[str, Any] = {
        "sweeps_total": len(scores),
        "sweeps_accepted": len(ok),
        "accepted_any": bool(ok),
    }
    if not ok:
        return out
    per_dim: dict[str, Any] = {}
    for k in _DIMS:
        preds = np.array([s["pred_mm"][k] for s in ok], dtype=float)
        errs = np.array([s["pct_err"][k] for s in ok], dtype=float)
        rng = float(preds.max() - preds.min())
        per_dim[k] = {
            "median_pct_err": float(np.median(errs)),
            "max_pct_err": float(errs.max()),
            "pred_range_mm": rng,
            "pred_std_mm": float(np.std(preds)),
            "repeatability_pct": 100.0 * rng / float(preds.mean()),
        }
    out["per_dim"] = per_dim
    out["max_pct_err_any_dim"] = max(s["max_pct_err"] for s in ok)
    return out


def _dof_comparison(free: dict[str, Any], support: dict[str, Any]) -> dict[str, Any]:
    """Report both configurations side by side. Does **not** pick a production path —
    that decision is made by a human reading these numbers, not from GT here."""
    def summarise(stats: dict[str, Any]) -> dict[str, Any]:
        if not stats.get("accepted_any"):
            return {"accepted_any": False}
        return {
            "accepted_any": True,
            "sweeps_accepted": stats["sweeps_accepted"],
            "median_pct_err_per_dim": {k: stats["per_dim"][k]["median_pct_err"] for k in _DIMS},
            "max_pct_err_any_dim": stats["max_pct_err_any_dim"],
        }
    return {"free_7dof": summarise(free), "support_6dof": summarise(support),
            "note": "Both reported independently; production DOF choice is a human decision, not GT-selected."}


def _research_gate(free: dict[str, Any], support: dict[str, Any]) -> dict[str, Any]:
    """The predeclared first physical research gate (NOT the warehouse SLA).

    For the same carton across the sweeps, the best available configuration must
    show: median absolute error per dimension <= 5%, no accepted sweep over 10% on
    any dimension, and cross-sweep repeatability range <= 5% per dimension. The gate
    passes if **either** DOF configuration meets all three."""
    def passes(stats: dict[str, Any]) -> tuple[bool, dict[str, bool]]:
        if not stats.get("accepted_any"):
            return False, {"has_accepted_sweep": False}
        per = stats["per_dim"]
        median_ok = all(per[k]["median_pct_err"] <= 5.0 for k in _DIMS)
        no_over_10 = stats["max_pct_err_any_dim"] <= 10.0
        repeat_ok = all(per[k]["repeatability_pct"] <= 5.0 for k in _DIMS)
        return (median_ok and no_over_10 and repeat_ok), {
            "has_accepted_sweep": True,
            "median_err_<=5pct": median_ok,
            "no_accepted_sweep_>10pct": no_over_10,
            "repeatability_range_<=5pct": repeat_ok,
        }

    free_pass, free_detail = passes(free)
    support_pass, support_detail = passes(support)
    return {
        "passed": bool(free_pass or support_pass),
        "free_7dof": {"passed": free_pass, **free_detail},
        "support_6dof": {"passed": support_pass, **support_detail},
        "criteria": "median<=5% per dim AND no accepted sweep>10% AND repeatability range<=5% per dim",
        "note": "Research gate, not the final warehouse SLA. A failure must be reported, not tuned away.",
    }
