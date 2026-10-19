# ADR: RGB-only monocular metric depth is not a billing-grade metric source

**Status:** Accepted
**Date:** 2026-10-19
**Scope:** Measurement engine only (`services/vision-poc`). Non-measurement MeasureX
rules are unchanged.
**Context:** M8 architecture decision point. Evidence:
[`services/vision-poc/docs/REAL_GPU_VALIDATION_REPORT.md`](../services/vision-poc/docs/REAL_GPU_VALIDATION_REPORT.md)
§5–§19.

## Decision

**Single-frame RGB-only monocular metric depth is NOT accepted as the sole
billing-grade metric source for MeasureX.** It may be used only for an explicitly
labelled ESTIMATE, never silently as a METRIC measurement.

## Context and evidence

Two independent monocular metric-depth models — Depth Anything V2 (Small and Base)
and MetricAnything Student — were run on the same real carton image (GT
345 / 290 / 245 mm) with the same mask, support selector, corrected intrinsics
(fx=fy 1004.5988), RANSAC and geometry diagnostic. MetricAnything materially
improved the horizontal footprint but **both models independently predicted
essentially the same wrong height (~360 mm vs GT 245 mm)**. Changing the depth
model alone did not recover absolute scale.

## The projective-scale limitation

A single RGB observation plus camera intrinsics does **not** independently establish
absolute object scale. The projection equation maps a 3D point to the image by
`x = K · (X / Z)`: an object twice as large at twice the distance projects to the
same pixels. Intrinsics fix direction (the ray through each pixel), not depth along
that ray. With one view there is no baseline to triangulate `Z`, so absolute metric
size is unobservable from pixels and intrinsics alone.

Learned monocular metric-depth models estimate absolute scale from **priors** learned
over their training distribution (typical object sizes, scene layouts, focal ranges).
That estimate is a statistical guess, not a measurement, and it degrades out of
distribution — which is exactly what the ~360 mm height error shows. Therefore
monocular metric-depth output **must not be treated as a guaranteed physical
measurement**.

## Measurement tiers

MeasureX measurements are one of two tiers. **A METRIC request must never be silently
downgraded to ESTIMATE** — if a metric cue is unavailable, the engine fails or reports
ESTIMATE explicitly, it does not relabel the result.

### ESTIMATE

- RGB-only monocular path.
- Must be clearly reported to the caller/user as _estimated_.
- Confidence must not imply billing-grade accuracy.

### METRIC

- Requires a genuine metric cue (not monocular priors alone).
- Preferred next research path: **guided multi-frame capture with metric
  visual-inertial camera pose** (see M9 spike below).
- ARCore / ARKit may supply metric camera pose where available.
- Hardware depth (LiDAR / ToF) may be used where available.
- Neither LiDAR nor a special measurement mat is mandatory globally — consistent with
  [`VISION_DECISION.md`](VISION_DECISION.md) §1.

## M9 spike proposal — guided multi-frame metric capture

Goal: recover absolute metric scale from a known metric baseline instead of monocular
priors.

Guided capture:

1. User points the camera at one carton.
2. App guides a short camera sweep.
3. Maintain one carton identity across frames.
4. Collect RGB frames plus **metric camera poses** where supported (ARCore/ARKit VIO).
5. Reconstruct / triangulate carton geometry relative to the support plane.
6. Vertical axis fixed from the support plane.
7. Project object points onto the support plane for L/W.
8. Robust support-plane distance for H.
9. Require temporal consistency before final confirmation.

**Gate:** the M9 spike must first prove metric-scale recovery on known test objects
**before** any Flutter workflow integration.

## Preserved future geometry change (not implemented here)

The current **unconstrained PCA/OBB is deprecated for real captures** — it is
unsuitable for partial single-view carton clouds (report §19). Proposed replacement:

```
support plane
  -> fixed vertical axis
  -> project object points onto the support plane
  -> robust 2D oriented footprint for L/W
  -> robust top/support distance for H
```

This production geometry change is recorded for a later, dedicated patch and is
**not** implemented in this documentation commit.

## Confidence defect (action item, not implemented here)

The latest grossly inaccurate run (report §19A) returned **confidence 0.6059,
level MEDIUM** despite >200% L/W errors. Assumed intrinsics and unvalidated metric
scale must **cap or block** production-grade confidence in a later patch. Confidence
code is **not** modified in this commit.

## Consequences

- No new depth model is added to production on the basis of this ADR.
- Billing-grade dimensioning waits on a METRIC-tier path (M9 spike), not on swapping
  monocular depth models.
- The RGB-only path remains available strictly as a labelled ESTIMATE.
