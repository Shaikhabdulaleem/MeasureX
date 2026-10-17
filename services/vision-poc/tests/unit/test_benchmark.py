"""M5 benchmark harness tests — pure, with no codecs or model weights."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from measurex_vision.benchmark import (
    BenchmarkSample,
    evaluate_samples,
    load_manifest,
    summarize,
    write_report,
)
from measurex_vision.contracts import (
    Confidence,
    Dimensions,
    FailureCode,
    MeasurementFailure,
    MeasurementSuccess,
)


def _sample(
    sample_id: str,
    *,
    object_id: str = "BOX_001",
    category: str = "small",
    phone: str = "phone_a",
    capture_type: str = "image",
) -> BenchmarkSample:
    return BenchmarkSample(
        sample_id=sample_id,
        object_id=object_id,
        category=category,
        phone_model=phone,
        capture_type=capture_type,
        file_path=f"{sample_id}.jpg",
        gt_length_mm=400,
        gt_width_mm=300,
        gt_height_mm=200,
        lighting="warehouse",
        distance_band="near",
        notes="",
    )


def _success(length: int, width: int, height: int, confidence: float = 0.7):
    return MeasurementSuccess(
        dimensions=Dimensions(length, width, height),
        confidence=Confidence.from_score(confidence),
        timing_ms={"depth": 20.0, "total": 30.0},
    )


def test_manifest_loads_integer_ground_truth(tmp_path: Path):
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "sample_id,object_id,category,phone_model,capture_type,file_path,"
        "gt_length_mm,gt_width_mm,gt_height_mm,lighting,distance_band,notes\n"
        "S1,B1,small,phone_a,image,objects/B1/a.jpg,400,300,200,bright,near,ok\n",
        encoding="utf-8",
    )

    samples = load_manifest(manifest)

    assert samples == [
        BenchmarkSample(
            sample_id="S1",
            object_id="B1",
            category="small",
            phone_model="phone_a",
            capture_type="image",
            file_path="objects/B1/a.jpg",
            gt_length_mm=400,
            gt_width_mm=300,
            gt_height_mm=200,
            lighting="bright",
            distance_band="near",
            notes="ok",
        )
    ]


@pytest.mark.parametrize(
    "row,error",
    [
        ("S1,B1,small,p,still,a.jpg,400,300,200,bright,near,", "capture_type"),
        ("S1,B1,small,p,image,a.jpg,300,400,200,bright,near,", "must be >="),
        ("S1,B1,small,p,image,a.jpg,zero,300,200,bright,near,", "must be an integer"),
    ],
)
def test_manifest_rejects_invalid_rows(tmp_path: Path, row: str, error: str):
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "sample_id,object_id,category,phone_model,capture_type,file_path,"
        "gt_length_mm,gt_width_mm,gt_height_mm,lighting,distance_band,notes\n"
        f"{row}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=error):
        load_manifest(manifest)


def test_evaluation_calculates_errors_failures_false_success_and_repeatability():
    samples = [
        _sample("S1"),
        _sample("S2", capture_type="video"),
        _sample("S3", object_id="BOX_002", category="medium", phone="phone_b"),
    ]
    records = evaluate_samples(
        samples,
        {
            "S1": _success(410, 300, 190),
            "S2": _success(440, 300, 200),
            "S3": MeasurementFailure(failure_code=FailureCode.DEPTH_INVALID),
        },
        false_success_tolerance_pct=5.0,
    )
    summary = summarize(records, false_success_tolerance_pct=5.0)

    assert records[0]["abs_error_length_mm"] == 10
    assert records[0]["pct_error_height"] == 5.0
    assert records[0]["false_success"] is False
    assert records[1]["false_success"] is True
    assert summary["sample_count"] == 3
    assert summary["success_rate"] == pytest.approx(2 / 3)
    assert summary["explicit_failure_rate"] == pytest.approx(1 / 3)
    assert summary["false_success"]["rate_among_successes"] == 0.5
    assert summary["failure_code_counts"] == {"depth_invalid": 1}
    assert summary["errors"]["dimensions"]["length"]["mae_mm"] == 25.0
    assert summary["errors"]["dimensions"]["length"]["p90_absolute_error_mm"] == 37.0
    assert summary["repeatability"]["by_object"]["BOX_001"]["length_spread_mm"] == 30
    assert set(summary["breakdowns"]["capture_type"]) == {"image", "video"}


def test_predictions_must_match_manifest_exactly():
    with pytest.raises(ValueError, match="missing: S2"):
        evaluate_samples(
            [_sample("S1"), _sample("S2")],
            {"S1": _success(400, 300, 200)},
            false_success_tolerance_pct=10,
        )


def test_report_writes_machine_readable_outputs_and_all_required_charts(tmp_path: Path):
    records = evaluate_samples(
        [_sample("S1"), _sample("S2", capture_type="video")],
        {
            "S1": _success(410, 295, 205),
            "S2": MeasurementFailure(failure_code=FailureCode.TEMPORAL_INSTABILITY),
        },
        false_success_tolerance_pct=10,
    )

    write_report(records, tmp_path, false_success_tolerance_pct=10)

    with (tmp_path / "results.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert [row["sample_id"] for row in rows] == ["S1", "S2"]
    assert rows[0]["success"] == "true"
    assert rows[1]["failure_code"] == "temporal_instability"
    assert summary["sample_count"] == 2

    charts = {
        "dimension_error_distribution.svg",
        "error_by_object_size.svg",
        "error_by_phone_model.svg",
        "error_by_lighting.svg",
        "error_by_confidence_level.svg",
        "single_vs_multi_frame.svg",
        "failure_code_counts.svg",
    }
    assert charts <= {path.name for path in tmp_path.glob("*.svg")}
    assert all((tmp_path / name).read_text(encoding="utf-8").startswith("<svg") for name in charts)
