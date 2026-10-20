#!/usr/bin/env python
"""Select exactly 8 frames from an M9 ``raw_capture.json`` candidate pool.

Selection is ground-truth-free: it uses only the exported guidance target and the
metric camera centres. Each camera's azimuth around the target (gravity-up) is
computed, the best contiguous ``>= 120 deg`` sweep is taken, and 8 approximately
evenly spaced positions are chosen across it, reported in chronological sweep order.
Frames are **never** selected by resulting dimension accuracy.

Writes ``selected_frames.json`` next to the manifest (or ``--out``) and prints the
selection with its coverage, adjacent angular separations, baseline and distances.

Usage::

    python scripts/m9_select_real_frames.py path/to/raw_capture.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from measurex_vision.multiview.real_capture import (
    SELECT_FRAMES,
    load_raw_capture,
    select_frames,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Select 8 frames from an M9 raw capture.")
    ap.add_argument("manifest", help="path to raw_capture.json")
    ap.add_argument("-n", "--num", type=int, default=SELECT_FRAMES, help="frames to select (default 8)")
    ap.add_argument("--out", help="output JSON path (default: selected_frames.json beside manifest)")
    args = ap.parse_args(argv)

    raw = load_raw_capture(args.manifest)
    result = select_frames(raw, n=args.num)
    out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.manifest)), "selected_frames.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)

    print(f"M9 frame selection: {args.manifest}")
    print(f"  selected    : {result['selected_frame_ids']}")
    print(f"  coverage    : {result['coverage_deg']:.0f} deg")
    print(f"  separations : {[round(s, 1) for s in result.get('adjacent_separations_deg', [])]} deg")
    print(f"  baseline    : {result.get('total_baseline_mm', 0.0):.0f} mm")
    print(f"  distances   : {[round(d, 3) for d in result.get('camera_target_distances_m', [])]} m")
    print(f"  wrote       : {out}")
    print(f"  RESULT: {'OK' if result['ok'] else 'INSUFFICIENT — ' + result.get('reason', '')}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
