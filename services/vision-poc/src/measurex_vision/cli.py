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


def _run_image(path: str, provider: str, checkpoint: str | None, debug: bool) -> int:
    from .depth import get_depth_estimator
    from .io import load_image

    image = load_image(path)
    estimator = get_depth_estimator(provider, checkpoint_path=checkpoint)
    depth = estimator.estimate(image)

    result = {
        "stage": "depth",
        "input": path,
        "provider": provider,
        "diagnostics": {
            "focal_px": depth.focal_px,
            "valid_ratio": depth.valid_ratio,
            "version": depth.version,
            "depth_shape": list(depth.depth_m.shape),
        },
        "measurement": _PENDING,  # L/W/H arrives once geometry is wired
    }
    if debug:
        from .visualization import save_depth_artifacts

        out_dir = os.environ.get("MEASUREX_VISION_OUTPUT_DIR", "./outputs")
        result["artifacts"] = save_depth_artifacts(out_dir, image, depth)
    print(json.dumps(result, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="measurex-vision",
        description="MeasureX camera-only shipment dimensioning (research POC).",
    )
    parser.add_argument("--version", action="version", version=f"measurex-vision {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="{image,video}")

    p_image = sub.add_parser("image", help="run depth on a single JPG/PNG image")
    p_image.add_argument("path", help="path to the image file")
    p_image.add_argument("--provider", default="depth_pro", help="depth provider (default: depth_pro)")
    p_image.add_argument("--checkpoint", default=None, help="model checkpoint path (else env/default)")
    p_image.add_argument("--debug", action="store_true", help="save depth debug artifacts")

    p_video = sub.add_parser("video", help="measure from a short MP4/MOV video")
    p_video.add_argument("path", help="path to the video file")
    p_video.add_argument("--debug", action="store_true", help="save intermediate debug artifacts")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "image":
        return _run_image(args.path, args.provider, args.checkpoint, args.debug)
    if args.command == "video":
        print(json.dumps({**_PENDING, "input": args.path, "capture_type": "video"}, indent=2))
        return 2
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
