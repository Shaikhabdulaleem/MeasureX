"""M9 parametric cuboid-fit proof — the main M9 decision test.

Fits a gravity-aligned metric cuboid (``cuboid_fit.fit_cuboid``) to the SAME
practical short-sweep capture families the visual hull failed on, and reports, as
SEPARATE experiments (ground truth is compared only AFTER the fact — never a bound,
prior, initialisation or threshold in the fit):

  H/I. EXACT-POSE grid                 — full spec grid (5 sizes × 4 yaws × 4 frame
       counts × 5 spans = 400 sequences) with the COMPLETE metric gate (including
       leave-one-out). Per-dimension P50/P90/P95/max, acceptance by gate stage, and
       research false-accept counts (accepted yet >5/10/20% wrong vs GT).
  V.   ROBUST VIABLE sweeps            — group every (frames, span) across sizes and
       yaws; a configuration is viable only if the whole group meets the criterion.
  G.   6-DOF vs 7-DOF                   — support-plane vs free fit, reported apart.
  R.   RESOLUTION 200/480/960          — mask bbox px, error, IoU, runtime + ±1px
       image-quantisation uncertainty (mm), GT-free.
  S.   SUPPORT-PLANE sensitivity        — plane offset/tilt error degradation.
  B.   POSE-SCALE bias                  — correlated ±% translation scale bias.
  T.   TRAJECTORY variation             — non-ideal but exactly-known trajectories.
  M.   MASK-ERROR robustness            — stay in gate OR reject typed.
  N.   POSE-NOISE degradation           — rotation + translation noise.

No GPU, no model, no network. No correction factor or per-carton tuning.

**This is a synthetic exact-mask / exact-pose proof.** The masks come from the same
ideal cuboid camera model the fitter optimises, so this is a mathematical /
implementation proof, NOT evidence of real-world segmentation accuracy or that the
warehouse workflow is ready. See docs/M9_MULTIVIEW_METRIC_SPIKE.md.

    python scripts/m9_cuboid_proof.py            # quick developer grid (fast)
    python scripts/m9_cuboid_proof.py --full     # the full 400-sequence spec grid
    python scripts/m9_cuboid_proof.py --full --out DIR   # also write md/json
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from measurex_vision.multiview import ReconstructionConfig, reconstruct
from measurex_vision.multiview.cuboid_fit import (
    CuboidFitConfig,
    fit_cuboid,
    image_quantization_uncertainty,
)
from measurex_vision.multiview.schema import CaptureBundle
from measurex_vision.multiview.synthetic import synthetic_capture

REAL_CARTON = ("real carton", 0.345, 0.290, 0.245)
BOXES = [
    ("small parcel", 0.200, 0.150, 0.120),
    REAL_CARTON,
    ("medium carton", 0.600, 0.400, 0.350),
    ("large carton", 0.800, 0.600, 0.500),
    ("tall narrow", 0.250, 0.240, 0.800),
]
FRAMES = (6, 8, 10, 12)
SPANS = (30.0, 45.0, 60.0, 90.0, 120.0)
YAWS = (0.0, 20.0, 45.0, 70.0)
IMG_W = 200  # default grid image; FOV matched via fx. Resolution study sweeps this.
DIMS = ("length_mm", "width_mm", "height_mm")

# The final acceptance grid runs the COMPLETE gate, including a BOUNDED leave-one-out
# (the quick dev grid can skip LOO for speed). GT is never read by the fit.
#
# yaw_starts_deg=(0,45) was verified to give IDENTICAL accuracy to the library
# default (0,30,60) across the hard cases (small parcel / tall-narrow / 70° yaw /
# large carton) — it is a runtime choice for the 400-sequence sweep, not an accuracy
# compromise. leave_one_out_max_runs=3 is the "bounded number of LOO runs".
FINAL_CFG = CuboidFitConfig(leave_one_out=True, leave_one_out_max_runs=3, yaw_starts_deg=(0.0, 45.0))
DEV_CFG = CuboidFitConfig(leave_one_out=False, yaw_starts_deg=(0.0, 45.0))


def _capture(L: float, W: float, H: float, *, frames: int, span: float, yaw: float,
             img_w: int = IMG_W, **kw) -> tuple[CaptureBundle, dict]:
    """One continuous hand-held pass (single ring, 15→40° elevation ramp). FOV is
    held constant across image widths by scaling fx with the width."""
    return synthetic_capture(
        length_m=L, width_m=W, height_m=H, n_views=frames,
        azimuth_span_deg=span, elevations_deg=(15.0, 40.0), continuous_sweep=True,
        image_wh=(img_w, int(img_w * 4 / 3)), fx=img_w * 1004.0 / 960.0,
        distance_m=max(1.3, 2.2 * max(L, W, H)), yaw_deg=yaw, **kw,
    )


def _signed_err_pct(pred: dict, gt: dict) -> dict:
    return {k: 100.0 * (pred[k] - gt[k]) / gt[k] for k in gt}


def _max_abs_err_pct(pred: dict, gt: dict) -> float:
    return max(abs(v) for v in _signed_err_pct(pred, gt).values())


# --------------------------------------------------------------------------- #
# H/I. Full exact-pose grid with the complete metric gate
# --------------------------------------------------------------------------- #

def _row(carton: str, gt: dict, frames: int, span: float, yaw: float, r: dict, dt: float) -> dict:
    row = {"carton": carton, "gt": gt, "frames": frames, "span": span, "yaw": yaw,
           "runtime_s": round(dt, 2)}
    d = r.get("diagnostics", {})
    # Acceptance by gate STAGE (GT-free diagnostics), for the stage breakdown.
    row["optimizer_converged"] = bool(d.get("optimizer_converged", False))
    sil_ok = bool(d and d.get("mean_iou") is not None
                  and d["mean_iou"] >= FINAL_CFG.min_mean_iou
                  and d["min_iou"] >= FINAL_CFG.min_min_iou)
    row["silhouette_ok"] = sil_ok
    ident = d.get("parameter_identifiability", {})
    row["identifiable"] = bool(ident.get("identifiable", False))
    loo = d.get("leave_one_out_spread", {})
    spread = loo.get("spread_frac_max")
    row["loo_ok"] = bool(spread is None or spread <= FINAL_CFG.max_dim_spread_frac)
    if r["success"]:
        row.update(accepted=True, pred=r["dimensions"], err_pct=_signed_err_pct(r["dimensions"], gt),
                   mean_iou=round(d["mean_iou"], 3), min_iou=round(d["min_iou"], 3),
                   view_coverage_deg=round(d["view_coverage_deg"], 1))
    else:
        row.update(accepted=False, reason=r["reason"], debug=r.get("debug_dimensions_mm"))
    return row


def exact_pose_grid(cfg: CuboidFitConfig, boxes, yaws, spans, frames_set) -> list[dict]:
    rows: list[dict] = []
    for name, L, W, H in boxes:
        for yaw in yaws:
            for frames in frames_set:
                for span in spans:
                    bundle, gt = _capture(L, W, H, frames=frames, span=span, yaw=yaw)
                    t = time.perf_counter()
                    r = fit_cuboid(bundle, cfg)
                    rows.append(_row(name, gt, frames, span, yaw, r, time.perf_counter() - t))
    return rows


def _pct(values: list[float], q: float) -> float | None:
    return round(float(np.percentile(values, q)), 2) if values else None


def _per_dim_stats(rows: list[dict]) -> dict:
    """Per-dimension P50/P90/P95/max of |error %| over ACCEPTED sequences, plus the
    pooled numbers. The research gate passes only if median |error| ≤ 2% for EVERY
    dimension independently (not just pooled)."""
    acc = [r for r in rows if r.get("accepted")]
    per_dim: dict[str, dict] = {}
    pooled: list[float] = []
    medians_ok = True
    for k in DIMS:
        vals = [abs(r["err_pct"][k]) for r in acc]
        pooled.extend(vals)
        p50 = _pct(vals, 50)
        per_dim[k] = {"p50": p50, "p90": _pct(vals, 90), "p95": _pct(vals, 95),
                      "max": round(max(vals), 2) if vals else None}
        if p50 is None or p50 > 2.0:
            medians_ok = False
    return {
        "per_dimension": per_dim,
        "pooled": {"p50": _pct(pooled, 50), "p90": _pct(pooled, 90),
                   "p95": _pct(pooled, 95), "max": round(max(pooled), 2) if pooled else None},
        "per_dimension_median_le_2pct_passed": bool(acc and medians_ok),
    }


def _false_accepts(rows: list[dict]) -> dict:
    """Research false accepts: sequences the gate ACCEPTED yet GT shows are badly
    wrong. GT is used only here, by the evaluator — never by the fitter."""
    acc = [r for r in rows if r.get("accepted")]
    worst = [max(abs(v) for v in r["err_pct"].values()) for r in acc]
    return {
        "accepted": len(acc),
        "gt_gt_5pct": int(sum(w > 5.0 for w in worst)),
        "gt_gt_10pct": int(sum(w > 10.0 for w in worst)),
        "gt_gt_20pct": int(sum(w > 20.0 for w in worst)),
        "worst_accepted_err_pct": round(max(worst), 2) if worst else None,
    }


def _stage_counts(rows: list[dict]) -> dict:
    return {
        "sequences": len(rows),
        "optimizer_converged": int(sum(r["optimizer_converged"] for r in rows)),
        "silhouette_accepted": int(sum(r["silhouette_ok"] for r in rows)),
        "identifiability_accepted": int(sum(r["identifiable"] for r in rows)),
        "loo_accepted": int(sum(r["loo_ok"] for r in rows)),
        "final_metric_accepted": int(sum(r.get("accepted", False) for r in rows)),
    }


def _aggregate(rows: list[dict]) -> dict:
    acc = [r for r in rows if r.get("accepted")]
    return {
        "sequences": len(rows),
        "accepted": len(acc),
        "acceptance_rate": round(len(acc) / len(rows), 3) if rows else 0.0,
        "stage_counts": _stage_counts(rows),
        "per_dim": _per_dim_stats(rows),
        "false_accepts": _false_accepts(rows),
    }


def _by_key(rows: list[dict], key) -> dict:
    out: dict = {}
    for r in rows:
        if not r.get("accepted"):
            continue
        out.setdefault(key(r), []).extend(abs(v) for v in r["err_pct"].values())
    return {str(k): round(float(np.median(v)), 2) for k, v in sorted(out.items())}


# --------------------------------------------------------------------------- #
# V. Robust viable capture configurations (grouped, not a single lucky row)
# --------------------------------------------------------------------------- #

def robust_viable(rows: list[dict]) -> dict:
    """Group every tested (frames, span) across ALL carton sizes and yaws. A
    configuration is "robustly viable" only if the WHOLE group meets the predeclared
    criterion: every sequence accepted, zero false accepts, and P95 ≤ 5% per
    dimension. One lucky row does NOT make a configuration viable.

    Returns a Pareto table and the smallest viable configuration (fewest frames,
    then narrowest span), or none if nothing qualifies."""
    groups: dict[tuple[int, float], list[dict]] = {}
    for r in rows:
        groups.setdefault((r["frames"], r["span"]), []).append(r)

    table = []
    viable = []
    for (frames, span), grp in sorted(groups.items()):
        acc = [r for r in grp if r.get("accepted")]
        rate = len(acc) / len(grp) if grp else 0.0
        per_dim_p95 = {}
        worst = 0.0
        false_acc = 0
        for k in DIMS:
            vals = [abs(r["err_pct"][k]) for r in acc]
            per_dim_p95[k] = _pct(vals, 95)
        for r in acc:
            w = max(abs(v) for v in r["err_pct"].values())
            worst = max(worst, w)
            if w > 5.0:
                false_acc += 1
        p95_ok = all(per_dim_p95[k] is not None and per_dim_p95[k] <= 5.0 for k in DIMS)
        is_viable = bool(rate == 1.0 and false_acc == 0 and p95_ok)
        row = {"frames": frames, "span": span, "n": len(grp), "acceptance_rate": round(rate, 3),
               "L_p95": per_dim_p95["length_mm"], "W_p95": per_dim_p95["width_mm"],
               "H_p95": per_dim_p95["height_mm"], "worst_err_pct": round(worst, 2),
               "false_accepts": false_acc, "robustly_viable": is_viable}
        table.append(row)
        if is_viable:
            viable.append((frames, span))
    viable.sort()
    return {"table": table,
            "smallest_viable": ({"frames": viable[0][0], "azimuth_span_deg": viable[0][1]}
                                if viable else None)}


# --------------------------------------------------------------------------- #
# G. 6-DOF support-plane vs 7-DOF free fit (reported apart)
# --------------------------------------------------------------------------- #

def dof_comparison(cfg: CuboidFitConfig) -> list[dict]:
    rows = []
    for frames, span in [(8, 60.0), (10, 90.0), (12, 120.0)]:
        bundle, gt = _capture(*REAL_CARTON[1:], frames=frames, span=span, yaw=20.0)
        for label, on_plane in (("6dof_plane", True), ("7dof_free", False)):
            t = time.perf_counter()
            r = fit_cuboid(bundle, cfg, on_plane=on_plane)
            dt = time.perf_counter() - t
            row = {"config": label, "frames": frames, "span": span, "runtime_s": round(dt, 2)}
            d = r.get("diagnostics", {})
            if r["success"]:
                row.update(accepted=True, err_pct={k: round(v, 1) for k, v in _signed_err_pct(r["dimensions"], gt).items()},
                           mean_iou=round(d["mean_iou"], 3),
                           min_identifiability=round(d["parameter_identifiability"]["min_sensitivity"], 3),
                           loo_spread=d["leave_one_out_spread"].get("spread_frac_max"))
            else:
                row.update(accepted=False, reason=r["reason"])
            rows.append(row)
    return rows


# --------------------------------------------------------------------------- #
# R. Image resolution 200/480/960 + ±1px quantisation uncertainty
# --------------------------------------------------------------------------- #

def resolution_study(cfg: CuboidFitConfig) -> list[dict]:
    cases = [
        ("small parcel", (0.200, 0.150, 0.120), 10, 90.0),
        ("real carton", REAL_CARTON[1:], 10, 90.0),
        ("tall narrow", (0.250, 0.240, 0.800), 10, 90.0),
        ("real carton short sweep", REAL_CARTON[1:], 6, 45.0),
    ]
    rows = []
    for name, dims, frames, span in cases:
        for img_w in (200, 480, 960):
            bundle, gt = _capture(*dims, frames=frames, span=span, yaw=20.0, img_w=img_w)
            bbox = min(
                min(int(np.ptp(np.nonzero(f.mask)[0])) + 1, int(np.ptp(np.nonzero(f.mask)[1])) + 1)
                for f in bundle.frames
            )
            t = time.perf_counter()
            r = fit_cuboid(bundle, cfg)
            dt = time.perf_counter() - t
            unc = image_quantization_uncertainty(bundle, cfg)
            row = {"case": name, "img_w": img_w, "frames": frames, "span": span,
                   "mask_bbox_px": int(bbox), "runtime_s": round(dt, 2),
                   "unc_mm": {k: (round(unc[k], 1) if unc.get(k) is not None else None)
                              for k in DIMS}}
            d = r.get("diagnostics", {})
            if r["success"]:
                row.update(accepted=True, pred=r["dimensions"],
                           err_pct={k: round(v, 1) for k, v in _signed_err_pct(r["dimensions"], gt).items()},
                           mean_iou=round(d["mean_iou"], 3), min_iou=round(d["min_iou"], 3))
            else:
                row.update(accepted=False, reason=r["reason"], debug=r.get("debug_dimensions_mm"))
            rows.append(row)
    return rows


# --------------------------------------------------------------------------- #
# S. Support-plane error sensitivity (poses stay exact)
# --------------------------------------------------------------------------- #

def _perturb_plane(bundle: CaptureBundle, offset_mm: float, tilt_deg: float, seed: int) -> CaptureBundle:
    rng = np.random.default_rng(seed)
    n = np.asarray(bundle.support_plane["normal"], dtype=float)
    d = float(bundle.support_plane["offset"])
    if tilt_deg > 0:
        axis = rng.standard_normal(3)
        axis -= (axis @ n) * n  # tilt axis perpendicular to the normal
        axis /= max(np.linalg.norm(axis), 1e-9)
        ang = np.radians(tilt_deg)
        k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
        n = (np.eye(3) + np.sin(ang) * k + (1 - np.cos(ang)) * (k @ k)) @ n
    d = d + offset_mm / 1000.0  # shift the plane along its normal
    plane = {"normal": [float(x) for x in n], "offset": d}
    return dataclasses.replace(bundle, support_plane=plane)


def support_plane_sensitivity(cfg: CuboidFitConfig) -> dict:
    out: dict = {"offset_mm": [], "tilt_deg": []}
    for mm in (1.0, 3.0, 5.0, 10.0):
        bundle, gt = _capture(*REAL_CARTON[1:], frames=10, span=90.0, yaw=20.0)
        r = fit_cuboid(_perturb_plane(bundle, mm, 0.0, seed=int(mm)), cfg)
        out["offset_mm"].append({"offset_mm": mm, **_degradation_row(r, gt)})
    for deg in (0.1, 0.25, 0.5, 1.0, 2.0):
        bundle, gt = _capture(*REAL_CARTON[1:], frames=10, span=90.0, yaw=20.0)
        r = fit_cuboid(_perturb_plane(bundle, 0.0, deg, seed=int(deg * 100)), cfg)
        out["tilt_deg"].append({"tilt_deg": deg, **_degradation_row(r, gt)})
    return out


def _degradation_row(r: dict, gt: dict) -> dict:
    if r["success"]:
        e = _signed_err_pct(r["dimensions"], gt)
        return {"accepted": True, "err_pct": {k: round(v, 1) for k, v in e.items()},
                "max_abs_pct": round(max(abs(v) for v in e.values()), 1)}
    return {"accepted": False, "reason": r["reason"]}


# --------------------------------------------------------------------------- #
# B. Metric-pose scale bias (correlated — NOT compensated)
# --------------------------------------------------------------------------- #

def _scale_poses(bundle: CaptureBundle, bias: float) -> CaptureBundle:
    """Scale every camera translation about the common world origin by (1+bias).
    Masks are untouched (they came from the true trajectory). This models a
    visual-inertial metric-scale error/drift; it is NEVER compensated."""
    frames = []
    for f in bundle.frames:
        T = f.T_world_from_camera.copy()
        T[:3, 3] = T[:3, 3] * (1.0 + bias)
        frames.append(dataclasses.replace(f, T_world_from_camera=T))
    # the support plane offset is a metric datum tied to the same origin — scale it too
    plane = None
    if bundle.support_plane is not None:
        plane = {**bundle.support_plane, "offset": bundle.support_plane["offset"] * (1.0 + bias)}
    return dataclasses.replace(bundle, frames=frames, support_plane=plane)


def pose_scale_bias(cfg: CuboidFitConfig) -> list[dict]:
    rows = []
    for bias in (-0.02, -0.01, -0.005, 0.005, 0.01, 0.02):
        bundle, gt = _capture(*REAL_CARTON[1:], frames=10, span=90.0, yaw=20.0)
        r = fit_cuboid(_scale_poses(bundle, bias), cfg)
        rows.append({"bias_pct": round(bias * 100, 1), **_degradation_row(r, gt)})
    return rows


# --------------------------------------------------------------------------- #
# T. Realistic (non-ideal) but exactly-known trajectories
# --------------------------------------------------------------------------- #

def trajectory_variation(cfg: CuboidFitConfig) -> list[dict]:
    variants = {
        "ideal arc": {},
        "non-uniform spacing": {"azimuth_jitter_deg": 6.0},
        "radial distance jitter": {"distance_jitter_frac": 0.08},
        "elevation jitter": {"elevation_jitter_deg": 5.0},
        "lateral path jitter": {"lateral_jitter_m": 0.03},
        "aim off-centre": {"aim_jitter_m": 0.03},
        "all combined": {"azimuth_jitter_deg": 6.0, "distance_jitter_frac": 0.08,
                         "elevation_jitter_deg": 5.0, "lateral_jitter_m": 0.03, "aim_jitter_m": 0.03},
    }
    rows = []
    for label, kw in variants.items():
        bundle, gt = _capture(*REAL_CARTON[1:], frames=10, span=90.0, yaw=20.0, seed=7, **kw)
        r = fit_cuboid(bundle, cfg)
        rows.append({"trajectory": label, **_degradation_row(r, gt)})
    return rows


# --------------------------------------------------------------------------- #
# M. Mask-error robustness ; N. pose-noise degradation
# --------------------------------------------------------------------------- #

def _perturb_mask(mask: np.ndarray, kind: str, seed: int) -> np.ndarray:
    ys, xs = np.nonzero(mask)
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    out = mask.copy()
    pad = max(3, (y1 - y0) // 12)
    if kind == "oversized":
        out[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad] = True
    elif kind == "undersized":
        out[:] = False
        out[y0 + pad:max(y0 + pad + 1, y1 - pad), x0 + pad:max(x0 + pad + 1, x1 - pad)] = \
            mask[y0 + pad:max(y0 + pad + 1, y1 - pad), x0 + pad:max(x0 + pad + 1, x1 - pad)]
    elif kind == "shifted":
        out = np.roll(mask, (pad, pad), axis=(0, 1))
    elif kind == "noisy":
        rng = np.random.default_rng(seed)
        out = np.logical_xor(mask, rng.random(mask.shape) < 0.02)
    return out


def mask_noise(cfg: CuboidFitConfig) -> list[dict]:
    rows = []
    for kind in ("clean", "oversized", "undersized", "shifted", "missing", "noisy"):
        bundle, gt = _capture(*REAL_CARTON[1:], frames=10, span=90.0, yaw=20.0)
        frames = list(bundle.frames)
        if kind == "missing":
            frames = frames[:1] + frames[2:]
        elif kind != "clean":
            f = frames[3]
            frames[3] = dataclasses.replace(f, mask=_perturb_mask(f.mask, kind, seed=3))
        r = fit_cuboid(dataclasses.replace(bundle, frames=frames), cfg)
        row = {"kind": kind}
        if r["success"]:
            row.update(accepted=True, max_err_pct=round(_max_abs_err_pct(r["dimensions"], gt), 1),
                       mean_iou=round(r["diagnostics"]["mean_iou"], 3))
        else:
            row.update(accepted=False, reason=r["reason"])
        rows.append(row)
    return rows


def _perturb_poses(bundle: CaptureBundle, rot_deg: float, trans_m: float, seed: int) -> CaptureBundle:
    rng = np.random.default_rng(seed)
    frames = []
    for f in bundle.frames:
        T = f.T_world_from_camera.copy()
        if rot_deg > 0:
            axis = rng.standard_normal(3)
            axis /= np.linalg.norm(axis)
            ang = np.radians(rot_deg) * rng.standard_normal()
            k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
            T[:3, :3] = (np.eye(3) + np.sin(ang) * k + (1 - np.cos(ang)) * (k @ k)) @ T[:3, :3]
        if trans_m > 0:
            T[:3, 3] += trans_m * rng.standard_normal(3)
        frames.append(dataclasses.replace(f, T_world_from_camera=T))
    return dataclasses.replace(bundle, frames=frames)


def pose_noise(cfg: CuboidFitConfig) -> dict:
    out: dict = {"rotation_deg": [], "translation_mm": []}
    for rot in (0.1, 0.25, 0.5, 1.0):
        bundle, gt = _capture(*REAL_CARTON[1:], frames=10, span=90.0, yaw=20.0)
        r = fit_cuboid(_perturb_poses(bundle, rot, 0.0, seed=int(rot * 100)), cfg)
        out["rotation_deg"].append({"rot_deg": rot, **_noise_row(r, gt)})
    for mm in (1.0, 3.0, 5.0, 10.0):
        bundle, gt = _capture(*REAL_CARTON[1:], frames=10, span=90.0, yaw=20.0)
        r = fit_cuboid(_perturb_poses(bundle, 0.0, mm / 1000.0, seed=int(mm)), cfg)
        out["translation_mm"].append({"trans_mm": mm, **_noise_row(r, gt)})
    return out


def _noise_row(r: dict, gt: dict) -> dict:
    if r["success"]:
        return {"accepted": True, "max_err_pct": round(_max_abs_err_pct(r["dimensions"], gt), 1),
                "mean_iou": round(r["diagnostics"]["mean_iou"], 3)}
    return {"accepted": False, "reason": r["reason"]}


# --------------------------------------------------------------------------- #
# O. Visual hull vs cuboid fit on the same short sweeps
# --------------------------------------------------------------------------- #

def compare_methods(cfg: CuboidFitConfig) -> list[dict]:
    hull_cfg = ReconstructionConfig(min_total_baseline_m=0.05, min_view_coverage_deg=15,
                                    fine_divisions=60, coarse_divisions=28, leave_one_out=False)
    rows = []
    for frames, span in [(8, 45.0), (10, 60.0), (10, 90.0), (12, 120.0)]:
        bundle, gt = _capture(*REAL_CARTON[1:], frames=frames, span=span, yaw=20.0)
        for method, fn in (("visual_hull", lambda b: reconstruct(b, hull_cfg)),
                           ("cuboid_fit", lambda b: fit_cuboid(b, cfg))):
            t = time.perf_counter()
            r = fn(bundle)
            dt = time.perf_counter() - t
            row = {"method": method, "frames": frames, "span": span, "runtime_s": round(dt, 2)}
            if r["success"]:
                row.update(accepted=True, err_pct={k: round(v, 1) for k, v in _signed_err_pct(r["dimensions"], gt).items()})
            else:
                row.update(accepted=False, reason=r["reason"], debug=r.get("debug_dimensions_mm"))
            rows.append(row)
    return rows


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #

def _dims(d: dict) -> str:
    return f"{d['length_mm']}/{d['width_mm']}/{d['height_mm']}"


def render(res: dict, full: bool) -> str:
    agg = res["aggregate"]
    pd = agg["per_dim"]["per_dimension"]
    pooled = agg["per_dim"]["pooled"]
    sc = agg["stage_counts"]
    fa = agg["false_accepts"]
    L = [f"# M9 parametric cuboid-fit proof ({'FULL 400-sequence grid' if full else 'quick dev grid'})\n"]
    L.append("> Synthetic exact-mask / exact-pose proof — a mathematical/implementation "
             "proof, NOT evidence of real-world segmentation accuracy or warehouse readiness.\n")

    L.append("## H/I. Exact-pose grid — complete metric gate (incl. leave-one-out)\n")
    L.append(f"**Aggregate:** accepted {agg['accepted']}/{agg['sequences']} "
             f"({agg['acceptance_rate']:.0%}).\n")
    L.append("**Acceptance by gate stage:** "
             f"optimizer-converged {sc['optimizer_converged']} · silhouette {sc['silhouette_accepted']} · "
             f"identifiability {sc['identifiability_accepted']} · LOO {sc['loo_accepted']} · "
             f"**final metric {sc['final_metric_accepted']}** / {sc['sequences']}\n")
    L.append("**Per-dimension |error %| over accepted:**\n")
    L.append("| dim | P50 | P90 | P95 | max |")
    L.append("|---|---|---|---|---|")
    for k in DIMS:
        s = pd[k]
        L.append(f"| {k[:-3]} | {s['p50']} | {s['p90']} | {s['p95']} | {s['max']} |")
    L.append(f"| pooled | {pooled['p50']} | {pooled['p90']} | {pooled['p95']} | {pooled['max']} |")
    L.append(f"\n**Per-dimension median ≤ 2% target: "
             f"{'PASSED' if agg['per_dim']['per_dimension_median_le_2pct_passed'] else 'NOT passed'}** "
             "(requires median|L|, median|W|, median|H| each ≤ 2%).\n")
    L.append(f"**Research false accepts** (accepted yet GT-wrong): >5% = {fa['gt_gt_5pct']}, "
             f">10% = {fa['gt_gt_10pct']}, >20% = {fa['gt_gt_20pct']}; "
             f"worst accepted error {fa['worst_accepted_err_pct']}% (of {fa['accepted']} accepted).\n")
    L.append(f"median |err %| by size: {res['by_size']}\n")
    L.append(f"median |err %| by yaw:  {res['by_yaw']}\n")

    L.append("\n## V. Robustly viable capture configurations (grouped across sizes & yaws)\n")
    rv = res["robust_viable"]
    L.append("Criterion per (frames, span) group: 100% accepted AND 0 false accepts AND P95 ≤ 5% per dim.\n")
    L.append(f"**Smallest robustly viable sweep:** {rv['smallest_viable'] or 'NONE qualified'}\n")
    L.append("| frames | span | n | accept | L P95 | W P95 | H P95 | worst% | false | viable |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in rv["table"]:
        L.append(f"| {r['frames']} | {r['span']:.0f} | {r['n']} | {r['acceptance_rate']:.0%} | "
                 f"{r['L_p95']} | {r['W_p95']} | {r['H_p95']} | {r['worst_err_pct']} | "
                 f"{r['false_accepts']} | {'yes' if r['robustly_viable'] else 'no'} |")

    L.append("\n## G. 6-DOF support-plane vs 7-DOF free fit\n")
    L.append("| frames | span | config | accepted | err% L/W/H | meanIoU | ident | LOO | s |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for r in res["dof_comparison"]:
        if r["accepted"]:
            e = r["err_pct"]
            L.append(f"| {r['frames']} | {r['span']:.0f} | {r['config']} | yes | "
                     f"{e['length_mm']:+.1f}/{e['width_mm']:+.1f}/{e['height_mm']:+.1f} | "
                     f"{r['mean_iou']} | {r['min_identifiability']} | {r['loo_spread']} | {r['runtime_s']} |")
        else:
            L.append(f"| {r['frames']} | {r['span']:.0f} | {r['config']} | **no** | {r['reason']} | | | | {r['runtime_s']} |")

    L.append("\n## R. Image resolution 200/480/960 + ±1px quantisation uncertainty\n")
    L.append("| case | img w | bbox px | accepted | err% L/W/H | meanIoU | minIoU | unc mm L/W/H | s |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for r in res["resolution"]:
        u = r["unc_mm"]
        us = f"{u['length_mm']}/{u['width_mm']}/{u['height_mm']}"
        if r["accepted"]:
            e = r["err_pct"]
            L.append(f"| {r['case']} | {r['img_w']} | {r['mask_bbox_px']} | yes | "
                     f"{e['length_mm']:+.1f}/{e['width_mm']:+.1f}/{e['height_mm']:+.1f} | "
                     f"{r['mean_iou']} | {r['min_iou']} | {us} | {r['runtime_s']} |")
        else:
            dbg = f" (debug {_dims(r['debug'])})" if r.get("debug") else ""
            L.append(f"| {r['case']} | {r['img_w']} | {r['mask_bbox_px']} | **no** | {r['reason']}{dbg} | | | {us} | {r['runtime_s']} |")

    L.append("\n## S. Support-plane error sensitivity (poses exact)\n")
    L.append("| plane offset mm | accepted | err% L/W/H | max% |")
    L.append("|---|---|---|---|")
    for r in res["support_plane_sensitivity"]["offset_mm"]:
        L.append(_sens_line(r, "offset_mm"))
    L.append("\n| plane tilt deg | accepted | err% L/W/H | max% |")
    L.append("|---|---|---|---|")
    for r in res["support_plane_sensitivity"]["tilt_deg"]:
        L.append(_sens_line(r, "tilt_deg"))

    L.append("\n## B. Metric-pose scale bias (NOT compensated)\n")
    L.append("| pose scale bias % | accepted | err% L/W/H | max% |")
    L.append("|---|---|---|---|")
    for r in res["pose_scale_bias"]:
        L.append(_sens_line(r, "bias_pct"))

    L.append("\n## T. Realistic trajectory variation (exactly-known poses)\n")
    L.append("| trajectory | accepted | err% L/W/H | max% |")
    L.append("|---|---|---|---|")
    for r in res["trajectory"]:
        L.append(_sens_line(r, "trajectory"))

    L.append("\n## M. Mask-error robustness (stay in gate OR typed failure)\n")
    L.append("| mask | accepted | max err% | reason/iou |")
    L.append("|---|---|---|---|")
    for r in res["mask_noise"]:
        rhs = f"iou {r['mean_iou']}" if r["accepted"] else r["reason"]
        L.append(f"| {r['kind']} | {r['accepted']} | {r.get('max_err_pct', '—')} | {rhs} |")

    L.append("\n## N. Pose-noise degradation (reported separately)\n")
    L.append("| rotation deg | accepted | max err% | mean IoU / reason |")
    L.append("|---|---|---|---|")
    for r in res["pose_noise"]["rotation_deg"]:
        L.append(f"| {r['rot_deg']} | {r['accepted']} | {r.get('max_err_pct', '—')} | {r.get('mean_iou', r.get('reason'))} |")
    L.append("\n| translation mm | accepted | max err% | mean IoU / reason |")
    L.append("|---|---|---|---|")
    for r in res["pose_noise"]["translation_mm"]:
        L.append(f"| {r['trans_mm']} | {r['accepted']} | {r.get('max_err_pct', '—')} | {r.get('mean_iou', r.get('reason'))} |")

    L.append("\n## O. Visual hull vs cuboid fit (same short sweeps)\n")
    L.append("| frames | span | method | accepted | err% L/W/H | reason | s |")
    L.append("|---|---|---|---|---|---|---|")
    for r in res["comparison"]:
        if r["accepted"]:
            e = r["err_pct"]
            L.append(f"| {r['frames']} | {r['span']:.0f} | {r['method']} | yes | "
                     f"{e['length_mm']:+.1f}/{e['width_mm']:+.1f}/{e['height_mm']:+.1f} | | {r['runtime_s']} |")
        else:
            dbg = f"debug {_dims(r['debug'])}" if r.get("debug") else r["reason"]
            L.append(f"| {r['frames']} | {r['span']:.0f} | {r['method']} | **no** | | {dbg} | {r['runtime_s']} |")
    return "\n".join(L) + "\n"


def _sens_line(r: dict, key: str) -> str:
    if r["accepted"]:
        e = r["err_pct"]
        return (f"| {r[key]} | yes | {e['length_mm']:+.1f}/{e['width_mm']:+.1f}/{e['height_mm']:+.1f} "
                f"| {r['max_abs_pct']} |")
    return f"| {r[key]} | **no** | {r['reason']} | |"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--full", action="store_true",
                    help="full 400-sequence spec grid (5 sizes × 4 yaws × 4 frames × 5 spans; slow)")
    args = ap.parse_args()

    cfg = FINAL_CFG
    boxes = BOXES if args.full else [BOXES[0], REAL_CARTON, BOXES[2]]
    yaws = YAWS if args.full else (0.0, 45.0)
    spans = SPANS if args.full else (45.0, 60.0, 90.0, 120.0)
    frames_set = FRAMES

    t0 = time.perf_counter()
    grid = exact_pose_grid(cfg, boxes, yaws, spans, frames_set)
    res = {
        "grid": grid,
        "aggregate": _aggregate(grid),
        "by_size": _by_key(grid, lambda r: r["carton"]),
        "by_yaw": _by_key(grid, lambda r: f"{r['yaw']:.0f}"),
        "robust_viable": robust_viable(grid),
        "dof_comparison": dof_comparison(cfg),
        "resolution": resolution_study(cfg),
        "support_plane_sensitivity": support_plane_sensitivity(cfg),
        "pose_scale_bias": pose_scale_bias(cfg),
        "trajectory": trajectory_variation(cfg),
        "mask_noise": mask_noise(cfg),
        "pose_noise": pose_noise(cfg),
        "comparison": compare_methods(cfg),
        "total_runtime_s": None,
    }
    res["total_runtime_s"] = round(time.perf_counter() - t0, 1)

    md = render(res, args.full)
    # Persist BEFORE printing: a cp1252 console (Windows) cannot encode '≤'/'×', and a
    # failed print must not lose the computed results.
    if args.out:
        os.makedirs(args.out, exist_ok=True)
        with open(os.path.join(args.out, "cuboid_proof.md"), "w", encoding="utf-8") as fh:
            fh.write(md)
        with open(os.path.join(args.out, "cuboid_proof.json"), "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=2)
    sys.stdout.buffer.write(md.encode("utf-8", errors="replace"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
