"""Command-line entry point for the vision POC.

    python -m measurex_vision.cli --help
    python -m measurex_vision.cli image path/to/image.jpg --debug
    python -m measurex_vision.cli video path/to/video.mp4 --debug

M1: ``image`` runs the depth stage (``DepthEstimator``) and, with ``--debug``,
writes depth artifacts, then prints depth diagnostics as JSON. Full L/W/H
(detection + segmentation + geometry) and ``video`` are later milestones.
"""

from __future__ import annotations

import argparse
import json
import os

from . import __version__

_PENDING = {
    "status": "not_implemented",
    "message": "Not wired yet (later milestone). See services/vision-poc/CLAUDE.md.",
}


def _run_image(args) -> int:
    from .contracts import MeasurementSuccess
    from .depth import get_depth_estimator
    from .detection import get_detector
    from .io import load_image
    from .pipeline import (
        MaskedCloud,
        build_masked_cloud,
        build_measurement,
        measure_from_cloud,
    )
    from .segmentation import get_segmenter

    image = load_image(args.path)
    # Only model-backed providers take a checkpoint; box_mask is model-free.
    seg_cfg = {"checkpoint_path": args.checkpoint} if args.segmenter != "box_mask" else {}
    providers = {
        "detector": get_detector(args.detector),
        "segmenter": get_segmenter(args.segmenter, **seg_cfg),
        "depth": get_depth_estimator(args.provider, checkpoint_path=args.checkpoint),
    }

    if args.debug:
        # Build the cloud once; save artifacts; measure from the same cloud.
        cloud = build_masked_cloud(image, **providers)
        outcome = measure_from_cloud(cloud) if isinstance(cloud, MaskedCloud) else cloud
        payload = {"input": args.path, **outcome.to_dict()}
        out_dir = os.environ.get("MEASUREX_VISION_OUTPUT_DIR", "./outputs")
        if isinstance(cloud, MaskedCloud):
            _save_debug_artifacts(out_dir, image, cloud, payload)
    else:
        outcome = build_measurement(image, **providers)
        payload = {"input": args.path, **outcome.to_dict()}

    print(json.dumps(payload, indent=2))
    return 0 if isinstance(outcome, MeasurementSuccess) else 2


def _save_debug_artifacts(out_dir: str, image, cloud, payload: dict) -> None:
    from .visualization import save_cloud_artifacts, save_depth_artifacts

    os.makedirs(out_dir, exist_ok=True)
    save_depth_artifacts(out_dir, image, cloud.depth, mask=cloud.mask)
    save_cloud_artifacts(
        out_dir, image, cloud.mask, cloud.points_m,
        bbox_xyxy=cloud.detection.bbox_xyxy, diagnostics=cloud.diagnostics.to_dict(),
    )
    with open(os.path.join(out_dir, "measurement.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="measurex-vision",
        description="MeasureX camera-only shipment dimensioning (research POC).",
    )
    parser.add_argument("--version", action="version", version=f"measurex-vision {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="{image,video}")

    p_image = sub.add_parser("image", help="detect + segment + depth -> masked cloud (single image)")
    p_image.add_argument("path", help="path to the image file")
    p_image.add_argument("--detector", default="central_candidate", help="detector (default: central_candidate)")
    p_image.add_argument("--segmenter", default="sam2", help="segmenter (default: sam2)")
    p_image.add_argument("--provider", default="depth_pro", help="depth provider (default: depth_pro)")
    p_image.add_argument("--checkpoint", default=None, help="model checkpoint path (else env/default)")
    p_image.add_argument("--debug", action="store_true", help="save debug artifacts")

    p_video = sub.add_parser("video", help="measure from a short MP4/MOV video")
    p_video.add_argument("path", help="path to the video file")
    p_video.add_argument("--debug", action="store_true", help="save intermediate debug artifacts")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "image":
        return _run_image(args)
    if args.command == "video":
        print(json.dumps({**_PENDING, "input": args.path, "capture_type": "video"}, indent=2))
        return 2
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
