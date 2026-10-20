"""Validate an M9 real-device ``raw_capture.json`` before any segmentation.

Checks the raw schema, that images exist, that poses are finite proper rigid
transforms in the fixed ``T_world_from_camera`` convention, that image and
intrinsics dimensions agree, that timestamps are paired, that tracking is TRACKING,
that gravity is valid, that the candidate baseline and view coverage clear the
research minimums, and that the optional support plane is a valid gravity-up floor.

Prints an explicit diagnostics report and exits non-zero if the raw geometry is
invalid — segmentation must not run on invalid geometry. Ground truth is never read.

Usage::

    python scripts/m9_validate_raw_capture.py path/to/M9_<ts>/raw_capture.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from measurex_vision.multiview.real_capture import (
    load_raw_capture,
    validate_raw_capture,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate an M9 raw_capture.json bundle.")
    ap.add_argument("manifest", help="path to raw_capture.json")
    ap.add_argument("--json", action="store_true", help="emit the diagnostics report as JSON")
    args = ap.parse_args(argv)

    raw = load_raw_capture(args.manifest)
    report = validate_raw_capture(raw, base_dir=os.path.dirname(os.path.abspath(args.manifest)))

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"M9 raw capture: {args.manifest}")
        print(f"  pose_source       : {report['pose_source']}")
        print(f"  candidate frames  : {report['candidate_frames']}")
        print(f"  total baseline    : {report['total_baseline_mm']:.0f} mm")
        print(f"  view coverage     : {report['view_coverage_deg']:.0f} deg")
        print(f"  support plane     : {'yes' if report['support_plane_present'] else 'no'}")
        print("  checks:")
        for c in report["checks"]:
            flag = "PASS" if c["ok"] else "FAIL"
            detail = f"  — {c['detail']}" if c["detail"] else ""
            print(f"    [{flag}] {c['check']}{detail}")
        print(f"  RESULT: {'OK' if report['ok'] else 'INVALID'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
