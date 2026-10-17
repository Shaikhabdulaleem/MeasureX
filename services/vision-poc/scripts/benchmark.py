"""Run or re-evaluate the MeasureX vision benchmark.

Live inference (requires the model/vision extras and benchmark media):

    python scripts/benchmark.py data/benchmark/manifest.csv \
        --false-success-tolerance-pct 10

CI/offline evaluation from one engine-result JSON object per JSONL line:

    python scripts/benchmark.py data/benchmark/manifest.csv \
        --predictions recorded-results.jsonl --false-success-tolerance-pct 10
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

from measurex_vision.benchmark import (
    BenchmarkSample,
    evaluate_samples,
    load_manifest,
    load_predictions,
    run_manifest,
    write_report,
)


def _build_live_runner(args: argparse.Namespace):
    from measurex_vision.depth import get_depth_estimator
    from measurex_vision.detection import get_detector
    from measurex_vision.io import load_image, sample_frames
    from measurex_vision.pipeline import build_measurement, build_measurement_video
    from measurex_vision.segmentation import get_segmenter

    segmenter_config = (
        {"checkpoint_path": args.checkpoint} if args.segmenter != "box_mask" else {}
    )
    detector = get_detector(args.detector)
    segmenter = get_segmenter(args.segmenter, **segmenter_config)
    depth = get_depth_estimator(args.provider, checkpoint_path=args.checkpoint)

    def run(sample: BenchmarkSample, media_path: Path):
        if not media_path.is_file():
            raise FileNotFoundError(f"media for {sample.sample_id!r} not found: {media_path}")
        print(f"[{sample.sample_id}] {sample.capture_type}: {media_path}", file=sys.stderr)
        started = perf_counter()
        if sample.capture_type == "image":
            result = build_measurement(
                load_image(str(media_path)),
                detector=detector,
                segmenter=segmenter,
                depth=depth,
            )
        else:
            result = build_measurement_video(
                sample_frames(str(media_path), max_frames=args.max_frames),
                detector=detector,
                segmenter=segmenter,
                depth=depth,
            )
        return result, (perf_counter() - started) * 1000.0

    return run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the MeasureX manifest benchmark and generate reproducible reports."
    )
    parser.add_argument("manifest", help="path to data/benchmark/manifest.csv")
    parser.add_argument(
        "--output-dir", default="outputs/benchmark", help="report directory (default: outputs/benchmark)"
    )
    parser.add_argument(
        "--false-success-tolerance-pct",
        type=float,
        required=True,
        help="maximum allowed error for every dimension; intentionally has no default",
    )
    parser.add_argument(
        "--predictions",
        help="evaluate JSONL engine outcomes instead of running model inference",
    )
    parser.add_argument("--detector", default="central_candidate")
    parser.add_argument("--segmenter", default="sam2")
    parser.add_argument("--provider", default="depth_pro")
    parser.add_argument("--checkpoint", default=None)
    parser.add_argument("--max-frames", type=int, default=8)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest = Path(args.manifest).resolve()
        samples = load_manifest(manifest)
        if args.predictions:
            records = evaluate_samples(
                samples,
                load_predictions(args.predictions),
                false_success_tolerance_pct=args.false_success_tolerance_pct,
            )
        else:
            records = run_manifest(
                samples,
                manifest.parent,
                _build_live_runner(args),
                false_success_tolerance_pct=args.false_success_tolerance_pct,
            )
        output_dir = Path(args.output_dir).resolve()
        summary = write_report(
            records,
            output_dir,
            false_success_tolerance_pct=args.false_success_tolerance_pct,
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"benchmark failed: {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "sample_count": summary["sample_count"],
                "success_rate": summary["success_rate"],
                "false_success_rate": summary["false_success"]["rate_among_successes"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
