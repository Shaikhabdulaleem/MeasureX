"""M9 synthetic metric-reconstruction proof.

Runs the multi-view visual hull on analytically generated cuboid captures with
known metric poses and reports, as SEPARATE experiments:

  1. EXACT-POSE full-coverage sanity test  (3 elevation rings, 330 deg azimuth) —
     a generous geometry check, NOT the warehouse workflow.
  2. POSE-NOISE robustness                 (same geometry, controlled rotation
     perturbations) — kept apart from the exact-pose aggregate.
  3. PRACTICAL SHORT-SWEEP matrix          (one continuous pass: few frames over a
     small azimuth span) — representative of a hand-held capture; finds the
     minimum geometrically observable pattern.
  4. RESOLUTION CONVERGENCE                 (does error shrink toward GT as the
     voxel shrinks, or is the floor set by hull/coverage geometry?).
  5. VOXEL QUANTIZATION analysis            (error in voxels, per dimension).

No GPU, no model, no network. Nothing here reads ground truth inside the
reconstruction — GT is compared only after the fact. No correction factor, no
dimension multiplier, and the known carton size never enters reconstruction.

    python scripts/m9_synthetic_proof.py            # tables to stdout
    python scripts/m9_synthetic_proof.py --out DIR  # also write md/json + debug
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
from measurex_vision.multiview.pipeline import reconstruct_from_provider
from measurex_vision.multiview.pose_provider import ARCoreMetricPoseProvider
from measurex_vision.multiview.synthetic import synthetic_capture

REAL_CARTON = (0.345, 0.290, 0.245)  # the physical test carton (mm: 345/290/245)

# (name, length_m, width_m, height_m) — a range of sizes/aspect ratios, NOT only
# the real test carton.
BOXES = [
    ("small parcel", 0.200, 0.150, 0.120),
    ("real carton", *REAL_CARTON),
    ("medium carton", 0.600, 0.400, 0.350),
    ("large carton", 0.800, 0.600, 0.500),
    ("tall narrow", 0.250, 0.240, 0.800),
]
# EXACT POSE: three independent full-coverage sweeps, pose_noise_deg == 0 for all.
EXACT_SWEEPS = [
    {"yaw_deg": 0.0, "world_origin": (0.0, 0.0, 0.0), "seed": 1},
    {"yaw_deg": 37.0, "world_origin": (0.6, 0.0, -0.4), "seed": 2},
    {"yaw_deg": -62.0, "world_origin": (-0.3, 0.0, 0.5), "seed": 3},
]
# POSE NOISE robustness: explicit controlled per-frame rotation perturbations,
# reported separately — never mixed into the exact-pose accuracy aggregate.
NOISE_SWEEPS = [
    {"pose_noise_deg": 0.15, "seed": 11},
    {"pose_noise_deg": 0.30, "seed": 12},
    {"pose_noise_deg": 0.50, "seed": 13},
]


def _err_pct(pred: dict, gt: dict) -> dict:
    return {k: 100.0 * (pred[k] - gt[k]) / gt[k] for k in gt}


def _aggregate(rows: list[dict]) -> dict:
    abs_pcts = [abs(v) for r in rows if "err_pct" in r for v in r["err_pct"].values()]
    return {
        "sequences": len(rows),
        "accepted": sum("err_pct" in r for r in rows),
        "median_abs_pct": float(np.median(abs_pcts)) if abs_pcts else None,
        "p90_abs_pct": float(np.percentile(abs_pcts, 90)) if abs_pcts else None,
        "p95_abs_pct": float(np.percentile(abs_pcts, 95)) if abs_pcts else None,
        "max_abs_pct": float(np.max(abs_pcts)) if abs_pcts else None,
    }


def run_group(config: ReconstructionConfig, sweeps: list[dict]) -> tuple[list[dict], dict]:
    """Reconstruct every (box, sweep) full-coverage capture; return rows + agg."""
    rows: list[dict] = []
    for name, L, W, H in BOXES:
        for si, sw in enumerate(sweeps):
            bundle, gt = synthetic_capture(length_m=L, width_m=W, height_m=H, **sw)
            t = time.perf_counter()
            r = reconstruct(bundle, config)
            dt = time.perf_counter() - t
            row = {"carton": name, "sweep": si, "frames": len(bundle.frames),
                   "gt": gt, "runtime_s": round(dt, 2), **{k: v for k, v in sw.items() if k != "world_origin"}}
            if r["success"]:
                row["pred"] = r["dimensions"]
                row["err_pct"] = _err_pct(r["dimensions"], gt)
                row["quality"] = r["quality"]["level"]
            else:
                row["reason"] = r["reason"]
            rows.append(row)
    return rows, _aggregate(rows)


def short_sweep_matrix(config: ReconstructionConfig) -> list[dict]:
    """One continuous hand-held pass (single ring, modest elevation ramp) over a
    small azimuth span, for the real carton. Finds the minimum observable pattern.
    Not tuned to GT — the capture geometry is varied, the algorithm is fixed."""
    L, W, H = REAL_CARTON
    rows: list[dict] = []
    for frames in (6, 8, 10, 12):
        for span in (30.0, 45.0, 60.0, 90.0, 120.0):
            bundle, gt = synthetic_capture(
                length_m=L, width_m=W, height_m=H, n_views=frames,
                azimuth_span_deg=span, elevations_deg=(15.0, 40.0),
                continuous_sweep=True, image_wh=(540, 720), distance_m=1.3,
            )
            t = time.perf_counter()
            r = reconstruct(bundle, config)
            dt = time.perf_counter() - t
            row = {"frames": frames, "azimuth_span_deg": span, "runtime_s": round(dt, 2)}
            if r["success"]:
                d = r["diagnostics"]
                row.update(
                    accepted=True,
                    pred=r["dimensions"],
                    err_pct=_err_pct(r["dimensions"], gt),
                    total_baseline_mm=round(d["total_baseline_mm"]),
                    max_view_angle_deg=round(d["max_view_angle_deg"], 1),
                    voxel_mm=round(d["voxel_size_m"] * 1000, 1),
                    loo_spread_max=r["quality"]["leave_one_out"].get("spread_frac_max"),
                )
            else:
                row.update(accepted=False, reason=r["reason"],
                           debug=r.get("debug_dimensions_mm"))
            rows.append(row)
    return rows


def resolution_convergence(base: ReconstructionConfig) -> list[dict]:
    """Real carton, full exact-pose coverage, increasing fine resolution. Reports
    whether error converges toward GT as the voxel shrinks."""
    bundle, gt = synthetic_capture(length_m=REAL_CARTON[0], width_m=REAL_CARTON[1], height_m=REAL_CARTON[2])
    rows: list[dict] = []
    for fine in (60, 90, 120, 160):
        cfg = dataclasses.replace(base, fine_divisions=fine, leave_one_out=False)
        t = time.perf_counter()
        r = reconstruct(bundle, cfg)
        dt = time.perf_counter() - t
        d = r["diagnostics"]
        pred = r["dimensions"]
        rows.append({
            "fine_divisions": fine,
            "voxel_mm": round(d["voxel_size_m"] * 1000, 2),
            "pred": pred,
            "abs_err_mm": {k: abs(pred[k] - gt[k]) for k in gt},
            "max_abs_pct": max(abs(100.0 * (pred[k] - gt[k]) / gt[k]) for k in gt),
            "final_voxels": d["final_occupied_voxels"],
            "runtime_s": round(dt, 2),
            "gt": gt,
        })
    return rows


def quantization_analysis(conv_rows: list[dict]) -> dict:
    """At the finest resolution, express each dimension's residual error in voxels
    (abs_err_mm / voxel_mm). An error that stays many voxels large as the voxel
    shrinks is hull/coverage geometry, not quantization."""
    fine = conv_rows[-1]
    voxel = fine["voxel_mm"]
    return {
        "fine_divisions": fine["fine_divisions"],
        "voxel_mm": voxel,
        "per_dim": {
            k: {"abs_err_mm": fine["abs_err_mm"][k], "error_in_voxels": round(fine["abs_err_mm"][k] / voxel, 2)}
            for k in fine["gt"]
        },
    }


def scale_equivariance(config: ReconstructionConfig) -> dict:
    b1, _ = synthetic_capture(length_m=0.345, width_m=0.290, height_m=0.245, scale=1.0)
    b2, _ = synthetic_capture(length_m=0.345, width_m=0.290, height_m=0.245, scale=2.0)
    r1 = reconstruct(b1, config)["dimensions"]
    r2 = reconstruct(b2, config)["dimensions"]
    return {"scale1_mm": r1, "scale2_mm": r2, "ratios": {k: round(r2[k] / r1[k], 4) for k in r1}}


def failure_demos(config: ReconstructionConfig) -> dict:
    out = {}
    b, _ = synthetic_capture(length_m=0.3, width_m=0.25, height_m=0.2, n_views=5, elevations_deg=(30,))
    f0 = b.frames[0]
    dup = dataclasses.replace(b, frames=[dataclasses.replace(f0, frame_id=str(i)) for i in range(5)])
    out["low_baseline"] = reconstruct(dup, config)["reason"]
    bb, _ = synthetic_capture(length_m=0.3, width_m=0.25, height_m=0.2, n_views=6, elevations_deg=(30,), azimuth_span_deg=3.0, distance_m=3.0)
    cfg2 = dataclasses.replace(config, min_total_baseline_m=0.001, min_view_coverage_deg=20)
    out["low_coverage"] = reconstruct(bb, cfg2)["reason"]
    bc, _ = synthetic_capture(length_m=0.3, width_m=0.25, height_m=0.2)
    out["memory_guard"] = reconstruct(bc, dataclasses.replace(config, max_voxels=1000))["reason"]
    out["metric_pose_unavailable"] = reconstruct_from_provider(ARCoreMetricPoseProvider(), config)["reason"]
    # Quality gate: a stable capture with an impossibly tight spread threshold must
    # fail typed rather than return a successful metric measurement.
    bd, _ = synthetic_capture(length_m=0.345, width_m=0.290, height_m=0.245)
    gated = dataclasses.replace(config, leave_one_out=True, leave_one_out_max_runs=4, max_dim_spread_frac=1e-6)
    out["unstable_reconstruction"] = reconstruct(bd, gated)["reason"]
    return out


def _dims(d: dict) -> str:
    return f"{d['length_mm']}/{d['width_mm']}/{d['height_mm']}"


def _group_table(title: str, rows: list[dict], agg: dict) -> list[str]:
    lines = [f"### {title}\n",
             "| carton | sweep | frames | noise deg | GT L/W/H | pred L/W/H | err% L/W/H | quality | s |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        noise = r.get("pose_noise_deg", 0.0)
        if "pred" in r:
            e = r["err_pct"]
            em = f"{e['length_mm']:+.1f}/{e['width_mm']:+.1f}/{e['height_mm']:+.1f}"
            lines.append(f"| {r['carton']} | {r['sweep']} | {r['frames']} | {noise} | {_dims(r['gt'])} | {_dims(r['pred'])} | {em} | {r['quality']} | {r['runtime_s']} |")
        else:
            lines.append(f"| {r['carton']} | {r['sweep']} | {r['frames']} | {noise} | {_dims(r['gt'])} | FAIL: {r['reason']} | | | {r['runtime_s']} |")
    a = agg
    if a["median_abs_pct"] is not None:
        lines.append(
            f"\n**Aggregate (abs % error, all dims):** median {a['median_abs_pct']:.2f}% · "
            f"P90 {a['p90_abs_pct']:.2f}% · P95 {a['p95_abs_pct']:.2f}% · max {a['max_abs_pct']:.2f}% · "
            f"accepted {a['accepted']}/{a['sequences']}\n"
        )
    return lines


def render_markdown(exact, exact_agg, noise, noise_agg, matrix, conv, quant, scale, failures) -> str:
    lines = ["# M9 synthetic proof\n"]
    lines += _group_table("1. EXACT POSE — full-coverage sanity test (pose_noise = 0)", exact, exact_agg)
    lines += _group_table("2. POSE-NOISE robustness (controlled perturbations)", noise, noise_agg)

    lines.append("## 3. PRACTICAL SHORT-SWEEP matrix (real carton, one continuous pass)\n")
    lines.append("| frames | azim span | accepted | pred L/W/H | err% L/W/H | baseline mm | coverage deg | voxel mm | LOO spread | s |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in matrix:
        if r["accepted"]:
            e = r["err_pct"]
            em = f"{e['length_mm']:+.1f}/{e['width_mm']:+.1f}/{e['height_mm']:+.1f}"
            sp = r["loo_spread_max"]
            sp = f"{sp:.3f}" if sp is not None else "—"
            lines.append(f"| {r['frames']} | {r['azimuth_span_deg']:.0f} | yes | {_dims(r['pred'])} | {em} | {r['total_baseline_mm']} | {r['max_view_angle_deg']} | {r['voxel_mm']} | {sp} | {r['runtime_s']} |")
        else:
            dbg = f" (debug {_dims(r['debug'])})" if r.get("debug") else ""
            lines.append(f"| {r['frames']} | {r['azimuth_span_deg']:.0f} | **no** | FAIL: {r['reason']}{dbg} | | | | | | {r['runtime_s']} |")

    lines.append("\n## 4. RESOLUTION CONVERGENCE (real carton, exact poses, full coverage)\n")
    lines.append("| fine_divisions | voxel mm | pred L/W/H | abs err L/W/H mm | max abs % | final voxels | s |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in conv:
        ae = r["abs_err_mm"]
        aem = f"{ae['length_mm']}/{ae['width_mm']}/{ae['height_mm']}"
        lines.append(f"| {r['fine_divisions']} | {r['voxel_mm']} | {_dims(r['pred'])} | {aem} | {r['max_abs_pct']:.1f}% | {r['final_voxels']} | {r['runtime_s']} |")

    lines.append("\n## 5. VOXEL QUANTIZATION analysis (finest resolution)\n")
    lines.append(f"voxel = {quant['voxel_mm']} mm (fine_divisions={quant['fine_divisions']})\n")
    lines.append("| dimension | abs err mm | error in voxels |")
    lines.append("|---|---|---|")
    for k, v in quant["per_dim"].items():
        lines.append(f"| {k} | {v['abs_err_mm']} | {v['error_in_voxels']} |")

    lines.append("\n## Metric-scale equivariance (2x scene+poses -> 2x dims)\n")
    lines.append(f"scale1 = {scale['scale1_mm']}\n\nscale2 = {scale['scale2_mm']}\n\nratios = {scale['ratios']}\n")
    lines.append("## Typed failure behaviour\n")
    for k, v in failures.items():
        lines.append(f"- `{k}` -> `{v}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="write md/json (and one debug run) here")
    ap.add_argument("--fine-divisions", type=int, default=90)
    args = ap.parse_args()

    base = ReconstructionConfig(fine_divisions=args.fine_divisions, leave_one_out=False)
    gated = dataclasses.replace(base, leave_one_out=True, leave_one_out_max_runs=4)

    exact, exact_agg = run_group(base, EXACT_SWEEPS)
    noise, noise_agg = run_group(base, NOISE_SWEEPS)
    matrix = short_sweep_matrix(gated)
    conv = resolution_convergence(base)
    quant = quantization_analysis(conv)
    scale = scale_equivariance(base)
    failures = failure_demos(base)

    md = render_markdown(exact, exact_agg, noise, noise_agg, matrix, conv, quant, scale, failures)
    print(md)

    if args.out:
        os.makedirs(args.out, exist_ok=True)
        with open(os.path.join(args.out, "proof_table.md"), "w", encoding="utf-8") as fh:
            fh.write(md)
        with open(os.path.join(args.out, "proof.json"), "w", encoding="utf-8") as fh:
            json.dump({
                "exact_pose": {"rows": exact, "aggregate": exact_agg},
                "pose_noise": {"rows": noise, "aggregate": noise_agg},
                "short_sweep_matrix": matrix,
                "resolution_convergence": conv,
                "quantization": quant,
                "scale": scale,
                "failures": failures,
            }, fh, indent=2)
        b, _ = synthetic_capture(length_m=0.345, width_m=0.290, height_m=0.245)
        reconstruct(b, base, debug_dir=os.path.join(args.out, "debug_real_carton"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
