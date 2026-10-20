#!/usr/bin/env python
"""Run the M9 cuboid fit on a prepared strict ``capture.json`` (one sweep).

Runs both configurations independently and never chooses between them from
accuracy — ground truth is **not** available to this script:

* 7-DOF free cuboid fit (always);
* 6-DOF support-plane cuboid fit (only when the bundle carries a valid support
  plane);
* image-space quantisation uncertainty of the 7-DOF fit (recorded, not gated into
  a new production threshold).

Writes ``run_result.json`` beside the manifest (or ``--out``) with, per fit:
success/failure, L/W/H, mean/min IoU, boundary residual, identifiability,
leave-one-out evidence and spread, view coverage, baseline, minimum mask bbox
pixels, quantisation uncertainty, optimiser status and runtime.

Usage::

    python scripts/m9_run_real_capture.py path/to/processed/capture.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from measurex_vision.multiview.real_capture import run_capture


def _summary(label: str, r: dict | None) -> str:
    if r is None:
        return f"  {label:12s}: (no support plane — not run)"
    if not r.get("success"):
        return f"  {label:12s}: REFUSED — {r.get('reason')}"
    d = r["dimensions"]
    diag = r.get("diagnostics", {})
    return (f"  {label:12s}: L={d['length_mm']} W={d['width_mm']} H={d['height_mm']} mm  "
            f"meanIoU={diag.get('mean_iou', 0):.3f} minIoU={diag.get('min_iou', 0):.3f}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the M9 cuboid fit on a prepared capture.json.")
    ap.add_argument("manifest", help="path to the prepared capture.json")
    ap.add_argument("--out", help="output JSON path (default: run_result.json beside manifest)")
    args = ap.parse_args(argv)

    result = run_capture(args.manifest)
    out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.manifest)), "run_result.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)

    print(f"M9 cuboid fit: {args.manifest}")
    print(_summary("free_7dof", result["free_7dof"]))
    print(_summary("support_6dof", result["support_6dof"]))
    q = result["quantization"]
    print(f"  quantization: L±{q.get('length_mm')} W±{q.get('width_mm')} H±{q.get('height_mm')} mm "
          f"(min mask bbox {q.get('min_mask_bbox_px')} px)")
    print(f"  wrote       : {out}")
    print("  NOTE: both configurations reported independently; no GT used here.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
