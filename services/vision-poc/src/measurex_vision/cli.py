"""Command-line entry point for the vision POC.

    python -m measurex_vision.cli --help
    python -m measurex_vision.cli image path/to/image.jpg --debug
    python -m measurex_vision.cli video path/to/video.mp4 --debug

``image`` runs the full single-frame pipeline (detect → segment → depth → plane
→ L/W/H); ``video`` samples frames, measures each, and temporally stabilizes.
Both print a MeasurementSuccess/Failure JSON; ``--debug`` writes artifacts.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from .models import PRODUCTION_STACK, get_metadata


def _detector_name(args) -> str:
    """Resolve the detector. ``--production`` defaults to the approved proposer
    (Grounding DINO), never the model-free central_candidate fallback."""
    if args.detector:
        return args.detector
    return PRODUCTION_STACK["detector"] if args.production else "central_candidate"


def _segmenter_name(args) -> str:
    """Resolve the segmenter. SAM 2 is the default in every mode; box_mask is a
    synthetic/test aid only and is never defaulted to."""
    return args.segmenter or PRODUCTION_STACK["segmenter"]


def _detector_cfg(args, detector: str) -> dict:
    """Grounding DINO tuning knobs; empty for the model-free detector."""
    if detector != "grounding_dino":
        return {}
    cfg = {"box_threshold": args.box_threshold}
    if args.prompt:
        cfg["prompt"] = args.prompt
    return cfg


def _depth_provider(args) -> str:
    """Resolve the depth provider: no production-safe default selects Depth Pro."""
    if args.provider:
        return args.provider
    return PRODUCTION_STACK["depth"] if args.production else "depth_pro"


def _print_resolved(detector: str, segmenter: str, depth: str, production: bool) -> None:
    """Print the resolved stack (with pinned revisions) before inference.

    Goes to stderr so the measurement JSON on stdout stays machine-parseable."""
    def rev(key: str) -> str:
        try:
            return get_metadata(key).revision
        except ValueError:
            return "unknown"

    print(
        "resolved providers:\n"
        f"  detector : {detector} (rev {rev(detector)})\n"
        f"  segmenter: {segmenter} (rev {rev(segmenter)})\n"
        f"  depth    : {depth} (rev {rev(depth)})\n"
        f"  production mode: {production}",
        file=sys.stderr,
    )


def _run_image(args) -> int:
    from .contracts import MeasurementSuccess
    from .depth import get_depth_estimator
    from .detection import get_detector
    from .io import exif_focal_px, load_image
    from .pipeline import (
        MaskedCloud,
        build_masked_cloud,
        build_measurement,
        measure_from_cloud,
    )
    from .segmentation import get_segmenter

    image = load_image(args.path)
    detector, segmenter, depth = _detector_name(args), _segmenter_name(args), _depth_provider(args)
    _print_resolved(detector, segmenter, depth, args.production)
    # Only model-backed providers take a checkpoint; box_mask is model-free.
    seg_cfg = {"checkpoint_path": args.checkpoint} if segmenter != "box_mask" else {}
    providers = {
        "detector": get_detector(detector, production=args.production, **_detector_cfg(args, detector)),
        "segmenter": get_segmenter(segmenter, production=args.production, **seg_cfg),
        "depth": get_depth_estimator(
            depth, production=args.production, checkpoint_path=args.checkpoint
        ),
    }
    intr = {
        "exif_focal_px": exif_focal_px(args.path),
        "fallback_fov_deg": args.fov_deg,
    }

    if args.debug:
        # Build the cloud once; save artifacts; measure from the same cloud.
        cloud = build_masked_cloud(image, **providers, **intr, release_models=args.low_memory)
        outcome = measure_from_cloud(cloud) if isinstance(cloud, MaskedCloud) else cloud
        payload = {"input": args.path, **outcome.to_dict()}
        out_dir = os.environ.get("MEASUREX_VISION_OUTPUT_DIR", "./outputs")
        if isinstance(cloud, MaskedCloud):
            _save_debug_artifacts(out_dir, image, cloud, payload)
    else:
        outcome = build_measurement(image, **providers, **intr, release_models=args.low_memory)
        payload = {"input": args.path, **outcome.to_dict()}

    print(json.dumps(payload, indent=2))
    return 0 if isinstance(outcome, MeasurementSuccess) else 2


def _save_debug_artifacts(out_dir: str, image, cloud, payload: dict) -> None:
    from .visualization import save_cloud_artifacts, save_depth_artifacts

    os.makedirs(out_dir, exist_ok=True)
    save_depth_artifacts(out_dir, image, cloud.depth, mask=cloud.mask)
    save_cloud_artifacts(
        out_dir, image, cloud.mask, cloud.object_points_m,
        bbox_xyxy=cloud.detection.bbox_xyxy, diagnostics=cloud.diagnostics.to_dict(),
    )
    with open(os.path.join(out_dir, "measurement.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


def _run_video(args) -> int:
    from .contracts import MeasurementSuccess
    from .depth import get_depth_estimator
    from .detection import get_detector
    from .io import sample_frames
    from .pipeline import build_measurement_video
    from .segmentation import get_segmenter

    frames = sample_frames(args.path, max_frames=args.max_frames)
    detector, segmenter, depth = _detector_name(args), _segmenter_name(args), _depth_provider(args)
    _print_resolved(detector, segmenter, depth, args.production)
    seg_cfg = {"checkpoint_path": args.checkpoint} if segmenter != "box_mask" else {}
    outcome = build_measurement_video(
        frames,
        detector=get_detector(detector, production=args.production, **_detector_cfg(args, detector)),
        segmenter=get_segmenter(segmenter, production=args.production, **seg_cfg),
        depth=get_depth_estimator(
            depth, production=args.production, checkpoint_path=args.checkpoint
        ),
        fallback_fov_deg=args.fov_deg,
        release_models=args.low_memory,
    )
    payload = {"input": args.path, "capture_type": "video", **outcome.to_dict()}
    if args.debug:
        out_dir = os.environ.get("MEASUREX_VISION_OUTPUT_DIR", "./outputs")
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "measurement.json"), "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
    print(json.dumps(payload, indent=2))
    return 0 if isinstance(outcome, MeasurementSuccess) else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="measurex-vision",
        description="MeasureX camera-only shipment dimensioning (research POC).",
    )
    parser.add_argument("--version", action="version", version=f"measurex-vision {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="{image,video}")

    p_image = sub.add_parser("image", help="single-image L/W/H measurement")
    p_image.add_argument("path", help="path to the image file")
    p_image.add_argument("--detector", default=None, help="detector (default: central_candidate; grounding_dino with --production)")
    p_image.add_argument("--segmenter", default=None, help="segmenter (default: sam2)")
    p_image.add_argument("--provider", default=None, help="depth provider (default: depth_pro, or depth_anything_v2 with --production)")
    p_image.add_argument("--checkpoint", default=None, help="model checkpoint path (else env/default)")
    p_image.add_argument("--production", action="store_true", help="resolve the approved production stack (GDINO/SAM2/DA-V2) and refuse any non-production-approved model")
    p_image.add_argument("--fov-deg", type=float, default=None, help="fallback horizontal FOV when focal is unknown")
    p_image.add_argument("--debug", action="store_true", help="save debug artifacts")
    p_image.add_argument("--low-memory", action="store_true", help="free each model after its stage (small GPUs)")
    p_image.add_argument("--box-threshold", type=float, default=0.35, help="grounding_dino box confidence (default: 0.35)")
    p_image.add_argument("--prompt", default=None, help="grounding_dino text prompt (default: shipment prompt)")

    p_video = sub.add_parser("video", help="stabilized measurement from a short MP4/MOV video")
    p_video.add_argument("path", help="path to the video file")
    p_video.add_argument("--detector", default=None, help="detector (default: central_candidate; grounding_dino with --production)")
    p_video.add_argument("--segmenter", default=None, help="segmenter (default: sam2)")
    p_video.add_argument("--provider", default=None, help="depth provider (default: depth_pro, or depth_anything_v2 with --production)")
    p_video.add_argument("--checkpoint", default=None, help="model checkpoint path (else env/default)")
    p_video.add_argument("--production", action="store_true", help="resolve the approved production stack (GDINO/SAM2/DA-V2) and refuse any non-production-approved model")
    p_video.add_argument("--fov-deg", type=float, default=None, help="fallback horizontal FOV when focal is unknown")
    p_video.add_argument("--max-frames", type=int, default=8, help="frames to sample (default: 8)")
    p_video.add_argument("--debug", action="store_true", help="save measurement.json")
    p_video.add_argument("--low-memory", action="store_true", help="free each model after its stage (small GPUs)")
    p_video.add_argument("--box-threshold", type=float, default=0.35, help="grounding_dino box confidence (default: 0.35)")
    p_video.add_argument("--prompt", default=None, help="grounding_dino text prompt (default: shipment prompt)")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "image":
        return _run_image(args)
    if args.command == "video":
        return _run_video(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
