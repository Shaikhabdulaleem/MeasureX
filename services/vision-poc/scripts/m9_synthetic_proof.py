"""M9 synthetic metric-reconstruction proof.

Runs the multi-view visual hull on analytically generated cuboid captures with
exact metric poses and reports GT vs reconstructed L/W/H, metric-scale
equivariance, and the typed-failure behaviour. No GPU, no model, no network.

    python scripts/m9_synthetic_proof.py            # table to stdout
    python scripts/m9_synthetic_proof.py --out DIR  # also write md/json + debug

This is the research proof gate: the geometry must recover cuboid dimensions on
exact synthetic poses before any phone capture. Nothing here reads ground truth
inside the reconstruction — GT is compared only after the fact.
"""

from __future__ import annotations

import argparse
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

# (name, length_m, width_m, height_m) — a range of sizes/aspect ratios, NOT only
# the real 345x290x245 test carton.
BOXES = [
    ("small parcel", 0.200, 0.150, 0.120),
    ("real carton", 0.345, 0.290, 0.245),
    ("medium carton", 0.600, 0.400, 0.350),
    ("large carton", 0.800, 0.600, 0.500),
    ("tall narrow", 0.250, 0.240, 0.800),
]
# Three independent "sweeps" per carton: different yaw, world origin and seed.
SWEEPS = [
    {"yaw_deg": 0.0, "world_origin": (0.0, 0.0, 0.0), "pose_noise_deg": 0.0, "seed": 1},
    {"yaw_deg": 37.0, "world_origin": (0.6, 0.0, -0.4), "pose_noise_deg": 0.0, "seed": 2},
    {"yaw_deg": -62.0, "world_origin": (-0.3, 0.0, 0.5), "pose_noise_deg": 0.15, "seed": 3},
]


def _err(pred: dict, gt: dict) -> dict:
    return {k: 100.0 * (pred[k] - gt[k]) / gt[k] for k in gt}


def run_table(config: ReconstructionConfig) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    for name, L, W, H in BOXES:
        for si, sw in enumerate(SWEEPS):
            bundle, gt = synthetic_capture(length_m=L, width_m=W, height_m=H, **sw)
            t = time.perf_counter()
            r = reconstruct(bundle, config)
            dt = time.perf_counter() - t
            row = {"carton": name, "sweep": si, "frames": len(bundle.frames), "gt": gt, "runtime_s": round(dt, 2)}
            if r["success"]:
                row["pred"] = r["dimensions"]
                row["err_pct"] = _err(r["dimensions"], gt)
                row["quality"] = r["quality"]["level"]
            else:
                row["reason"] = r["reason"]
            rows.append(row)
    abs_pcts = [abs(v) for row in rows if "err_pct" in row for v in row["err_pct"].values()]
    agg = {
        "sequences": len(rows),
        "accepted": sum("err_pct" in r for r in rows),
        "median_abs_pct": float(np.median(abs_pcts)),
        "p90_abs_pct": float(np.percentile(abs_pcts, 90)),
        "p95_abs_pct": float(np.percentile(abs_pcts, 95)),
        "max_abs_pct": float(np.max(abs_pcts)),
    }
    return rows, agg


def scale_equivariance(config: ReconstructionConfig) -> dict:
    b1, _ = synthetic_capture(length_m=0.345, width_m=0.290, height_m=0.245, scale=1.0)
    b2, _ = synthetic_capture(length_m=0.345, width_m=0.290, height_m=0.245, scale=2.0)
    r1 = reconstruct(b1, config)["dimensions"]
    r2 = reconstruct(b2, config)["dimensions"]
    return {"scale1_mm": r1, "scale2_mm": r2, "ratios": {k: round(r2[k] / r1[k], 4) for k in r1}}


def failure_demos(config: ReconstructionConfig) -> dict:
    out = {}
    # Low baseline: identical poses.
    b, _ = synthetic_capture(length_m=0.3, width_m=0.25, height_m=0.2, n_views=5, elevations_deg=(30,))
    import dataclasses
    f0 = b.frames[0]
    dup = dataclasses.replace(b, frames=[dataclasses.replace(f0, frame_id=str(i)) for i in range(5)])
    out["low_baseline"] = reconstruct(dup, config)["reason"]
    # Low view coverage: tiny arc.
    bb, _ = synthetic_capture(length_m=0.3, width_m=0.25, height_m=0.2, n_views=6, elevations_deg=(30,), azimuth_span_deg=3.0, distance_m=3.0)
    cfg2 = dataclasses.replace(config, min_total_baseline_m=0.001, min_view_coverage_deg=20)
    out["low_coverage"] = reconstruct(bb, cfg2)["reason"]
    # Memory guard.
    bc, _ = synthetic_capture(length_m=0.3, width_m=0.25, height_m=0.2)
    out["memory_guard"] = reconstruct(bc, dataclasses.replace(config, max_voxels=1000))["reason"]
    # No metric pose.
    out["metric_pose_unavailable"] = reconstruct_from_provider(ARCoreMetricPoseProvider(), config)["reason"]
    return out


def render_markdown(rows, agg, scale, failures) -> str:
    lines = ["# M9 synthetic proof\n", "## GT vs reconstructed (exact metric poses)\n"]
    lines.append("| carton | sweep | frames | GT L/W/H (mm) | pred L/W/H (mm) | err% L/W/H | quality | s |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in rows:
        gt = r["gt"]
        g = f"{gt['length_mm']}/{gt['width_mm']}/{gt['height_mm']}"
        if "pred" in r:
            p = r["pred"]
            pm = f"{p['length_mm']}/{p['width_mm']}/{p['height_mm']}"
            e = r["err_pct"]
            em = f"{e['length_mm']:+.1f}/{e['width_mm']:+.1f}/{e['height_mm']:+.1f}"
            lines.append(f"| {r['carton']} | {r['sweep']} | {r['frames']} | {g} | {pm} | {em} | {r['quality']} | {r['runtime_s']} |")
        else:
            lines.append(f"| {r['carton']} | {r['sweep']} | {r['frames']} | {g} | FAIL: {r['reason']} | | | {r['runtime_s']} |")
    lines.append(
        f"\n**Aggregate (abs % error, all dims):** median {agg['median_abs_pct']:.2f}% · "
        f"P90 {agg['p90_abs_pct']:.2f}% · P95 {agg['p95_abs_pct']:.2f}% · max {agg['max_abs_pct']:.2f}% · "
        f"accepted {agg['accepted']}/{agg['sequences']}\n"
    )
    lines.append("## Metric-scale equivariance (2x scene+poses -> 2x dims)\n")
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

    config = ReconstructionConfig(fine_divisions=args.fine_divisions, leave_one_out=False)
    rows, agg = run_table(config)
    scale = scale_equivariance(config)
    failures = failure_demos(config)
    md = render_markdown(rows, agg, scale, failures)
    print(md)

    if args.out:
        os.makedirs(args.out, exist_ok=True)
        with open(os.path.join(args.out, "proof_table.md"), "w", encoding="utf-8") as fh:
            fh.write(md)
        with open(os.path.join(args.out, "proof.json"), "w", encoding="utf-8") as fh:
            json.dump({"rows": rows, "aggregate": agg, "scale": scale, "failures": failures}, fh, indent=2)
        # One debug run (with leave-one-out) for artifact inspection.
        b, _ = synthetic_capture(length_m=0.345, width_m=0.290, height_m=0.245)
        reconstruct(b, ReconstructionConfig(fine_divisions=args.fine_divisions), debug_dir=os.path.join(args.out, "debug_real_carton"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
