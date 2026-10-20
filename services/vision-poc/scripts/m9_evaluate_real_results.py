#!/usr/bin/env python
"""Evaluate M9 real-capture run results against tape-measured ground truth.

This is the **only** tool that reads ``ground_truth.json``. The measurement and
fitting code never opens it, so no GT correction, scale multiplier or manual
adjustment can leak into a dimension. It consumes already-computed, GT-free
``run_result.json`` files (from ``m9_run_real_capture.py``) for the 3 independent
sweeps of the same carton.

Reports, per sweep: predicted vs GT L/W/H, absolute error (mm and %), volume error,
accepted/rejected and the failure reason. Across accepted sweeps: median and max
error per dimension, prediction range, standard deviation and repeatability. Also
compares 6-DOF vs 7-DOF (without using GT to pick a production path) and prints the
predeclared first physical research gate verdict.

Usage::

    python scripts/m9_evaluate_real_results.py ground_truth.json \
        sweep_01/run_result.json sweep_02/run_result.json sweep_03/run_result.json
"""

from __future__ import annotations

import argparse
import json
import sys

from measurex_vision.multiview.real_capture import evaluate_runs

_DIMS = ("length_mm", "width_mm", "height_mm")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Evaluate M9 real-capture runs against ground truth.")
    ap.add_argument("ground_truth", help="ground_truth.json {length_mm,width_mm,height_mm}")
    ap.add_argument("runs", nargs="+", help="run_result.json for each independent sweep")
    ap.add_argument("--out", help="write the full evaluation report JSON here")
    args = ap.parse_args(argv)

    with open(args.ground_truth, encoding="utf-8") as fh:
        gt_doc = json.load(fh)
    gt = {k: int(gt_doc[k]) for k in _DIMS}

    runs = []
    for p in args.runs:
        with open(p, encoding="utf-8") as fh:
            runs.append(json.load(fh))

    report = evaluate_runs(runs, gt)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)

    print(f"GT (mm): L={gt['length_mm']} W={gt['width_mm']} H={gt['height_mm']}")
    for s in report["sweeps"]:
        print(f"\nSweep {s['sweep']}: {s.get('manifest')}")
        for label in ("free_7dof", "support_6dof"):
            sc = s[label]
            if not sc.get("present"):
                print(f"  {label:12s}: (not run)")
            elif not sc.get("accepted"):
                print(f"  {label:12s}: REFUSED — {sc.get('reason')}")
            else:
                pe = sc["pct_err"]
                print(f"  {label:12s}: L={sc['pred_mm']['length_mm']} "
                      f"W={sc['pred_mm']['width_mm']} H={sc['pred_mm']['height_mm']} mm  "
                      f"err L={pe['length_mm']:.1f}% W={pe['width_mm']:.1f}% H={pe['height_mm']:.1f}%")

    print("\nRepeatability (accepted sweeps):")
    for label in ("free_7dof", "support_6dof"):
        st = report["repeatability"][label]
        if not st.get("accepted_any"):
            print(f"  {label:12s}: no accepted sweep")
            continue
        print(f"  {label:12s}: {st['sweeps_accepted']}/{st['sweeps_total']} accepted")
        for k in _DIMS:
            d = st["per_dim"][k]
            print(f"    {k:10s} median={d['median_pct_err']:.1f}% max={d['max_pct_err']:.1f}% "
                  f"range={d['pred_range_mm']:.0f}mm repeat={d['repeatability_pct']:.1f}%")

    gate = report["research_gate"]
    print(f"\nFIRST RESEARCH GATE: {'PASS' if gate['passed'] else 'FAIL'}")
    print(f"  criteria: {gate['criteria']}")
    print(f"  free_7dof   passed={gate['free_7dof']['passed']}")
    print(f"  support_6dof passed={gate['support_6dof']['passed']}")
    print(f"  {gate['note']}")
    return 0 if gate["passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
