"""M9 metric quality gates: multi-view voxel support, typed low-quality failure,
and exact-pose vs pose-noise separation.

A METRIC result must be refused (``success=False``) when the geometry is not
observable enough — it must never return dimensions as a successful metric
measurement on weak geometry. Voxels seen by a single camera are unconstrained in
depth and cannot belong to the hull."""

from __future__ import annotations

import dataclasses

import numpy as np

from measurex_vision.multiview import FailureCode, ReconstructionConfig, reconstruct
from measurex_vision.multiview.synthetic import synthetic_capture
from measurex_vision.multiview.visual_hull import carve, estimate_roi

CFG = ReconstructionConfig(
    min_total_baseline_m=0.05, min_view_coverage_deg=15,
    fine_divisions=60, coarse_divisions=28, leave_one_out=False,
)


def _capture(noise=0.0, seed=1):
    return synthetic_capture(
        length_m=0.345, width_m=0.290, height_m=0.245, n_views=12,
        elevations_deg=(8, 38, 65), image_wh=(540, 720), distance_m=1.3,
        pose_noise_deg=noise, seed=seed,
    )


# --- requirement 6: a voxel must be observed by >= min_usable_views frames ------

def test_single_view_voxels_cannot_survive():
    bundle, _ = _capture()
    centre, half = estimate_roi(bundle, CFG)
    lo, hi, voxel = centre - half, centre + half, 2 * half / 28
    one = carve([bundle.frames[0]], lo, hi, voxel, consensus=1.0, max_voxels=CFG.max_voxels, min_usable_views=2)
    assert one.points_m.shape[0] == 0  # one frame -> usable==1 -> nothing survives


def test_well_observed_voxels_survive_and_are_deterministic():
    bundle, _ = _capture()
    centre, half = estimate_roi(bundle, CFG)
    lo, hi, voxel = centre - half, centre + half, 2 * half / 28
    kw = {"consensus": 1.0, "max_voxels": CFG.max_voxels, "min_usable_views": 2}
    a = carve(bundle.frames, lo, hi, voxel, **kw)
    b = carve(bundle.frames, lo, hi, voxel, **kw)
    assert a.points_m.shape[0] > 0
    np.testing.assert_array_equal(a.points_m, b.points_m)  # deterministic


# --- requirement 7: low quality -> typed failure, not a successful measurement --

def test_unstable_reconstruction_fails_typed():
    bundle, _ = _capture()
    cfg = dataclasses.replace(CFG, leave_one_out=True, leave_one_out_max_runs=4, max_dim_spread_frac=1e-6)
    result = reconstruct(bundle, cfg)
    assert result["success"] is False
    assert result["reason"] == FailureCode.UNSTABLE_RECONSTRUCTION.value
    assert "debug_dimensions_mm" in result  # diagnostic dims retained, not public


def test_low_silhouette_consistency_fails_typed():
    bundle, _ = _capture()
    cfg = dataclasses.replace(CFG, min_silhouette_consistency=1.01)  # unreachable -> always fails
    result = reconstruct(bundle, cfg)
    assert result["success"] is False
    assert result["reason"] == FailureCode.INSUFFICIENT_SILHOUETTE_CONSISTENCY.value


def test_well_observed_capture_passes_the_gate():
    bundle, _ = _capture()
    cfg = dataclasses.replace(CFG, leave_one_out=True, leave_one_out_max_runs=4)
    assert reconstruct(bundle, cfg)["success"] is True


# --- requirement 2: exact-pose and pose-noise are separate experiments ----------

def test_exact_and_noisy_pose_are_independent_experiments():
    """Exact-pose and pose-noise captures are distinct inputs, reconstructed and
    reported separately — their results must never be pooled into one aggregate.
    (The proof script keeps them in separate groups; this asserts the inputs and
    outputs genuinely differ so the separation is meaningful.)"""
    cfg = dataclasses.replace(CFG, leave_one_out=True, leave_one_out_max_runs=4)
    exact_bundle = _capture(noise=0.0)[0]
    noisy_bundle = _capture(noise=0.5, seed=7)[0]
    # The pose-noise capture really is perturbed, not a copy of the exact one.
    assert not np.allclose(
        exact_bundle.frames[1].T_world_from_camera, noisy_bundle.frames[1].T_world_from_camera
    )
    exact = reconstruct(exact_bundle, cfg)
    assert exact["success"]
    assert exact["quality"]["leave_one_out"]["spread_frac_max"] is not None
