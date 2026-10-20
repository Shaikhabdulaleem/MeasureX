#!/usr/bin/env python
"""Prepare a strict M9 ``capture.json`` from a raw capture + selected 8 frames.

Runs the existing M8 segmentation components on each selected frame — Grounding
DINO (narrow prompt ``"cardboard box."``) to propose the single carton, then SAM 2
to cut a clean mask — and writes the strict ``capture.json`` (masks, intrinsics,
metric poses, gravity, optional support plane) that the M9 cuboid fitter consumes.
No monocular depth is used. The fitter never learns ground truth.

If segmentation fails for a frame (no target, multiple targets, or an unclean /
off-frame / wrong-sized mask) a **typed frame failure** is recorded — a mask is
never fabricated. Debug overlays and per-frame segmentation diagnostics are written
for every selected frame.

The pure orchestration (:func:`prepare_capture`) takes a ``segment_fn`` so it is
testable with precomputed masks and no model downloads; the CLI wires ``segment_fn``
to Grounding DINO + SAM 2.

Usage::

    python scripts/m9_prepare_real_capture.py path/to/raw_capture.json \
        --selection path/to/selected_frames.json --out path/to/processed/
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from measurex_vision.multiview.real_capture import (
    RawCapture,
    RawFrame,
    load_raw_capture,
)
from measurex_vision.quality.mask_checks import validate_mask

# A mask that survives these GT-free checks is "clean enough" to measure.
MIN_AREA_RATIO = 0.02
MAX_AREA_RATIO = 0.90
MAX_BORDER_RATIO = 0.30
# A "strong" single detection: above this score, and clearly ahead of the runner-up.
STRONG_SCORE = 0.40
AMBIGUOUS_MARGIN = 0.90  # runner-up within 90% of the top score => ambiguous

SegmentFn = Callable[[np.ndarray, RawFrame], "FrameMask | FrameFailure"]


@dataclass(frozen=True)
class FrameMask:
    frame_id: str
    mask: np.ndarray                 # (H, W) bool
    detector_score: float
    bbox_xyxy: tuple[float, float, float, float]


@dataclass(frozen=True)
class FrameFailure:
    frame_id: str
    code: str
    detail: str = ""


def assess_detections(scores: list[float]) -> str | None:
    """GT-free detector gate. Returns a failure code string, or None when there is
    exactly one strong carton target."""
    strong = [s for s in scores if s >= STRONG_SCORE]
    if not strong:
        return "no_target"
    if len(strong) >= 2:
        top = max(strong)
        if sorted(strong, reverse=True)[1] >= AMBIGUOUS_MARGIN * top:
            return "multiple_targets"
    return None


def assess_mask(mask: np.ndarray) -> str | None:
    """GT-free mask gate (area + image-border contact). Returns a failure code
    string, or None when the mask is clean enough to measure.

    shortcut: no connected-component fragmentation check (needs a CC lib not in the
    CI deps); single-target is enforced at the detection stage. Add a CC check once
    real SAM 2 masks are in hand and a labelling pass exists."""
    code = validate_mask(
        mask,
        min_area_ratio=MIN_AREA_RATIO,
        max_area_ratio=MAX_AREA_RATIO,
        max_border_ratio=MAX_BORDER_RATIO,
    )
    return code.value if code is not None else None


def _border_ratio(mask: np.ndarray) -> float:
    m = np.asarray(mask, dtype=bool)
    border = np.zeros_like(m)
    border[0, :] = border[-1, :] = border[:, 0] = border[:, -1] = True
    return float((m & border).sum()) / max(float(m.sum()), 1.0)


def prepare_capture(
    raw: RawCapture,
    selected_ids: list[str],
    segment_fn: SegmentFn,
    out_dir: str,
    images_dir: str,
    *,
    load_image: Callable[[str], np.ndarray] | None = None,
    write_overlay: Callable[[str, np.ndarray, FrameMask], None] | None = None,
) -> dict[str, Any]:
    """Segment the selected frames and write the strict ``capture.json``.

    ``segment_fn`` maps ``(image, raw_frame) -> FrameMask | FrameFailure``. Failures
    are recorded, never fabricated into masks. Returns a diagnostics dict; the
    manifest contains only frames whose mask passed, and is marked not-ok when fewer
    than the reconstruction minimum (4) survive."""
    os.makedirs(os.path.join(out_dir, "masks"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "overlays"), exist_ok=True)
    load_image = load_image or _load_image_pil

    by_id = {f.frame_id: f for f in raw.frames}
    doc_frames: list[dict[str, Any]] = []
    seg_diag: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for fid in selected_ids:
        rf = by_id.get(fid)
        if rf is None:
            failures.append({"frame_id": fid, "code": "frame_not_found"})
            continue
        image = load_image(os.path.join(images_dir, rf.image))
        result = segment_fn(image, rf)
        if isinstance(result, FrameFailure):
            failures.append({"frame_id": fid, "code": result.code, "detail": result.detail})
            seg_diag.append({"frame_id": fid, "ok": False, "code": result.code, "detail": result.detail})
            continue

        code = assess_mask(result.mask)
        area_ratio = float(result.mask.sum()) / float(result.mask.size)
        ys, xs = np.nonzero(result.mask)
        bbox_wh = (int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)) if xs.size else (0, 0)
        diag = {
            "frame_id": fid,
            "detector_score": result.detector_score,
            "mask_area_ratio": area_ratio,
            "mask_bbox_wh_px": bbox_wh,
            "mask_border_ratio": _border_ratio(result.mask),
            "ok": code is None,
        }
        if code is not None:
            diag["code"] = code
            failures.append({"frame_id": fid, "code": code})
            seg_diag.append(diag)
            continue
        seg_diag.append(diag)

        rel_mask = f"masks/{fid}.png"
        _save_mask_png(result.mask, os.path.join(out_dir, rel_mask))
        # Copy the native-orientation RGB into the processed bundle so the strict
        # manifest is self-contained and portable (load_bundle resolves image paths
        # relative to capture.json).
        rel_img = f"frames/{os.path.basename(rf.image)}"
        os.makedirs(os.path.join(out_dir, "frames"), exist_ok=True)
        shutil.copyfile(os.path.join(images_dir, rf.image), os.path.join(out_dir, rel_img))
        if write_overlay is not None:
            write_overlay(os.path.join(out_dir, "overlays", f"overlay_{fid}.jpg"), image, result)
        doc_frames.append({
            "frame_id": fid,
            "image": rel_img,
            "mask": rel_mask,
            "intrinsics": {k: rf.intrinsics[k] for k in ("fx", "fy", "cx", "cy", "width", "height")},
            "T_world_from_camera": rf.T_world_from_camera.tolist(),
        })

    manifest = {
        "schema_version": 1,
        "measurement_tier": "metric",
        "pose_source": raw.pose_source,
        "pose_convention": "T_world_from_camera",
        "units": "meters",
        "gravity_world": [float(x) for x in raw.gravity_world],
        "frames": doc_frames,
    }
    if raw.support_plane is not None:
        manifest["support_plane"] = raw.support_plane

    ok = len(doc_frames) >= 4
    if ok:
        with open(os.path.join(out_dir, "capture.json"), "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2)
    with open(os.path.join(out_dir, "segmentation_diagnostics.json"), "w", encoding="utf-8") as fh:
        json.dump({"frames": seg_diag, "failures": failures}, fh, indent=2)

    return {
        "ok": ok,
        "frames_requested": len(selected_ids),
        "frames_segmented": len(doc_frames),
        "failures": failures,
        "capture_json": os.path.join(out_dir, "capture.json") if ok else None,
        "segmentation_diagnostics": os.path.join(out_dir, "segmentation_diagnostics.json"),
    }


def _load_image_pil(path: str) -> np.ndarray:
    from PIL import Image

    with Image.open(path) as img:
        return np.asarray(img.convert("RGB"), dtype=np.uint8)


def _save_mask_png(mask: np.ndarray, path: str) -> None:
    from PIL import Image

    Image.fromarray((np.asarray(mask, dtype=bool) * 255).astype(np.uint8)).save(path)


def _write_overlay_pil(path: str, image: np.ndarray, fm: FrameMask) -> None:
    """Debug overlay: detector bbox + tinted SAM mask on the native-orientation RGB.
    Uses Pillow only (no cv2), so it runs wherever the dev extra is installed."""
    from PIL import Image, ImageDraw

    base = Image.fromarray(np.asarray(image, dtype=np.uint8)).convert("RGB")
    tint = np.zeros((*fm.mask.shape, 3), dtype=np.uint8)
    tint[fm.mask] = (0, 180, 0)
    over = Image.blend(base, Image.fromarray(tint).convert("RGB"), 0.35)
    draw = ImageDraw.Draw(over)
    x0, y0, x1, y1 = fm.bbox_xyxy
    draw.rectangle([x0, y0, x1, y1], outline=(255, 0, 0), width=3)
    draw.text((max(2, x0), max(2, y0 - 12)), f"{fm.detector_score:.2f}", fill=(255, 0, 0))
    over.save(path, quality=95)


def _gdino_sam_segment_fn() -> SegmentFn:
    """Wire Grounding DINO (prompt 'cardboard box.') + SAM 2 into a ``segment_fn``.
    Models are loaded lazily on first call; this never runs in unit tests or CI."""
    from measurex_vision.detection.grounding_dino import GroundingDinoDetector
    from measurex_vision.segmentation.sam2 import Sam2Segmenter

    detector = GroundingDinoDetector(prompt="cardboard box.")
    segmenter = Sam2Segmenter()

    def seg(image: np.ndarray, rf: RawFrame) -> FrameMask | FrameFailure:
        detections = detector.detect(image)
        code = assess_detections([d.score for d in detections])
        if code is not None:
            return FrameFailure(rf.frame_id, code, f"{len(detections)} detection(s)")
        target = detector.select_target(detections)
        mask = np.asarray(segmenter.segment(image, target.bbox_xyxy), dtype=bool)
        return FrameMask(rf.frame_id, mask, target.score, target.bbox_xyxy)

    return seg


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Segment selected M9 frames into a strict capture.json.")
    ap.add_argument("manifest", help="path to raw_capture.json")
    ap.add_argument("--selection", help="selected_frames.json (default: beside manifest)")
    ap.add_argument("--out", required=True, help="output directory for the processed capture")
    args = ap.parse_args(argv)

    base = os.path.dirname(os.path.abspath(args.manifest))
    raw = load_raw_capture(args.manifest)
    sel_path = args.selection or os.path.join(base, "selected_frames.json")
    with open(sel_path, encoding="utf-8") as fh:
        selected_ids = json.load(fh)["selected_frame_ids"]

    report = prepare_capture(
        raw, selected_ids, _gdino_sam_segment_fn(), args.out, images_dir=base,
        write_overlay=_write_overlay_pil,
    )
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
