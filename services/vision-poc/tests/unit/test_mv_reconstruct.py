"""M9 end-to-end metric reconstruction on synthetic exact-pose captures.

Fast CI configuration (moderate resolution) — the ``<=2%`` headline accuracy is
demonstrated by ``scripts/m9_synthetic_proof.py``; here we prove the geometry is
correct, metric scale comes from the poses, and failures are handled."""

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
    # Coarse CI config (fine_divisions=60); the tight <=2-3% accuracy is shown by
    # scripts/m9_synthetic_proof.py. Here we assert correct recovery, not SLA.
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


def test_leave_one_out_reports_spread():
    bundle, _ = _capture((0.345, 0.290, 0.245))
    cfg = dataclasses.replace(CFG, leave_one_out=True, leave_one_out_max_runs=4)
    result = reconstruct(bundle, cfg)
    assert result["success"]
    loo = result["quality"]["leave_one_out"]
    assert loo["runs"] >= 2
    assert loo["spread_frac_max"] < 0.1  # exact poses -> stable
