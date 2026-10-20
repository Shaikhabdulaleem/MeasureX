"""M9 parametric gravity-aligned cuboid fit (offline, synthetic, no GT in the fit).

Covers the Phase R checklist: 6-DOF support-plane and 7-DOF free construction,
projection, silhouette rasterisation, L/W symmetry canonicalisation, support-plane
normal canonicalisation, deterministic fitting, recovery from a non-GT
initialisation across sizes and yaws, low-coverage ambiguity, bad-mask robustness,
pose-noise behaviour, leave-one-out instability, and scale equivariance.

Scenes are deliberately tiny (small image, few frames) so the pure-NumPy optimiser
runs fast with no GPU/model/network. The fit never reads ground-truth dimensions —
GT is compared only after the fact, as an assertion."""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from measurex_vision.multiview import CuboidFitConfig, ReconstructionConfig, fit_cuboid
from measurex_vision.multiview import cuboid_fit as cf
from measurex_vision.multiview.schema import (
    CaptureBundle,
    FailureCode,
    canonical_support_plane,
)
from measurex_vision.multiview.synthetic import synthetic_capture

CFG = CuboidFitConfig(leave_one_out=False)


def _cap(dims=(0.345, 0.290, 0.245), *, n=6, span=90.0, yaw=0.0, w=120, noise=0.0, seed=1):
    """One short continuous sweep, small image, FOV matched to width via fx."""
    return synthetic_capture(
        length_m=dims[0], width_m=dims[1], height_m=dims[2], n_views=n,
        azimuth_span_deg=span, elevations_deg=(12.0, 40.0), continuous_sweep=True,
        image_wh=(w, int(w * 4 / 3)), fx=w * 1004.0 / 960.0, distance_m=1.3,
        yaw_deg=yaw, pose_noise_deg=noise, seed=seed,
    )


def _max_err(pred: dict, gt: dict) -> float:
    return max(abs(pred[k] - gt[k]) / gt[k] for k in gt)


# --- geometry: construction, projection, silhouette (no fitting) ------------- #

def test_6dof_construction_bottom_face_on_plane():
    bundle, _ = _cap()
    frame = cf.build_frame(bundle)
    assert frame.on_plane and frame.dof == 6
    p = cf.CuboidParameters(cu=0.0, cv=0.0, cw=0.0, yaw=0.3, length=0.4, width=0.3, height=0.25)
    verts = cf.cuboid_vertices(p, frame)
    n, d = frame.up, -float(frame.up @ frame.anchor)
    signed = verts @ n + d
    bottom = np.sort(signed)[:4]  # the 4 lowest vertices
    assert np.allclose(bottom, 0.0, atol=1e-9)             # bottom face exactly on the plane
    assert np.isclose(np.sort(signed)[4:].mean(), p.height, atol=1e-9)  # top face at +H


def test_7dof_free_construction_when_no_support_plane():
    bundle, _ = _cap()
    bundle = dataclasses.replace(bundle, support_plane=None)
    frame = cf.build_frame(bundle)
    assert not frame.on_plane and frame.dof == 7


def test_projection_and_silhouette_match_observed_mask():
    """The true box's projected silhouette (rasterised) must agree with the mask the
    synthetic renderer produced for every frame — this exercises project + raster."""
    bundle, _ = _cap(n=6)
    frame = cf.build_frame(bundle)
    true = cf.CuboidParameters(cu=0, cv=0, cw=0, yaw=0.0, length=0.345, width=0.290, height=0.245)
    verts = cf.cuboid_vertices(true, frame)
    for vf in bundle.frames:
        px, depth = cf.project_cuboid(verts, vf)
        assert np.all(depth > 0)
        pred = cf.cuboid_silhouette(px, vf.width, vf.height)
        inter = np.logical_and(pred, vf.mask).sum()
        union = np.logical_or(pred, vf.mask).sum()
        assert inter / union > 0.95  # rasterised silhouette ~= observed mask


def test_lw_symmetry_canonicalisation():
    # (L, W, yaw) and (W, L, yaw+90°) are the same box; canonicalise enforces L>=W.
    p = cf.CuboidParameters(cu=0.1, cv=-0.2, cw=0.0, yaw=0.2, length=0.3, width=0.4, height=0.25)
    c = cf.canonicalise(p)
    assert c.length >= c.width
    assert -np.pi / 2 <= c.yaw < np.pi / 2
    # the two encodings produce the same 8 vertices
    bundle, _ = _cap()
    frame = cf.build_frame(bundle)
    swapped = cf.CuboidParameters(cu=0.1, cv=-0.2, cw=0.0, yaw=0.2 + np.pi / 2, length=0.4, width=0.3, height=0.25)
    v1 = np.array(sorted(map(tuple, np.round(cf.cuboid_vertices(p, frame), 9))))
    v2 = np.array(sorted(map(tuple, np.round(cf.cuboid_vertices(swapped, frame), 9))))
    assert np.allclose(v1, v2)


# --- support-plane normal canonicalisation (schema) ------------------------- #

def test_support_plane_normal_canonicalised_toward_up():
    up = np.array([0.0, -1.0, 0.0])  # gravity (0,1,0) -> up (0,-1,0)
    flipped = {"normal": [0.0, 1.0, 0.0], "offset": 0.7}  # points opposite up
    canon = canonical_support_plane(flipped, up)
    assert np.allclose(canon["normal"], [0.0, -1.0, 0.0])  # flipped toward up
    assert canon["offset"] == -0.7                          # offset negated with it
    already = {"normal": [0.0, -1.0, 0.0], "offset": 0.3}
    assert canonical_support_plane(already, up) == already   # left unchanged


def test_bundle_canonicalises_support_plane_on_construction():
    bundle, _ = _cap()  # reuse valid frames/gravity
    gravity = np.array([0.0, 1.0, 0.0])
    b = CaptureBundle(frames=list(bundle.frames), gravity_world=gravity, pose_source="t",
                      support_plane={"normal": [0.0, 1.0, 0.0], "offset": 0.5})
    assert np.allclose(b.support_plane["normal"], [0.0, -1.0, 0.0])  # toward up at __post_init__
    assert b.support_plane["offset"] == -0.5


# --- fitting: recovery, determinism, sizes, yaws ---------------------------- #

def test_recovers_from_non_gt_initialisation():
    bundle, gt = _cap()
    r = fit_cuboid(bundle, CFG)
    assert r["success"], r
    assert _max_err(r["dimensions"], gt) <= 0.05  # within 5% on a short sweep (hull fails here)


def test_fit_is_deterministic():
    bundle, _ = _cap(w=110)
    assert fit_cuboid(bundle, CFG)["dimensions"] == fit_cuboid(bundle, CFG)["dimensions"]


@pytest.mark.parametrize("dims", [(0.200, 0.150, 0.120), (0.600, 0.400, 0.350), (0.250, 0.240, 0.800)])
def test_recovers_multiple_sizes(dims):
    bundle, gt = _cap(dims=dims, n=8, span=90.0)
    r = fit_cuboid(bundle, CFG)
    assert r["success"], r
    assert _max_err(r["dimensions"], gt) <= 0.06  # no per-carton tuning


@pytest.mark.parametrize("yaw", [0.0, 20.0, 45.0])
def test_recovers_multiple_yaws(yaw):
    bundle, gt = _cap(n=8, span=90.0, yaw=yaw)
    r = fit_cuboid(bundle, CFG)
    assert r["success"], r
    assert _max_err(r["dimensions"], gt) <= 0.06  # observability not dependent on orientation


def test_scale_equivariance():
    """2× scene + 2× camera translations (masks identical) -> 2× dimensions. Scale is
    fixed by the camera poses, not a learned prior."""
    b1, _ = synthetic_capture(length_m=0.345, width_m=0.290, height_m=0.245, n_views=6,
                              azimuth_span_deg=90, elevations_deg=(12, 40), continuous_sweep=True,
                              image_wh=(120, 160), fx=120 * 1004.0 / 960, distance_m=1.3, scale=1.0)
    b2, _ = synthetic_capture(length_m=0.345, width_m=0.290, height_m=0.245, n_views=6,
                              azimuth_span_deg=90, elevations_deg=(12, 40), continuous_sweep=True,
                              image_wh=(120, 160), fx=120 * 1004.0 / 960, distance_m=1.3, scale=2.0)
    r1, r2 = fit_cuboid(b1, CFG)["dimensions"], fit_cuboid(b2, CFG)["dimensions"]
    for k in r1:
        assert r2[k] / r1[k] == pytest.approx(2.0, abs=0.05)


# --- gates: ambiguity, instability, bad masks, pose noise ------------------- #

def test_low_identifiability_fails_typed():
    bundle, _ = _cap()
    cfg = dataclasses.replace(CFG, min_identifiability=1.0)  # unreachable -> always ambiguous
    r = fit_cuboid(bundle, cfg)
    assert r["success"] is False
    assert r["reason"] == FailureCode.AMBIGUOUS_CUBOID_FIT.value
    assert "debug_dimensions_mm" in r  # diagnostic dims retained, not public


def test_leave_one_out_instability_fails_typed():
    bundle, _ = _cap(w=110)
    cfg = dataclasses.replace(CFG, leave_one_out=True, leave_one_out_max_runs=2, max_dim_spread_frac=1e-9)
    r = fit_cuboid(bundle, cfg)
    assert r["success"] is False
    assert r["reason"] == FailureCode.UNSTABLE_CUBOID_FIT.value


def test_silhouette_gate_helper_includes_boundary_residual():
    """The shared silhouette gate (used by both the production gate and the benchmark
    stage accounting) rejects on the boundary residual, not IoU alone — so a stage
    cannot be reported as passed that the real gate would fail."""
    cfg = CuboidFitConfig()
    assert cf.silhouette_consistent(0.95, 0.90, cfg.max_boundary_frac * 0.5, cfg) is True
    assert cf.silhouette_consistent(0.95, 0.90, cfg.max_boundary_frac * 2.0, cfg) is False


def test_insufficient_silhouette_consistency_fails_typed():
    bundle, _ = _cap()
    cfg = dataclasses.replace(CFG, min_mean_iou=1.01)  # unreachable -> always fails
    r = fit_cuboid(bundle, cfg)
    assert r["success"] is False
    assert r["reason"] == FailureCode.INSUFFICIENT_SILHOUETTE_CONSISTENCY.value


def test_one_oversized_mask_is_not_silently_wrong():
    """A single over-segmented mask must not yield a silently-wrong metric size: the
    fit either stays within the gate (other views constrain it) or fails typed."""
    bundle, gt = _cap(n=8, span=90.0)
    f = bundle.frames[3]
    big = f.mask.copy()
    ys, xs = np.nonzero(big)
    big[max(0, ys.min() - 8):ys.max() + 8, max(0, xs.min() - 8):xs.max() + 8] = True
    bundle = dataclasses.replace(bundle, frames=[*bundle.frames[:3], dataclasses.replace(f, mask=big), *bundle.frames[4:]])
    r = fit_cuboid(bundle, CFG)
    if r["success"]:
        assert _max_err(r["dimensions"], gt) <= 0.08
    else:
        assert r["reason"] in {
            FailureCode.INSUFFICIENT_SILHOUETTE_CONSISTENCY.value,
            FailureCode.AMBIGUOUS_CUBOID_FIT.value,
        }


def test_modest_pose_noise_still_recovers():
    bundle, gt = _cap(n=8, span=90.0, noise=0.3, seed=5)
    r = fit_cuboid(bundle, CFG)
    assert r["success"], r
    assert _max_err(r["dimensions"], gt) <= 0.08


# --- Fix 1: support-plane scale normalisation -------------------------------- #

def test_scaled_plane_equations_canonicalise_identically():
    """(n, d) and (k·n, k·d) are the same physical plane; canonicalisation must map
    all of them to ONE representation AND one cuboid geometry (Fix 1)."""
    up = np.array([0.0, -1.0, 0.0])  # gravity (0,1,0) -> up (0,-1,0); all planes are y=1
    planes = [{"normal": [0.0, 1.0, 0.0], "offset": -1.0},
              {"normal": [0.0, 2.0, 0.0], "offset": -2.0},
              {"normal": [0.0, -3.0, 0.0], "offset": 3.0}]
    canon = [canonical_support_plane(p, up) for p in planes]
    for c in canon:
        assert np.allclose(c["normal"], canon[0]["normal"])
        assert c["offset"] == pytest.approx(canon[0]["offset"])
    assert np.allclose(canon[0]["normal"], [0.0, -1.0, 0.0])
    assert canon[0]["offset"] == pytest.approx(1.0)

    bundle, _ = _cap()
    cp = cf.CuboidParameters(cu=0.05, cv=-0.1, cw=0.0, yaw=0.2, length=0.4, width=0.3, height=0.25)
    verts = []
    for p in planes:
        b = dataclasses.replace(bundle, support_plane=dict(p))  # __post_init__ canonicalises
        verts.append(cf.cuboid_vertices(cp, cf.build_frame(b)))
    assert np.allclose(verts[0], verts[1])  # same plane -> same box geometry
    assert np.allclose(verts[0], verts[2])


def test_support_offset_scales_when_normal_normalised():
    """Normalising the normal MUST scale the offset by the same factor, else the
    plane moves. normal [0,2,0]/offset -2 is the plane y=1, not y=2."""
    up = np.array([0.0, -1.0, 0.0])
    c = canonical_support_plane({"normal": [0.0, 2.0, 0.0], "offset": -2.0}, up)
    assert np.allclose(c["normal"], [0.0, -1.0, 0.0])
    assert c["offset"] == pytest.approx(1.0)  # NOT 2.0 (the un-scaled-offset bug)


# --- Fix 2: optimizer convergence reporting ---------------------------------- #

def test_optimizer_reports_convergence():
    bundle, _ = _cap(n=8, span=90.0)
    d = fit_cuboid(bundle, CFG)["diagnostics"]
    assert d["optimizer_converged"] is True
    assert d["optimizer_hit_max_iter"] is False
    assert d["optimizer_success"] is True
    assert d["optimizer_final_step_size"] >= 0.0
    assert isinstance(d["optimizer_at_parameter_bound"], bool)


def test_max_iter_detected_and_not_reported_successful():
    """A fit cut off at the iteration cap is NOT reported as a successful optimiser
    result, and with require_convergence it fails typed (cuboid_fit_failed)."""
    bundle, _ = _cap(n=8, span=90.0)
    cfg = dataclasses.replace(CFG, max_iter=1)  # cannot shrink below min_step in 1 sweep
    r = fit_cuboid(bundle, cfg)
    assert r["success"] is False
    assert r["reason"] == FailureCode.CUBOID_FIT_FAILED.value
    assert r["diagnostics"]["optimizer_hit_max_iter"] is True
    assert r["diagnostics"]["optimizer_success"] is False


# --- Fix 3: full-DOF identifiability ----------------------------------------- #

def test_identifiability_reports_every_fitted_dof():
    bundle, _ = _cap(n=8, span=90.0)
    ident = fit_cuboid(bundle, CFG)["diagnostics"]["parameter_identifiability"]
    for name in ("length", "width", "height", "cu", "cv", "yaw"):
        assert name in ident["per_dof"]
    assert ident["identifiable"] is True


def test_identifiability_reports_cw_for_7dof():
    bundle, _ = _cap(n=8, span=90.0)
    ident = fit_cuboid(bundle, CFG, on_plane=False)["diagnostics"]["parameter_identifiability"]
    assert "cw" in ident["per_dof"]  # free vertical centre only exists in 7-DOF


# --- Fix 4: leak-free leave-one-out ------------------------------------------ #

def test_leave_one_out_revalidates_each_subset():
    """Every LOO subset is re-validated against the SAME config, so a subset that
    drops below min_frames is skipped — proving the refit is rebuilt per subset, not
    run on stale full-sequence geometry. (The old leaky code used a hardcoded floor
    of 4 and the full-sequence frame/locus.)"""
    bundle, _ = _cap(n=5, span=90.0)
    config = ReconstructionConfig(min_frames=5)  # every 4-frame subset is below min
    loo = cf._leave_one_out(bundle, config, dataclasses.replace(CFG, leave_one_out=True), None)
    assert loo["runs"] == 0  # all subsets re-validated and rejected (no stale fit)


def test_leave_one_out_subset_fit_is_stable_on_good_capture():
    bundle, _ = _cap(n=8, span=90.0)
    loo = cf._leave_one_out(bundle, ReconstructionConfig(), dataclasses.replace(CFG, leave_one_out=True), None)
    assert loo["runs"] >= 2
    assert loo["spread_frac_max"] < 0.10


# --- Fix: LOO evidence requirement — absence of evidence is NOT "stable" ------ #

def test_loo_zero_successful_runs_fails_metric():
    """A. No LOO subset can be refit (every subset drops below min_frames) -> the
    metric result is refused, not passed on a None spread."""
    bundle, _ = _cap(n=6, span=90.0)
    cfg = dataclasses.replace(CFG, leave_one_out=True, leave_one_out_max_runs=4)
    r = fit_cuboid(bundle, cfg, config=ReconstructionConfig(min_frames=6))
    assert r["success"] is False
    assert r["reason"] == FailureCode.INSUFFICIENT_STABILITY_EVIDENCE.value
    loo = r["diagnostics"]["leave_one_out_spread"]
    assert loo["successful_runs"] == 0 and loo["failed_runs"] == loo["requested_runs"]
    assert all(f["reason"] == FailureCode.INSUFFICIENT_FRAMES.value for f in loo["failures"])


def test_loo_single_successful_run_fails_metric():
    """B. One successful LOO run is below min_loo_success_runs (2) -> refused."""
    bundle, _ = _cap(n=8, span=90.0)
    cfg = dataclasses.replace(CFG, leave_one_out=True, leave_one_out_max_runs=1)
    r = fit_cuboid(bundle, cfg)
    assert r["success"] is False
    assert r["reason"] == FailureCode.INSUFFICIENT_STABILITY_EVIDENCE.value
    assert r["diagnostics"]["leave_one_out_spread"]["successful_runs"] == 1


def test_loo_all_subsets_valid_and_stable_succeeds():
    """C. Every selected subset refits and the spread is tiny -> success, with full
    LOO evidence reported."""
    bundle, _ = _cap(n=8, span=90.0)
    cfg = dataclasses.replace(CFG, leave_one_out=True, leave_one_out_max_runs=3)
    r = fit_cuboid(bundle, cfg)
    assert r["success"], r
    loo = r["diagnostics"]["leave_one_out_spread"]
    assert loo["successful_runs"] == loo["requested_runs"] >= 2
    assert loo["failed_runs"] == 0


def test_loo_subset_loses_observability_fails_metric():
    """D. A dropped end-frame pushes some subsets below the view-coverage floor; with
    every selected subset required, the missing evidence refuses the metric even
    though the surviving subsets agree (tiny spread)."""
    bundle, _ = _cap(n=6, span=45.0)
    cfg = dataclasses.replace(CFG, leave_one_out=True, leave_one_out_max_runs=4)
    r = fit_cuboid(bundle, cfg, config=ReconstructionConfig(min_view_coverage_deg=45.0))
    assert r["success"] is False
    assert r["reason"] == FailureCode.INSUFFICIENT_STABILITY_EVIDENCE.value
    loo = r["diagnostics"]["leave_one_out_spread"]
    assert loo["failed_runs"] >= 1
    assert any(f["reason"] == FailureCode.INSUFFICIENT_VIEW_COVERAGE.value for f in loo["failures"])


def test_loo_unconverged_subfit_excluded_from_evidence():
    """E. A subfit that does not converge is recorded as a failure and its dimensions
    are NOT counted toward the spread — unconverged geometry is not stability
    evidence (max_iter=1 cannot shrink the step below min_step)."""
    bundle, _ = _cap(n=8, span=90.0)
    cfg = dataclasses.replace(CFG, leave_one_out=True, leave_one_out_max_runs=3, max_iter=1)
    loo = cf._leave_one_out(bundle, ReconstructionConfig(), cfg, None)
    assert loo["successful_runs"] == 0
    assert loo["failed_runs"] == loo["requested_runs"]
    assert all(f["reason"] == FailureCode.CUBOID_FIT_FAILED.value for f in loo["failures"])
    assert loo["spread_frac_max"] is None  # no dims from unconverged subfits


# --- Fix 13: the 7-DOF fit actually runs (not only constructs) --------------- #

def test_7dof_free_fit_recovers_dimensions():
    bundle, gt = _cap(n=8, span=90.0)
    r = fit_cuboid(bundle, CFG, on_plane=False)
    assert r["success"], r
    assert r["diagnostics"]["dof"] == 7 and not r["diagnostics"]["on_plane"]
    assert _max_err(r["dimensions"], gt) <= 0.08


# --- Fix 11: resolution helper + typed insufficient-resolution --------------- #

def test_image_quantization_uncertainty_helper():
    bundle, _ = _cap(n=8, span=90.0, w=200)
    unc = cf.image_quantization_uncertainty(bundle, CFG)
    assert unc["runs"] >= 2
    for k in ("length_mm", "width_mm", "height_mm"):
        assert unc[k] is not None and unc[k] >= 0.0
    assert unc["min_mask_bbox_px"] > 0


def test_insufficient_image_resolution_typed():
    bundle, _ = _cap(n=8, span=90.0, w=120)
    cfg = dataclasses.replace(CFG, min_mask_bbox_px=1e6)  # unreachable floor
    r = fit_cuboid(bundle, cfg)
    assert r["success"] is False
    assert r["reason"] == FailureCode.INSUFFICIENT_IMAGE_RESOLUTION.value


# --- Fix 15: pose-scale bias propagates into dimensions ---------------------- #

def test_pose_scale_bias_propagates_into_dimensions():
    """A correlated +2% scale on every camera translation (+ the plane datum) must
    propagate ~+2% into dimensions — scale comes from the poses, and the fit does
    NOT compensate. This defines the metric-pose-provider accuracy requirement."""
    bundle, _ = _cap(n=8, span=90.0)
    base = fit_cuboid(bundle, CFG)
    assert base["success"]
    bias = 0.02
    frames = [dataclasses.replace(f, T_world_from_camera=_scale_t(f.T_world_from_camera, bias))
              for f in bundle.frames]
    plane = {**bundle.support_plane, "offset": bundle.support_plane["offset"] * (1 + bias)}
    biased = fit_cuboid(dataclasses.replace(bundle, frames=frames, support_plane=plane), CFG)
    assert biased["success"]
    for k in base["dimensions"]:
        ratio = biased["dimensions"][k] / base["dimensions"][k]
        assert ratio == pytest.approx(1.0 + bias, abs=0.01)


def _scale_t(T: np.ndarray, bias: float) -> np.ndarray:
    out = T.copy()
    out[:3, 3] = out[:3, 3] * (1.0 + bias)
    return out
