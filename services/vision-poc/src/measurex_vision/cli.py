"""Command-line entry point for the vision POC.

Milestone 0 scaffold: ``--help`` and the ``image`` / ``video`` subcommands exist
and parse, but the measurement pipeline is not wired yet (no models integrated).
The subcommands emit a structured JSON notice and exit non-zero so nothing
mistakes the scaffold for a working measurement.

    python -m measurex_vision.cli --help
    python -m measurex_vision.cli image path/to/image.jpg --debug
    python -m measurex_vision.cli video path/to/video.mp4 --debug
"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__

_NOT_IMPLEMENTED = {
    "status": "not_implemented",
    "milestone": "M0-scaffold",
    "message": "Measurement pipeline is not integrated yet (no AI models). "
    "See services/vision-poc/CLAUDE.md 'First task sequence'.",
}


def _notice(source: str, kind: str, debug: bool) -> int:
    payload = {**_NOT_IMPLEMENTED, "input": source, "capture_type": kind, "debug": debug}
    print(json.dumps(payload, indent=2))
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="measurex-vision",
        description="MeasureX camera-only shipment dimensioning (research POC).",
    )
    parser.add_argument("--version", action="version", version=f"measurex-vision {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="{image,video}")

    p_image = sub.add_parser("image", help="measure from a single JPG/PNG image")
    p_image.add_argument("path", help="path to the image file")
    p_image.add_argument("--debug", action="store_true", help="save intermediate debug artifacts")

    p_video = sub.add_parser("video", help="measure from a short MP4/MOV video")
    p_video.add_argument("path", help="path to the video file")
    p_video.add_argument("--debug", action="store_true", help="save intermediate debug artifacts")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command in ("image", "video"):
        return _notice(args.path, args.command, args.debug)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
