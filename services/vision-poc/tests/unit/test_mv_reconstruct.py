"""M9 end-to-end metric reconstruction on synthetic exact-pose captures.

Fast CI configuration (moderate resolution). This proves the geometry is correct,
metric scale comes from the poses, and failures are handled — NOT a headline
accuracy figure. ``scripts/m9_synthetic_proof.py`` reports the actual exact-pose
error distribution (a small consistent over-estimate, median ~3% on the current
visual hull, which does NOT meet the ~2% exact-pose target — see
``docs/M9_MULTIVIEW_METRIC_SPIKE.md``)."""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from measurex_vision.multiview import FailureCode, ReconstructionConfig, reconstruct
from measurex_vision.multiview.synthetic import synthetic_capture

CFG = ReconstructionConfig(
    min_total_baseline_m=0.05, min_view_coverage_deg=15,
    fine_divisions=60, coarse_divisions=28, leave_one_out=False,
)


def _capture(dims, scale=1.0):
    return synthetic_capture(
        length_m=dims[0], width_m=dims[1], height_m=dims[2],
        n_views=12, elevations_deg=(8, 38, 65), image_wh=(540, 720),
        distance_m=1.3, scale=scale,
    )


@pytest.mark.parametrize("dims", [(0.345, 0.290, 0.245), (0.500, 0.300, 0.250), (0.400, 0.350, 0.300)])
def test_recovers_dimensions_within_tolerance(dims):
    bundle, gt = _capture(dims)
    result = reconstruct(bundle, CFG)
    assert result["success"], result
    pred = result["dimensions"]
    # Coarse CI config (fine_divisions=60). The actual exact-pose error
    # distribution (~3% median, not <=2%) is reported by
    # scripts/m9_synthetic_proof.py; here we assert correct recovery, not an SLA.
    for k in gt:
        err = abs(pred[k] - gt[k]) / gt[k]
        assert err <= 0.09, f"{k}: pred {pred[k]} gt {gt[k]} ({err:.1%})"


def test_metric_scale_comes_from_poses():
    """Scaling the scene AND camera translations by 2x must scale the recovered
    dimensions by 2x — proof that scale is metric (from poses), not a learned
    monocular prior. Masks are identical between the two captures."""
    b1, _ = _capture((0.345, 0.290, 0.245), scale=1.0)
    b2, _ = _capture((0.345, 0.290, 0.245), scale=2.0)
    r1 = reconstruct(b1, CFG)["dimensions"]
    r2 = reconstruct(b2, CFG)["dimensions"]
    for k in r1:
        assert r2[k] / r1[k] == pytest.approx(2.0, abs=0.02)


def test_deterministic():
    bundle, _ = _capture((0.345, 0.290, 0.245))
    assert reconstruct(bundle, CFG)["dimensions"] == reconstruct(bundle, CFG)["dimensions"]


def test_memory_guard_fails_typed():
    bundle, _ = _capture((0.345, 0.290, 0.245))
    tiny = dataclasses.replace(CFG, max_voxels=1000)
    result = reconstruct(bundle, tiny)
    assert result["success"] is False
    assert result["reason"] == FailureCode.RECONSTRUCTION_FAILED.value


def test_robust_to_one_oversized_mask():
    """A single over-segmented (too-large) mask — the common SAM failure — must not
    degrade the result: other views still carve the extra volume away."""
    bundle, gt = _capture((0.345, 0.290, 0.245))
    f0 = bundle.frames[0]
    big = f0.mask.copy()
    ys, xs = np.nonzero(big)
    big[ys.min() - 30 : ys.max() + 30, xs.min() - 30 : xs.max() + 30] = True  # bloated
    bundle = dataclasses.replace(bundle, frames=[dataclasses.replace(f0, mask=big), *bundle.frames[1:]])
    result = reconstruct(bundle, CFG)
    assert result["success"], result
    for k in gt:
        assert abs(result["dimensions"][k] - gt[k]) / gt[k] <= 0.09


def test_resolution_sweep_shrinks_voxels_without_diverging():
    """A finer grid must use a smaller voxel and keep more occupied voxels, while
    the recovered dimensions stay in a stable band (they do NOT keep converging to
    GT — the residual error floors on hull/coverage geometry, not quantisation, as
    scripts/m9_synthetic_proof.py reports in full). GT-independent band check."""
    bundle, gt = _capture((0.345, 0.290, 0.245))
    runs = {}
    for fine in (40, 60):
        cfg = dataclasses.replace(CFG, fine_divisions=fine)
        r = reconstruct(bundle, cfg)
        assert r["success"], r
        d = r["diagnostics"]
        max_err = max(abs(r["dimensions"][k] - gt[k]) / gt[k] for k in gt)
        runs[fine] = (d["voxel_size_m"], d["final_occupied_voxels"], max_err)
    assert runs[60][0] < runs[40][0]                 # finer voxel
    assert runs[60][1] > runs[40][1]                 # more voxels
    assert runs[40][2] <= 0.06 and runs[60][2] <= 0.06  # stable band, no divergence


def test_leave_one_out_reports_spread():
    bundle, _ = _capture((0.345, 0.290, 0.245))
    cfg = dataclasses.replace(CFG, leave_one_out=True, leave_one_out_max_runs=4)
    result = reconstruct(bundle, cfg)
    assert result["success"]
    loo = result["quality"]["leave_one_out"]
    assert loo["runs"] >= 2
    assert loo["spread_frac_max"] < 0.1  # exact poses -> stable
