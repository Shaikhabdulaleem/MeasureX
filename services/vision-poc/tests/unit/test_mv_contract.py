"""M9 strict manifest contract + save/load round-trip.

A capture manifest that is not a well-formed METRIC bundle is rejected with a
typed :class:`ContractError` (never silently accepted). A bundle reconstructed in
memory and one round-tripped through ``save_bundle`` -> ``load_bundle`` must give
equivalent dimensions within voxel tolerance — including the support plane, which
must survive the write."""

from __future__ import annotations

import dataclasses
import json

import numpy as np
import pytest

from measurex_vision.multiview import (
    ContractError,
    FailureCode,
    MetricReconstructionError,
    ReconstructionConfig,
    load_bundle,
    reconstruct,
    validate_bundle,
)
from measurex_vision.multiview.schema import _validate_support_plane
from measurex_vision.multiview.synthetic import save_bundle, synthetic_capture

CFG = ReconstructionConfig(
    min_total_baseline_m=0.05, min_view_coverage_deg=15,
    fine_divisions=60, coarse_divisions=28, leave_one_out=False,
)


def _write_and_tamper(tmp_path, **overrides) -> str:
    """Save a synthetic bundle, then patch capture.json with ``overrides``."""
    bundle, _ = synthetic_capture(
        length_m=0.3, width_m=0.25, height_m=0.2, n_views=6, elevations_deg=(10, 45),
    )
    manifest = save_bundle(bundle, str(tmp_path))
    with open(manifest, encoding="utf-8") as fh:
        doc = json.load(fh)
    doc.update(overrides)
    with open(manifest, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    return manifest


def test_round_trip_preserves_dimensions_and_support_plane(tmp_path):
    bundle, _ = synthetic_capture(length_m=0.345, width_m=0.290, height_m=0.245)
    assert bundle.support_plane is not None
    in_memory = reconstruct(bundle, CFG)["dimensions"]

    manifest = save_bundle(bundle, str(tmp_path))
    loaded = load_bundle(manifest)
    assert loaded.support_plane is not None  # the write did not drop it
    reloaded = reconstruct(loaded, CFG)["dimensions"]

    for k in in_memory:
        assert abs(reloaded[k] - in_memory[k]) <= 3  # mm; sub-voxel round-trip


def test_round_trip_without_support_plane(tmp_path):
    bundle, _ = synthetic_capture(length_m=0.3, width_m=0.25, height_m=0.2)
    bundle = dataclasses.replace(bundle, support_plane=None)
    manifest = save_bundle(bundle, str(tmp_path))
    with open(manifest, encoding="utf-8") as fh:
        assert "support_plane" not in json.load(fh)
    assert load_bundle(manifest).support_plane is None


def test_schema_version_rejected(tmp_path):
    with pytest.raises(ContractError, match="schema_version"):
        load_bundle(_write_and_tamper(tmp_path, schema_version=2))


def test_non_metric_tier_rejected(tmp_path):
    with pytest.raises(ContractError, match="measurement_tier"):
        load_bundle(_write_and_tamper(tmp_path, measurement_tier="estimate"))


def test_wrong_pose_convention_rejected(tmp_path):
    with pytest.raises(ContractError, match="pose_convention"):
        load_bundle(_write_and_tamper(tmp_path, pose_convention="T_camera_from_world"))


def test_wrong_units_rejected(tmp_path):
    with pytest.raises(ContractError, match="units"):
        load_bundle(_write_and_tamper(tmp_path, units="millimeters"))


def test_empty_frames_rejected(tmp_path):
    with pytest.raises(ContractError, match="frames"):
        load_bundle(_write_and_tamper(tmp_path, frames=[]))


def test_missing_mask_file_rejected(tmp_path):
    manifest = _write_and_tamper(tmp_path)
    with open(manifest, encoding="utf-8") as fh:
        doc = json.load(fh)
    doc["frames"][0]["mask"] = "masks/does_not_exist.png"
    with open(manifest, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    with pytest.raises(ContractError, match="does not exist"):
        load_bundle(manifest)


@pytest.mark.parametrize(
    "plane",
    [
        {"normal": [0.0, 0.0, 0.0], "offset": 0.0},          # zero normal
        {"normal": [0.0, 1.0, 0.0], "offset": float("inf")},  # non-finite offset
        {"normal": [1.0, 0.0, 0.0], "offset": 0.0},          # 90 deg from up
        {"offset": 0.0},                                      # missing normal
    ],
)
def test_malformed_support_plane_rejected(plane):
    up = np.array([0.0, 1.0, 0.0])  # gravity (0,1,0) -> up (0,-1,0); |n.up| test
    with pytest.raises(MetricReconstructionError) as e:
        _validate_support_plane(plane, -up)
    assert e.value.code == FailureCode.INVALID_SUPPORT_PLANE


def test_valid_support_plane_accepted_by_validate_bundle():
    bundle, _ = synthetic_capture(length_m=0.3, width_m=0.25, height_m=0.2, n_views=6, elevations_deg=(10, 45))
    validate_bundle(bundle, CFG)  # support plane is horizontal -> accepted
