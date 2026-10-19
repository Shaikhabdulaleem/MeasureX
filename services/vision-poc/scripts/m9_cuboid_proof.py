"""M9 parametric cuboid-fit proof — the main M9 decision test.

Fits a gravity-aligned metric cuboid (``cuboid_fit.fit_cuboid``) to the SAME
practical short-sweep capture families the visual hull failed on, and reports, as
SEPARATE experiments:

  H/I. EXACT-POSE short-sweep matrix   — sizes × frames × azimuth span × carton
       yaw. The decision question: what is the minimum practical sweep that
       reliably recovers a box? Target: median abs % error per dim ≤ 2%.
  M.   MASK-ERROR robustness           — oversized / undersized / shifted / missing
       / noisy masks: stay in the gate OR reject with a typed failure (never a
       silent bad dimension).
  N.   POSE-NOISE degradation          — rotation and translation noise, reported
       apart from the exact-pose statistics.
  O.   VISUAL-HULL vs CUBOID-FIT       — both methods on the same short sweeps.

No GPU, no model, no network. Ground truth is compared only after the fact — it is
never a bound, prior, initialisation or threshold in the fit. No correction factor
or per-carton tuning.

    python scripts/m9_cuboid_proof.py            # tables to stdout (quick grid)
    python scripts/m9_cuboid_proof.py --full     # the full spec grid (slow)
    python scripts/m9_cuboid_proof.py --out DIR  # also write md/json
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
from measurex_vision.multiview.cuboid_fit import CuboidFitConfig, fit_cuboid
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
IMG_W = 200  # small image keeps the offline grid tractable; FOV matched via fx


def _capture(L: float, W: float, H: float, *, frames: int, span: float, yaw: float) -> tuple[CaptureBundle, dict]:
    """One continuous hand-held pass (single ring, 15→40° elevation ramp)."""
    return synthetic_capture(
        length_m=L, width_m=W, height_m=H, n_views=frames,
        azimuth_span_deg=span, elevations_deg=(15.0, 40.0), continuous_sweep=True,
        image_wh=(IMG_W, int(IMG_W * 4 / 3)), fx=IMG_W * 1004.0 / 960.0,
        distance_m=max(1.3, 2.2 * max(L, W, H)), yaw_deg=yaw,
    )


def _err_pct(pred: dict, gt: dict) -> dict:
    return {k: 100.0 * (pred[k] - gt[k]) / gt[k] for k in gt}


def _row(carton: str, gt: dict, frames: int, span: float, yaw: float, r: dict, dt: float) -> dict:
    row = {"carton": carton, "gt": gt, "frames": frames, "span": span, "yaw": yaw, "runtime_s": round(dt, 2)}
    d = r.get("diagnostics", {})
    if r["success"]:
        row.update(accepted=True, pred=r["dimensions"], err_pct=_err_pct(r["dimensions"], gt),
                   mean_iou=round(d["mean_iou"], 3), min_iou=round(d["min_iou"], 3),
                   view_coverage_deg=round(d["view_coverage_deg"], 1))
    else:
        row.update(accepted=False, reason=r["reason"], debug=r.get("debug_dimensions_mm"))
    return row


def short_sweep_matrix(cfg: CuboidFitConfig, boxes, yaws, spans) -> list[dict]:
    rows: list[dict] = []
    for name, L, W, H in boxes:
        for yaw in yaws:
            for frames in FRAMES:
                for span in spans:
                    bundle, gt = _capture(L, W, H, frames=frames, span=span, yaw=yaw)
                    t = time.perf_counter()
                    r = fit_cuboid(bundle, cfg)
                    rows.append(_row(name, gt, frames, span, yaw, r, time.perf_counter() - t))
    return rows


def _aggregate(rows: list[dict]) -> dict:
    pcts = [abs(v) for r in rows if r.get("accepted") for v in r["err_pct"].values()]
    acc = [r for r in rows if r.get("accepted")]
    return {
        "sequences": len(rows), "accepted": len(acc),
        "acceptance_rate": round(len(acc) / len(rows), 3) if rows else 0.0,
        "p50_abs_pct": round(float(np.percentile(pcts, 50)), 2) if pcts else None,
        "p90_abs_pct": round(float(np.percentile(pcts, 90)), 2) if pcts else None,
        "p95_abs_pct": round(float(np.percentile(pcts, 95)), 2) if pcts else None,
        "max_abs_pct": round(float(np.max(pcts)), 2) if pcts else None,
        "target_le_2pct_passed": bool(pcts and np.percentile(pcts, 50) <= 2.0),
    }


def _by_key(rows: list[dict], key) -> dict:
    out: dict = {}
    for r in rows:
        if not r.get("accepted"):
            continue
        k = key(r)
        out.setdefault(k, []).extend(abs(v) for v in r["err_pct"].values())
    return {str(k): round(float(np.median(v)), 2) for k, v in sorted(out.items())}


def minimum_viable(rows: list[dict]) -> dict:
    """Smallest (frames, span) whose accepted fits all stay within 2% — the minimum
    practical sweep the cuboid fit needs (GT compared only after the fact)."""
    best = None
    for r in rows:
        if r.get("accepted") and max(abs(v) for v in r["err_pct"].values()) <= 2.0:
            cand = (r["frames"], r["span"])
            if best is None or cand < best:
                best = cand
    return {"frames": best[0], "azimuth_span_deg": best[1]} if best else {}


# --- Phase M: mask-error robustness ---------------------------------------- #

def _perturb_mask(mask: np.ndarray, kind: str, seed: int) -> np.ndarray:
    ys, xs = np.nonzero(mask)
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    out = mask.copy()
    pad = max(3, (y1 - y0) // 12)
    if kind == "oversized":
        out[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad] = True
    elif kind == "undersized":
        out[:] = False
        out[y0 + pad:max(y0 + pad + 1, y1 - pad), x0 + pad:max(x0 + pad + 1, x1 - pad)] = mask[y0 + pad:max(y0 + pad + 1, y1 - pad), x0 + pad:max(x0 + pad + 1, x1 - pad)]
    elif kind == "shifted":
        out = np.roll(mask, (pad, pad), axis=(0, 1))
    elif kind == "noisy":
        rng = np.random.default_rng(seed)
        flip = rng.random(mask.shape) < 0.02
        out = np.logical_xor(mask, flip)
    return out


def mask_noise(cfg: CuboidFitConfig) -> list[dict]:
    rows = []
    for kind in ("clean", "oversized", "undersized", "shifted", "missing", "noisy"):
        bundle, gt = _capture(*REAL_CARTON[1:], frames=10, span=90.0, yaw=20.0)
        frames = list(bundle.frames)
        if kind == "missing":
            frames = frames[:1] + frames[2:]  # drop one frame entirely
        elif kind != "clean":
            f = frames[3]
            frames[3] = dataclasses.replace(f, mask=_perturb_mask(f.mask, kind, seed=3))
        b = dataclasses.replace(bundle, frames=frames)
        r = fit_cuboid(b, cfg)
        row = {"kind": kind}
        if r["success"]:
            e = max(abs(v) for v in _err_pct(r["dimensions"], gt).values())
            row.update(accepted=True, max_err_pct=round(e, 1), mean_iou=round(r["diagnostics"]["mean_iou"], 3))
        else:
            row.update(accepted=False, reason=r["reason"])
        rows.append(row)
    return rows


# --- Phase N: pose noise (rotation + translation), reported separately ------ #

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
        return {"accepted": True, "max_err_pct": round(max(abs(v) for v in _err_pct(r["dimensions"], gt).values()), 1),
                "mean_iou": round(r["diagnostics"]["mean_iou"], 3)}
    return {"accepted": False, "reason": r["reason"]}


# --- Phase O: visual hull vs cuboid fit on the same short sweeps ------------- #

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
                e = _err_pct(r["dimensions"], gt)
                row.update(accepted=True, err_pct={k: round(v, 1) for k, v in e.items()})
            else:
                row.update(accepted=False, reason=r["reason"], debug=r.get("debug_dimensions_mm"))
            rows.append(row)
    return rows


def _dims(d: dict) -> str:
    return f"{d['length_mm']}/{d['width_mm']}/{d['height_mm']}"


def render(matrix, agg, mask, noise, cmp, min_viable, by_size, by_yaw) -> str:
    L = ["# M9 parametric cuboid-fit proof\n"]
    L.append("## H/I. Exact-pose short-sweep matrix (cuboid fit)\n")
    L.append(f"**Aggregate:** accepted {agg['accepted']}/{agg['sequences']} "
             f"({agg['acceptance_rate']:.0%}) · abs%% err P50 {agg['p50_abs_pct']} · "
             f"P90 {agg['p90_abs_pct']} · P95 {agg['p95_abs_pct']} · max {agg['max_abs_pct']} · "
             f"**≤2%% P50 target {'PASSED' if agg['target_le_2pct_passed'] else 'NOT passed'}**\n")
    L.append(f"median abs%% by carton size: {by_size}\n")
    L.append(f"median abs%% by carton yaw: {by_yaw}\n")
    L.append(f"minimum viable sweep (all dims ≤2%%): {min_viable}\n")
    L.append("| carton | frames | span | yaw | GT L/W/H | pred L/W/H | err% L/W/H | meanIoU | minIoU | s |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in matrix:
        if r["accepted"]:
            e = r["err_pct"]
            em = f"{e['length_mm']:+.1f}/{e['width_mm']:+.1f}/{e['height_mm']:+.1f}"
            L.append(f"| {r['carton']} | {r['frames']} | {r['span']:.0f} | {r['yaw']:.0f} | {_dims(r['gt'])} | {_dims(r['pred'])} | {em} | {r['mean_iou']} | {r['min_iou']} | {r['runtime_s']} |")
        else:
            dbg = f" (debug {_dims(r['debug'])})" if r.get("debug") else ""
            L.append(f"| {r['carton']} | {r['frames']} | {r['span']:.0f} | {r['yaw']:.0f} | {_dims(r['gt'])} | FAIL: {r['reason']}{dbg} | | | | {r['runtime_s']} |")

    L.append("\n## M. Mask-error robustness (stay in gate OR typed failure)\n")
    L.append("| mask | accepted | max err% | reason/iou |")
    L.append("|---|---|---|---|")
    for r in mask:
        rhs = f"iou {r['mean_iou']}" if r["accepted"] else r["reason"]
        L.append(f"| {r['kind']} | {r['accepted']} | {r.get('max_err_pct', '—')} | {rhs} |")

    L.append("\n## N. Pose-noise degradation (reported separately)\n")
    L.append("| rotation deg | accepted | max err% | mean IoU / reason |")
    L.append("|---|---|---|---|")
    for r in noise["rotation_deg"]:
        rhs = r.get("mean_iou", r.get("reason"))
        L.append(f"| {r['rot_deg']} | {r['accepted']} | {r.get('max_err_pct', '—')} | {rhs} |")
    L.append("\n| translation mm | accepted | max err% | mean IoU / reason |")
    L.append("|---|---|---|---|")
    for r in noise["translation_mm"]:
        rhs = r.get("mean_iou", r.get("reason"))
        L.append(f"| {r['trans_mm']} | {r['accepted']} | {r.get('max_err_pct', '—')} | {rhs} |")

    L.append("\n## O. Visual hull vs cuboid fit (same short sweeps)\n")
    L.append("| frames | span | method | accepted | err% L/W/H | reason | s |")
    L.append("|---|---|---|---|---|---|---|")
    for r in cmp:
        if r["accepted"]:
            e = r["err_pct"]
            L.append(f"| {r['frames']} | {r['span']:.0f} | {r['method']} | yes | {e['length_mm']:+.1f}/{e['width_mm']:+.1f}/{e['height_mm']:+.1f} | | {r['runtime_s']} |")
        else:
            dbg = f"debug {_dims(r['debug'])}" if r.get("debug") else r["reason"]
            L.append(f"| {r['frames']} | {r['span']:.0f} | {r['method']} | **no** | | {dbg} | {r['runtime_s']} |")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--full", action="store_true", help="full spec grid (5 sizes × 4 yaws × all frames × all spans; slow)")
    args = ap.parse_args()

    cfg = CuboidFitConfig(leave_one_out=False)  # matrix uses silhouette+identifiability gates
    boxes = BOXES if args.full else [BOXES[0], REAL_CARTON, BOXES[2]]
    yaws = YAWS if args.full else (0.0, 45.0)
    spans = SPANS if args.full else (45.0, 60.0, 90.0, 120.0)

    matrix = short_sweep_matrix(cfg, boxes, yaws, spans)
    agg = _aggregate(matrix)
    by_size = _by_key(matrix, lambda r: r["carton"])
    by_yaw = _by_key(matrix, lambda r: f"{r['yaw']:.0f}")
    mv = minimum_viable(matrix)
    mask = mask_noise(cfg)
    noise = pose_noise(cfg)
    cmp = compare_methods(cfg)

    md = render(matrix, agg, mask, noise, cmp, mv, by_size, by_yaw)
    # Persist BEFORE printing: a cp1252 console (Windows) cannot encode '≤'/'×', and
    # a failed print must not lose the computed results.
    if args.out:
        os.makedirs(args.out, exist_ok=True)
        with open(os.path.join(args.out, "cuboid_proof.md"), "w", encoding="utf-8") as fh:
            fh.write(md)
        with open(os.path.join(args.out, "cuboid_proof.json"), "w", encoding="utf-8") as fh:
            json.dump({"matrix": matrix, "aggregate": agg, "by_size": by_size, "by_yaw": by_yaw,
                       "minimum_viable": mv, "mask_noise": mask, "pose_noise": noise, "comparison": cmp}, fh, indent=2)
    sys.stdout.buffer.write(md.encode("utf-8", errors="replace"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
