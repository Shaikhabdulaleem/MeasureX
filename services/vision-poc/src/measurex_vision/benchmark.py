"""Pure benchmark evaluation and report generation for the vision POC.

The model runner lives in ``scripts/benchmark.py``.  This module deliberately
depends only on the standard library so recorded results can be evaluated in CI
without codecs, model packages, checkpoints, or benchmark media.
"""

from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from html import escape
from pathlib import Path
from statistics import fmean, median
from typing import Any

from .contracts import MeasurementResult

REQUIRED_MANIFEST_COLUMNS = (
    "sample_id",
    "object_id",
    "category",
    "phone_model",
    "capture_type",
    "file_path",
    "gt_length_mm",
    "gt_width_mm",
    "gt_height_mm",
    "lighting",
    "distance_band",
    "notes",
)

_DIMENSIONS = ("length", "width", "height")
_RESULT_COLUMNS = (
    *REQUIRED_MANIFEST_COLUMNS,
    "success",
    "pred_length_mm",
    "pred_width_mm",
    "pred_height_mm",
    "abs_error_length_mm",
    "abs_error_width_mm",
    "abs_error_height_mm",
    "pct_error_length",
    "pct_error_width",
    "pct_error_height",
    "gt_cbm",
    "pred_cbm",
    "abs_error_cbm",
    "pct_error_cbm",
    "confidence",
    "confidence_level",
    "method",
    "model_versions_json",
    "diagnostics_json",
    "failure_code",
    "false_success",
    "total_runtime_ms",
    "timing_ms_json",
)


@dataclass(frozen=True)
class BenchmarkSample:
    sample_id: str
    object_id: str
    category: str
    phone_model: str
    capture_type: str
    file_path: str
    gt_length_mm: int
    gt_width_mm: int
    gt_height_mm: int
    lighting: str
    distance_band: str
    notes: str

    def to_dict(self) -> dict[str, str | int]:
        return {name: getattr(self, name) for name in REQUIRED_MANIFEST_COLUMNS}


def load_manifest(path: str | Path) -> list[BenchmarkSample]:
    """Load and strictly validate the benchmark manifest."""
    manifest_path = Path(path)
    with manifest_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = [name for name in REQUIRED_MANIFEST_COLUMNS if name not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"manifest is missing required columns: {', '.join(missing)}")

        samples: list[BenchmarkSample] = []
        seen_ids: set[str] = set()
        for line_number, row in enumerate(reader, start=2):
            values = {name: (row.get(name) or "").strip() for name in REQUIRED_MANIFEST_COLUMNS}
            sample_id = values["sample_id"]
            if not sample_id:
                raise ValueError(f"manifest row {line_number}: sample_id is required")
            if sample_id in seen_ids:
                raise ValueError(f"manifest row {line_number}: duplicate sample_id {sample_id!r}")
            seen_ids.add(sample_id)
            for column in (
                "object_id",
                "category",
                "phone_model",
                "file_path",
                "lighting",
                "distance_band",
            ):
                if not values[column]:
                    raise ValueError(f"manifest row {line_number}: {column} is required")

            capture_type = values["capture_type"].lower()
            if capture_type not in {"image", "video"}:
                raise ValueError(
                    f"manifest row {line_number}: capture_type must be image or video"
                )
            ground_truth: dict[str, int] = {}
            for dimension in _DIMENSIONS:
                column = f"gt_{dimension}_mm"
                try:
                    ground_truth[column] = int(values[column])
                except ValueError as exc:
                    raise ValueError(
                        f"manifest row {line_number}: {column} must be an integer"
                    ) from exc
                if ground_truth[column] <= 0:
                    raise ValueError(f"manifest row {line_number}: {column} must be > 0")
            if ground_truth["gt_length_mm"] < ground_truth["gt_width_mm"]:
                raise ValueError(
                    f"manifest row {line_number}: gt_length_mm must be >= gt_width_mm"
                )
            samples.append(
                BenchmarkSample(
                    **{
                        **values,
                        **ground_truth,
                        "capture_type": capture_type,
                    }
                )
            )
    if not samples:
        raise ValueError("manifest contains no samples")
    return samples


def _as_payload(result: MeasurementResult | Mapping[str, Any]) -> dict[str, Any]:
    return result.to_dict() if hasattr(result, "to_dict") else dict(result)


def evaluate_result(
    sample: BenchmarkSample,
    result: MeasurementResult | Mapping[str, Any],
    *,
    false_success_tolerance_pct: float,
    total_runtime_ms: float | None = None,
) -> dict[str, Any]:
    """Join one engine outcome to ground truth and calculate sample metrics."""
    if false_success_tolerance_pct <= 0 or not math.isfinite(false_success_tolerance_pct):
        raise ValueError("false-success tolerance must be a finite value > 0")

    payload = _as_payload(result)
    success = payload.get("success")
    if not isinstance(success, bool):
        raise TypeError(f"result for {sample.sample_id!r} must contain boolean success")

    timing = payload.get("timing_ms") or {}
    if not isinstance(timing, Mapping):
        raise TypeError(f"result for {sample.sample_id!r} has invalid timing_ms")
    numeric_timing = {
        str(name): float(value)
        for name, value in timing.items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }
    measured_total = total_runtime_ms
    if measured_total is None and "total" in numeric_timing:
        measured_total = numeric_timing["total"]
    gt_volume_mm3 = sample.gt_length_mm * sample.gt_width_mm * sample.gt_height_mm

    record: dict[str, Any] = {
        **sample.to_dict(),
        "success": success,
        "confidence": payload.get("confidence", ""),
        "confidence_level": payload.get("confidence_level", "failed"),
        "method": payload.get("method", ""),
        "model_versions": payload.get("model_versions") or {},
        "diagnostics": payload.get("diagnostics") or {},
        "failure_code": payload.get("failure_code", ""),
        "false_success": False,
        "gt_cbm": gt_volume_mm3 / 1_000_000_000,
        "total_runtime_ms": measured_total,
        "timing_ms": numeric_timing,
    }
    if not success:
        return record

    dimensions = payload.get("dimensions")
    if not isinstance(dimensions, Mapping):
        raise TypeError(f"successful result for {sample.sample_id!r} is missing dimensions")

    percentage_errors: list[float] = []
    for dimension in _DIMENSIONS:
        predicted = dimensions.get(f"{dimension}_mm")
        if not isinstance(predicted, int) or isinstance(predicted, bool) or predicted < 0:
            raise ValueError(
                f"successful result for {sample.sample_id!r} has invalid {dimension}_mm"
            )
        ground_truth = getattr(sample, f"gt_{dimension}_mm")
        absolute_error = abs(predicted - ground_truth)
        percentage_error = absolute_error / ground_truth * 100.0
        record[f"pred_{dimension}_mm"] = predicted
        record[f"abs_error_{dimension}_mm"] = absolute_error
        record[f"pct_error_{dimension}"] = percentage_error
        percentage_errors.append(percentage_error)

    predicted_volume_mm3 = math.prod(record[f"pred_{name}_mm"] for name in _DIMENSIONS)
    absolute_volume_error_mm3 = abs(predicted_volume_mm3 - gt_volume_mm3)
    record.update(
        {
            "gt_cbm": gt_volume_mm3 / 1_000_000_000,
            "pred_cbm": predicted_volume_mm3 / 1_000_000_000,
            "abs_error_cbm": absolute_volume_error_mm3 / 1_000_000_000,
            "pct_error_cbm": absolute_volume_error_mm3 / gt_volume_mm3 * 100.0,
            "false_success": max(percentage_errors) > false_success_tolerance_pct,
        }
    )
    return record


def evaluate_samples(
    samples: Iterable[BenchmarkSample],
    results_by_sample_id: Mapping[str, MeasurementResult | Mapping[str, Any]],
    *,
    false_success_tolerance_pct: float,
) -> list[dict[str, Any]]:
    """Evaluate recorded outcomes, requiring exactly one result per manifest sample."""
    sample_list = list(samples)
    expected = {sample.sample_id for sample in sample_list}
    missing = sorted(expected - results_by_sample_id.keys())
    extra = sorted(results_by_sample_id.keys() - expected)
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if extra:
            details.append(f"unknown: {', '.join(extra)}")
        raise ValueError("prediction sample IDs do not match manifest (" + "; ".join(details) + ")")
    return [
        evaluate_result(
            sample,
            results_by_sample_id[sample.sample_id],
            false_success_tolerance_pct=false_success_tolerance_pct,
        )
        for sample in sample_list
    ]


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percentile
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return float(ordered[lower])
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower))


def _error_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [record for record in records if record["success"]]
    dimensions: dict[str, Any] = {}
    for dimension in _DIMENSIONS:
        absolute = [float(row[f"abs_error_{dimension}_mm"]) for row in successful]
        percentage = [float(row[f"pct_error_{dimension}"]) for row in successful]
        dimensions[dimension] = {
            "mae_mm": fmean(absolute) if absolute else None,
            "median_absolute_error_mm": median(absolute) if absolute else None,
            "p90_absolute_error_mm": _percentile(absolute, 0.9),
            "mean_percentage_error": fmean(percentage) if percentage else None,
        }
    cbm_absolute = [float(row["abs_error_cbm"]) for row in successful]
    cbm_percentage = [float(row["pct_error_cbm"]) for row in successful]
    return {
        "dimensions": dimensions,
        "cbm": {
            "mae_cbm": fmean(cbm_absolute) if cbm_absolute else None,
            "median_absolute_error_cbm": median(cbm_absolute) if cbm_absolute else None,
            "p90_absolute_error_cbm": _percentile(cbm_absolute, 0.9),
            "mean_percentage_error": fmean(cbm_percentage) if cbm_percentage else None,
        },
    }


def _group_summary(records: list[dict[str, Any]], key: str) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[str(record.get(key) or "unknown")].append(record)
    output: dict[str, Any] = {}
    for name in sorted(groups):
        rows = groups[name]
        successful = [row for row in rows if row["success"]]
        output[name] = {
            "sample_count": len(rows),
            "success_count": len(successful),
            "success_rate": len(successful) / len(rows),
            "errors": _error_metrics(rows),
        }
    return output


def _repeatability(records: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record["success"]:
            groups[str(record["object_id"])].append(record)
    by_object: dict[str, Any] = {}
    for object_id, rows in sorted(groups.items()):
        spreads = {}
        for dimension in _DIMENSIONS:
            values = [int(row[f"pred_{dimension}_mm"]) for row in rows]
            spreads[f"{dimension}_spread_mm"] = (
                max(values) - min(values) if len(values) >= 2 else None
            )
        by_object[object_id] = {"successful_samples": len(rows), **spreads}
    return {"by_object": by_object}


def summarize(
    records: list[dict[str, Any]], *, false_success_tolerance_pct: float
) -> dict[str, Any]:
    """Aggregate sample results into the machine-readable benchmark summary."""
    total = len(records)
    successful = [record for record in records if record["success"]]
    failures = [record for record in records if not record["success"]]
    false_successes = [record for record in successful if record["false_success"]]
    timings: dict[str, list[float]] = defaultdict(list)
    for record in records:
        if record.get("total_runtime_ms") is not None:
            timings["total"].append(float(record["total_runtime_ms"]))
        for stage, value in record.get("timing_ms", {}).items():
            if stage != "total":
                timings[stage].append(float(value))

    return {
        "sample_count": total,
        "success_count": len(successful),
        "explicit_failure_count": len(failures),
        "success_rate": len(successful) / total if total else 0.0,
        "explicit_failure_rate": len(failures) / total if total else 0.0,
        "false_success": {
            "tolerance_pct": false_success_tolerance_pct,
            "rule": "max_dimension_percentage_error > tolerance_pct",
            "count": len(false_successes),
            "rate_among_successes": (
                len(false_successes) / len(successful) if successful else 0.0
            ),
            "rate_among_all_samples": len(false_successes) / total if total else 0.0,
        },
        "errors": _error_metrics(records),
        "failure_code_counts": dict(
            sorted(Counter(str(row.get("failure_code") or "unknown") for row in failures).items())
        ),
        "methods": dict(
            sorted(Counter(str(row["method"]) for row in successful if row.get("method")).items())
        ),
        "model_versions": [
            json.loads(serialized)
            for serialized in sorted(
                {
                    json.dumps(row["model_versions"], sort_keys=True, separators=(",", ":"))
                    for row in successful
                    if row.get("model_versions")
                }
            )
        ],
        "repeatability": _repeatability(records),
        "runtime_ms": {
            stage: {
                "mean": fmean(values),
                "median": median(values),
                "p90": _percentile(values, 0.9),
                "sample_count": len(values),
            }
            for stage, values in sorted(timings.items())
        },
        "breakdowns": {
            "object_size": _group_summary(records, "category"),
            "phone_model": _group_summary(records, "phone_model"),
            "lighting": _group_summary(records, "lighting"),
            "confidence_level": _group_summary(records, "confidence_level"),
            "capture_type": _group_summary(records, "capture_type"),
        },
    }


def _csv_value(record: dict[str, Any], column: str) -> Any:
    json_fields = {
        "timing_ms_json": "timing_ms",
        "model_versions_json": "model_versions",
        "diagnostics_json": "diagnostics",
    }
    if column in json_fields:
        return json.dumps(
            record.get(json_fields[column], {}), sort_keys=True, separators=(",", ":")
        )
    value = record.get(column, "")
    if isinstance(value, float):
        return f"{value:.6f}"
    if isinstance(value, bool):
        return str(value).lower()
    return value


def _write_bar_chart(path: Path, title: str, values: Mapping[str, float | int | None]) -> None:
    valid = [(str(label), float(value)) for label, value in values.items() if value is not None]
    width, height = 760, 420
    left, top, bottom = 80, 55, 85
    chart_width, chart_height = width - left - 30, height - top - bottom
    maximum = max((value for _, value in valid), default=0.0)
    scale = chart_height / maximum if maximum > 0 else 0.0
    bar_width = chart_width / max(1, len(valid)) * 0.68
    gap = chart_width / max(1, len(valid))
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#fff"/>',
        f'<text x="{width / 2}" y="30" text-anchor="middle" font-family="sans-serif" font-size="18">{escape(title)}</text>',
        f'<line x1="{left}" y1="{top + chart_height}" x2="{left + chart_width}" y2="{top + chart_height}" stroke="#333"/>',
    ]
    if not valid:
        parts.append(
            f'<text x="{width / 2}" y="{height / 2}" text-anchor="middle" font-family="sans-serif">No data</text>'
        )
    for index, (label, value) in enumerate(valid):
        x = left + index * gap + (gap - bar_width) / 2
        bar_height = value * scale
        y = top + chart_height - bar_height
        parts.extend(
            [
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_width:.2f}" height="{bar_height:.2f}" fill="#2563eb"/>',
                f'<text x="{x + bar_width / 2:.2f}" y="{max(top + 14, y - 6):.2f}" text-anchor="middle" font-family="sans-serif" font-size="12">{value:.2f}</text>',
                f'<text x="{x + bar_width / 2:.2f}" y="{top + chart_height + 22}" text-anchor="middle" font-family="sans-serif" font-size="11">{escape(label[:22])}</text>',
            ]
        )
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def _mean_max_dimension_error(rows: list[dict[str, Any]]) -> float | None:
    values = [
        max(float(row[f"pct_error_{name}"]) for name in _DIMENSIONS)
        for row in rows
        if row["success"]
    ]
    return fmean(values) if values else None


def _chart_breakdown(
    output_dir: Path, records: list[dict[str, Any]], key: str, filename: str, title: str
) -> None:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[str(record.get(key) or "unknown")].append(record)
    _write_bar_chart(
        output_dir / filename,
        title,
        {name: _mean_max_dimension_error(rows) for name, rows in sorted(grouped.items())},
    )


def write_report(
    records: list[dict[str, Any]],
    output_dir: str | Path,
    *,
    false_success_tolerance_pct: float,
) -> dict[str, Any]:
    """Write results.csv, summary.json, and the required SVG charts."""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    with (destination / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_RESULT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow({column: _csv_value(record, column) for column in _RESULT_COLUMNS})

    summary = summarize(records, false_success_tolerance_pct=false_success_tolerance_pct)
    (destination / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    dimension_metrics = summary["errors"]["dimensions"]
    distribution_values = {
        f"{name} MAE": metrics["mae_mm"]
        for name, metrics in dimension_metrics.items()
    }
    distribution_values.update(
        {
            f"{name} median": metrics["median_absolute_error_mm"]
            for name, metrics in dimension_metrics.items()
        }
    )
    distribution_values.update(
        {
            f"{name} P90": metrics["p90_absolute_error_mm"]
            for name, metrics in dimension_metrics.items()
        }
    )
    _write_bar_chart(
        destination / "dimension_error_distribution.svg",
        "Dimension absolute error distribution (mm)",
        distribution_values,
    )
    _chart_breakdown(
        destination, records, "category", "error_by_object_size.svg", "Error by object size (%)"
    )
    _chart_breakdown(
        destination, records, "phone_model", "error_by_phone_model.svg", "Error by phone model (%)"
    )
    _chart_breakdown(
        destination, records, "lighting", "error_by_lighting.svg", "Error by lighting (%)"
    )
    _chart_breakdown(
        destination,
        records,
        "confidence_level",
        "error_by_confidence_level.svg",
        "Error by confidence level (%)",
    )
    _chart_breakdown(
        destination,
        records,
        "capture_type",
        "single_vs_multi_frame.svg",
        "Single-frame vs multi-frame error (%)",
    )
    _write_bar_chart(
        destination / "failure_code_counts.svg",
        "Failure-code counts",
        summary["failure_code_counts"],
    )
    return summary


def load_predictions(path: str | Path) -> dict[str, dict[str, Any]]:
    """Load JSONL records containing sample_id plus an engine result payload."""
    predictions: dict[str, dict[str, Any]] = {}
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict) or not isinstance(value.get("sample_id"), str):
                raise TypeError(f"predictions line {line_number}: sample_id is required")
            sample_id = value.pop("sample_id")
            if sample_id in predictions:
                raise ValueError(f"predictions line {line_number}: duplicate sample_id {sample_id!r}")
            predictions[sample_id] = value
    return predictions


MeasurementRunner = Callable[[BenchmarkSample, Path], tuple[MeasurementResult, float]]


def run_manifest(
    samples: Iterable[BenchmarkSample],
    manifest_dir: Path,
    runner: MeasurementRunner,
    *,
    false_success_tolerance_pct: float,
) -> list[dict[str, Any]]:
    """Run inference serially in manifest order and evaluate each outcome."""
    records = []
    for sample in samples:
        result, runtime_ms = runner(sample, manifest_dir / sample.file_path)
        records.append(
            evaluate_result(
                sample,
                result,
                false_success_tolerance_pct=false_success_tolerance_pct,
                total_runtime_ms=runtime_ms,
            )
        )
    return records
