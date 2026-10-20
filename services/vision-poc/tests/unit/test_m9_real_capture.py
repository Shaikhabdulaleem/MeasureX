"""M9 real-device capture: raw validation, 8-frame selection, strict-manifest
preparation, fit-run orchestration and the GT-only evaluator.

Everything runs offline with synthetic poses and precomputed masks — no model
downloads, no GPU, no network. The synthetic capture gives exact metric poses +
masks, so these tests exercise the geometry/plumbing, not model accuracy.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from measurex_vision.multiview.real_capture import (
    MIN_VIEW_COVERAGE_DEG,
    RawCaptureError,
    coverage_deg,
    evaluate_runs,
    load_raw_capture,
    run_capture,
    select_frames,
    validate_raw_capture,
)
from measurex_vision.multiview.schema import _object_locus
from measurex_vision.multiview.synthetic import synthetic_capture

# Load the standalone prepare script by path (not part of the package), mirroring
# the existing script-test convention (see test_m9_cuboid_proof.py).
_PREP = Path(__file__).resolve().parents[2] / "scripts" / "m9_prepare_real_capture.py"
_spec = importlib.util.spec_from_file_location("m9_prepare_real_capture", _PREP)
assert _spec and _spec.loader
prep = importlib.util.module_from_spec(_spec)
# Register before exec: dataclasses under `from __future__ import annotations`
# resolve their field annotations via sys.modules at class-creation time.
sys.modules["m9_prepare_real_capture"] = prep
_spec.loader.exec_module(prep)


# --------------------------------------------------------------------------- #
# Fixtures: build a real-shaped raw_capture.json on disk from a synthetic bundle.
# --------------------------------------------------------------------------- #

def _build_raw_dir(tmp: Path, *, n_views: int = 16, span: float = 140.0, with_plane: bool = True) -> Path:
    bundle, gt = synthetic_capture(
        length_m=0.345, width_m=0.290, height_m=0.245,
        n_views=n_views, continuous_sweep=True, azimuth_span_deg=span,
        gravity_world=(0.0, -1.0, 0.0),  # ARCore world: +Y up, gravity points -Y
        image_wh=(640, 480),
    )
    target = _object_locus(bundle.frames)
    (tmp / "frames").mkdir(parents=True, exist_ok=True)
    doc_frames = []
    for i, f in enumerate(bundle.frames):
        img_rel = f"frames/{f.frame_id}.png"
        _solid_png(tmp / img_rel, f.width, f.height)
        ts = 1_000_000_000 + i * 33_000_000  # ~30 FPS
        doc_frames.append({
            "frame_id": f.frame_id,
            "frame_timestamp_ns": ts,
            "image_timestamp_ns": ts,  # same observation
            "image": img_rel,
            "intrinsics": {
                "fx": f.intrinsics.fx, "fy": f.intrinsics.fy,
                "cx": f.intrinsics.cx, "cy": f.intrinsics.cy,
                "width": f.width, "height": f.height,
            },
            "T_world_from_camera": f.T_world_from_camera.tolist(),
            "tracking_state": "TRACKING",
            "guidance_angle_deg": 0.0,
            "camera_distance_to_target_m": 1.5,
        })
    doc = {
        "schema_version": 1,
        "capture_type": "m9_real_raw",
        "pose_source": "arcore",
        "pose_convention": "T_world_from_camera",
        "camera_convention": "opencv_x_right_y_down_z_forward",
        "units": "meters",
        "gravity_world": [0.0, -1.0, 0.0],
        "device": {"model": "SM-A165F", "manufacturer": "samsung"},
        "guidance_target_world": [float(x) for x in target],
        "frames": doc_frames,
    }
    if with_plane:
        doc["support_plane"] = bundle.support_plane
    path = tmp / "raw_capture.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    # Keep the masks around so prepare's mock segment_fn can hand them back.
    _spec_masks[path] = {f.frame_id: f.mask for f in bundle.frames}
    _spec_gt[path] = gt
    return path


_spec_masks: dict[Path, dict[str, np.ndarray]] = {}
_spec_gt: dict[Path, dict[str, int]] = {}


def _solid_png(path: Path, w: int, h: int) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.zeros((h, w, 3), dtype=np.uint8)).save(path)


# --------------------------------------------------------------------------- #
# Raw validation
# --------------------------------------------------------------------------- #

def test_valid_raw_capture_passes(tmp_path):
    raw = load_raw_capture(str(_build_raw_dir(tmp_path)))
    report = validate_raw_capture(raw, base_dir=str(tmp_path))
    assert report["ok"], [c for c in report["checks"] if not c["ok"]]
    assert report["view_coverage_deg"] >= MIN_VIEW_COVERAGE_DEG
    assert report["candidate_frames"] == 16


def test_raw_rejects_wrong_capture_type(tmp_path):
    p = _build_raw_dir(tmp_path)
    doc = json.loads(p.read_text())
    doc["capture_type"] = "something_else"
    p.write_text(json.dumps(doc))
    with pytest.raises(RawCaptureError):
        load_raw_capture(str(p))


def test_raw_rejects_invalid_pose(tmp_path):
    p = _build_raw_dir(tmp_path)
    doc = json.loads(p.read_text())
    doc["frames"][0]["T_world_from_camera"] = [[2, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    p.write_text(json.dumps(doc))
    report = validate_raw_capture(load_raw_capture(str(p)), base_dir=str(tmp_path))
    assert not report["ok"]
    assert any(c["check"] == "poses_valid" and not c["ok"] for c in report["checks"])


def test_raw_rejects_image_intrinsics_size_mismatch(tmp_path):
    p = _build_raw_dir(tmp_path)
    doc = json.loads(p.read_text())
    doc["frames"][0]["intrinsics"]["width"] = 999  # image is 640 wide
    p.write_text(json.dumps(doc))
    report = validate_raw_capture(load_raw_capture(str(p)), base_dir=str(tmp_path))
    assert any(c["check"] == "image_intrinsics_dims_agree" and not c["ok"] for c in report["checks"])


def test_raw_rejects_timestamp_mismatch(tmp_path):
    p = _build_raw_dir(tmp_path)
    doc = json.loads(p.read_text())
    doc["frames"][0]["image_timestamp_ns"] += 50_000_000  # 50 ms apart
    p.write_text(json.dumps(doc))
    report = validate_raw_capture(load_raw_capture(str(p)), base_dir=str(tmp_path))
    assert any(c["check"] == "timestamps_paired" and not c["ok"] for c in report["checks"])


def test_raw_rejects_non_tracking_frame(tmp_path):
    p = _build_raw_dir(tmp_path)
    doc = json.loads(p.read_text())
    doc["frames"][0]["tracking_state"] = "PAUSED"
    p.write_text(json.dumps(doc))
    report = validate_raw_capture(load_raw_capture(str(p)), base_dir=str(tmp_path))
    assert any(c["check"] == "tracking_all_tracking" and not c["ok"] for c in report["checks"])


def test_raw_support_plane_optional(tmp_path):
    raw = load_raw_capture(str(_build_raw_dir(tmp_path, with_plane=False)))
    report = validate_raw_capture(raw, base_dir=str(tmp_path))
    assert report["ok"]
    assert report["support_plane_present"] is False


# --------------------------------------------------------------------------- #
# Coverage + 8-frame selection
# --------------------------------------------------------------------------- #

def test_coverage_deg_arc_vs_full_ring():
    assert coverage_deg([0, 30, 60, 90, 120]) == pytest.approx(120.0, abs=1.0)
    ring = list(np.linspace(0, 360, 12, endpoint=False))
    assert coverage_deg(ring) >= 300.0  # near-full ring


def test_select_exactly_8_chronological(tmp_path):
    raw = load_raw_capture(str(_build_raw_dir(tmp_path, n_views=16, span=140.0)))
    sel = select_frames(raw, n=8)
    assert sel["ok"], sel.get("reason")
    assert len(sel["selected_frame_ids"]) == 8
    assert len(set(sel["selected_frame_ids"])) == 8  # no duplicates
    assert sel["coverage_deg"] >= MIN_VIEW_COVERAGE_DEG
    # Chronological: frame ids are zero-padded sequence numbers in capture order.
    ids = sel["selected_frame_ids"]
    assert ids == sorted(ids)


def test_select_fails_when_too_few_tracking(tmp_path):
    raw = load_raw_capture(str(_build_raw_dir(tmp_path, n_views=6)))
    sel = select_frames(raw, n=8)
    assert not sel["ok"]
    assert sel["selected_frame_ids"] == []


# --------------------------------------------------------------------------- #
# Prepare: strict manifest creation with precomputed (mock) masks — no models.
# --------------------------------------------------------------------------- #

def test_prepare_creates_loadable_strict_manifest(tmp_path):
    p = _build_raw_dir(tmp_path)
    raw = load_raw_capture(str(p))
    masks = _spec_masks[p]
    selected = select_frames(raw, n=8)["selected_frame_ids"]

    def seg(image, rf):
        return prep.FrameMask(rf.frame_id, masks[rf.frame_id], 0.95, (10.0, 10.0, 100.0, 100.0))

    out = tmp_path / "processed"
    report = prep.prepare_capture(
        raw, selected, seg, str(out), images_dir=str(tmp_path),
        load_image=lambda _p: np.zeros((480, 640, 3), dtype=np.uint8),
        write_overlay=None,
    )
    assert report["ok"], report["failures"]
    assert report["frames_segmented"] == 8
    # The produced manifest loads cleanly through the strict M9 contract.
    from measurex_vision.multiview.schema import load_bundle
    bundle = load_bundle(report["capture_json"])
    assert len(bundle.frames) == 8
    assert bundle.support_plane is not None


def test_prepare_records_typed_failure_not_fabricated_mask(tmp_path):
    p = _build_raw_dir(tmp_path)
    raw = load_raw_capture(str(p))
    masks = _spec_masks[p]
    selected = select_frames(raw, n=8)["selected_frame_ids"]
    empty = np.zeros_like(next(iter(masks.values())))

    def seg(image, rf):
        if rf.frame_id == selected[0]:
            return prep.FrameFailure(rf.frame_id, "no_target", "score below threshold")
        if rf.frame_id == selected[1]:
            return prep.FrameMask(rf.frame_id, empty, 0.9, (0.0, 0.0, 1.0, 1.0))  # empty -> mask gate
        return prep.FrameMask(rf.frame_id, masks[rf.frame_id], 0.95, (10.0, 10.0, 100.0, 100.0))

    out = tmp_path / "processed"
    report = prep.prepare_capture(
        raw, selected, seg, str(out), images_dir=str(tmp_path),
        load_image=lambda _p: np.zeros((480, 640, 3), dtype=np.uint8),
        write_overlay=None,
    )
    codes = {f["code"] for f in report["failures"]}
    assert "no_target" in codes
    assert report["frames_segmented"] == 6  # the two bad frames dropped, none fabricated


def test_assess_detections_gate():
    assert prep.assess_detections([0.1, 0.2]) == "no_target"
    assert prep.assess_detections([0.8, 0.78]) == "multiple_targets"
    assert prep.assess_detections([0.8, 0.2]) is None


# --------------------------------------------------------------------------- #
# Fit run (7-DOF + 6-DOF) — no GT anywhere in this path.
# --------------------------------------------------------------------------- #

def test_run_capture_has_no_ground_truth_parameter():
    import inspect

    params = set(inspect.signature(run_capture).parameters)
    assert "gt" not in params and "ground_truth" not in params


def test_run_capture_produces_both_configs(tmp_path):
    p = _build_raw_dir(tmp_path)
    raw = load_raw_capture(str(p))
    masks = _spec_masks[p]
    selected = select_frames(raw, n=8)["selected_frame_ids"]

    def seg(image, rf):
        return prep.FrameMask(rf.frame_id, masks[rf.frame_id], 0.95, (10.0, 10.0, 100.0, 100.0))

    out = tmp_path / "processed"
    prep.prepare_capture(raw, selected, seg, str(out), images_dir=str(tmp_path),
                         load_image=lambda _p: np.zeros((480, 640, 3), dtype=np.uint8), write_overlay=None)
    result = run_capture(str(out / "capture.json"))
    assert "free_7dof" in result and result["free_7dof"]["method"] == "multiview_cuboid_fit"
    assert result["support_6dof"] is not None  # bundle carries a support plane
    assert result["quantization"]["min_mask_bbox_px"] > 0


# --------------------------------------------------------------------------- #
# Evaluator: ground truth consumed ONLY here.
# --------------------------------------------------------------------------- #

def _run(dims, *, with_support=True, success=True, reason=None):
    def one(d):
        if not success:
            return {"success": False, "reason": reason}
        return {"success": True, "method": "multiview_cuboid_fit",
                "dimensions": {"length_mm": d[0], "width_mm": d[1], "height_mm": d[2]}}
    return {"manifest": "m", "free_7dof": one(dims),
            "support_6dof": one(dims) if with_support else None}


def test_evaluator_gate_pass_tight_repeatable():
    gt = {"length_mm": 345, "width_mm": 290, "height_mm": 245}
    runs = [_run((346, 291, 246)), _run((347, 289, 244)), _run((345, 290, 247))]
    rep = evaluate_runs(runs, gt)
    assert rep["research_gate"]["free_7dof"]["passed"]
    assert rep["research_gate"]["passed"]
    assert rep["repeatability"]["free_7dof"]["sweeps_accepted"] == 3


def test_evaluator_gate_fails_on_large_error():
    gt = {"length_mm": 345, "width_mm": 290, "height_mm": 245}
    runs = [_run((420, 291, 246)), _run((347, 289, 244)), _run((345, 290, 247))]  # 1 sweep ~22% on L
    rep = evaluate_runs(runs, gt)
    assert not rep["research_gate"]["free_7dof"]["passed"]


def test_evaluator_reports_refused_sweeps():
    gt = {"length_mm": 345, "width_mm": 290, "height_mm": 245}
    runs = [_run((346, 291, 246)), _run((0, 0, 0), success=False, reason="unstable_cuboid_fit")]
    rep = evaluate_runs(runs, gt)
    assert rep["sweeps"][1]["free_7dof"]["accepted"] is False
    assert rep["sweeps"][1]["free_7dof"]["reason"] == "unstable_cuboid_fit"
    assert rep["repeatability"]["free_7dof"]["sweeps_accepted"] == 1
