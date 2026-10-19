# MeasureX Vision POC — Real GPU Validation Report

> **STATUS: M8 accuracy gate FAILED.** The evaluation now spans five runs on the
> same real carton: the original real run (§5), the support-plane-separated run
> (§17, fix 08ef2e3), the post-intrinsics-fix run (§19A, fix 8eb020f), and two
> depth-model *diagnostic* benchmarks — DA-V2 Base (§19B) and MetricAnything
> Student (§19C). The two full production runs produced grossly wrong dimensions;
> the diagnostic benchmarks (not full production runs) confirm that swapping the
> monocular metric-depth model alone does not recover absolute scale, especially
> height. A diagnostics-only patch (§18) gathered the real-run evidence. The M8
> decision is recorded in [`../../../docs/ADR_RGB_METRIC_SCALE.md`](../../../docs/ADR_RGB_METRIC_SCALE.md).
> **M8 has not passed.**

- **Date:** 2026-10-18 (first real run)
- **Run by:** owner (Kaggle)
- **Environment:** Kaggle

## 1. GPU environment
- GPU name: `____`  | device count: `__`  | CUDA: `__`  | torch: `__`

## 2. Models / checkpoints used (production M8 stack)
| Model | Role | Checkpoint | Resolved commit/rev |
|---|---|---|---|
| Grounding DINO Tiny | open-vocab detection | groundingdino_swint_ogc | `____` |
| SAM 2.1 Small | segmentation | sam2.1_hiera_small.pt | `____` |
| Depth Anything V2 Metric Indoor Small | metric depth | depth_anything_v2_metric_hypersim_vits | `____` |

> Depth Pro is **research-only** (non-commercial weights) and is **not** the
> production path — kept for comparison only, never for a production run.

## 3. License / commercial status (from MODELS.md)
| Model | Weight license | Commercial | PRODUCTION_ALLOWED |
|---|---|---|---|
| Grounding DINO Tiny | Apache-2.0 | Yes | true |
| SAM 2.1 Small | Apache-2.0 | Yes | true |
| Depth Anything V2 Metric Indoor Small | Apache-2.0 | Yes | true |
| Depth Pro | Apple-ASCL (research only) | No | **false** (not production) |

## 4. Real carton ground truth (tape-measured, mm)
- object_id: `carton_01`  | Length: `345`  | Width: `290`  | Height: `245`

## 5. Image results (per photo)
| Sample | Pred L | Pred W | Pred H | Confidence | Level | Runtime (ms) | Success |
|---|---|---|---|---|---|---|---|
| image_001 | 1132 | 1046 | 619 | 0.574 | LOW | ~16700 | true (but wrong) |

> Prompt used: `--prompt "cardboard box."` (deliberate — the broad default prompt
> produced a false multiple-target result). Prompt tuning is a separate follow-up.
> Diagnostics: mask_area_ratio 0.280, point_count 343476, depth_valid_ratio 1.0,
> intrinsics_source assumed, fx=fy 753.449, assumed_fov_deg 65.0,
> plane_inlier_ratio 0.535, object_point_count 154844.

> **Capture note (corrected):** this image is from a Samsung Galaxy A16 4G
> (SM-A165F/DS) 1x main camera, shot in **portrait** at 960×1280. The old
> fallback applied the 65° FOV across the **short** (960 px) axis, giving
> fx=fy 753.449 — physically wrong for a portrait frame. The fallback now treats
> the built-in 65° as a **long-axis** FOV (across max(w,h)=1280), giving
> fx=fy ≈ 1005 px, orientation-invariant. This corrects a scale assumption only;
> it does **not** solve the accuracy problem — the support-plane overshoot below
> remains the dominant error, and intrinsics stay `assumed` (no EXIF/device focal).

## 6. Video result (stabilized)
- Frames accepted: `__/__`  | Stabilized L/W/H: `__ / __ / __` mm
- Spread L/W/H: `__ / __ / __` mm  | Confidence: `____`  | Runtime: `__` ms

## 7. Single-frame vs stabilized
- Single-frame ranges — L: `__–__`  W: `__–__`  H: `__–__` mm
- Stabilized — L: `__`  W: `__`  H: `__` mm
- Did multi-frame reduce error vs the best single frame? `____`

## 8. Depth provider comparison
Full depth-provider comparison data is in **§19** (same image, mask, support
selector, intrinsics, RANSAC and geometry). Summary:
- **Depth Anything V2 Small** — current production POC provider (§19A).
- **Depth Anything V2 Base** — diagnostic benchmark; did **not** improve accuracy (§19B).
- **MetricAnything Student** — external diagnostic benchmark; improved the robust
  footprint but **not** metric height (§19C).
- **Depth Pro** — research-only (non-commercial weights); **not** a production path.

## 9. Dimensional errors (vs ground truth)
| Dim | Pred | GT | Abs err (mm) | % err |
|---|---|---|---|---|
| Length | 1132 | 345 | 787 | +228% |
| Width | 1046 | 290 | 756 | +261% |
| Height | 619 | 245 | 374 | +153% |

## 10. CBM error
- Pred CBM: `0.733`  | GT CBM: `0.0245`  | Abs err: `0.708`  | % err: `+2890%`

## 11. Runtime
- Total: `~16700` ms  | detection `__` / segmentation `__` / depth `__` / geometry `__`

## 12. Failures
- Any `success:false`? No — the run returned `success:true` with LOW confidence,
  but the dimensions are grossly wrong (a false success). Root cause in §16.

## 13. Debug observations
- Mask quality: plausible (mask_area_ratio 0.28). depth plausibility: all valid
  (depth_valid_ratio 1.0). plane/up-axis: **wrong** — the support plane was fitted
  from the object-only cloud, so a dominant carton face was taken as the floor.
- Which stage dominated the error? Geometry (support-plane selection). Intrinsics
  were also `assumed` (65° FOV), an independent scale uncertainty, but the 3–4×
  overshoot is the support-plane architecture bug, not FOV alone.

## 14. Did confidence correlate with actual error?
- `____` (e.g. "low confidence runs had the largest error" / "no correlation")

## 15. Recommendation (pick one)
- [ ] A. Ready for wider benchmark
- [ ] B. Needs geometry/depth tuning
- [ ] C. Needs segmentation tuning
- [ ] D. Needs a different metric-depth provider
- [x] E. Not currently accurate enough
- [ ] F. Promising enough to begin Flutter integration **after** a larger benchmark

**Rationale:** The reruns requested after the first failure have now been done.
The support-plane separation (§17) and the portrait-FOV intrinsics (§19A) were
both fixed, yet the post-fix production run is still ~206% over on L/W and ~50%
over on H. Two independent metric-depth models (DA-V2 §19B and MetricAnything
§19C) predict essentially the same wrong ~360 mm height from the same single RGB
view, so option D (a different metric-depth provider) is ruled out as the fix.
Single-frame RGB-only measurement is **not currently accurate enough** for
billing-grade use. **M9 metric multi-frame research** (guided capture with metric
visual-inertial camera pose) is the recommended next path — see
[`../../../docs/ADR_RGB_METRIC_SCALE.md`](../../../docs/ADR_RGB_METRIC_SCALE.md).
Flutter integration is **not** ready.

## 16. Known issues found & fixed during validation
- **O(N²) plane-refit memory bug (fixed).** The real Kaggle carton test ran the
  full production pipeline (Grounding DINO + SAM 2 + Depth Anything V2) and hit a
  host-memory OOM/restart, even though each model passed standalone. Root cause:
  `geometry/planes.py::fit_plane_ransac` refit the inlier plane with
  `np.linalg.svd(pts - centroid)`, whose default `full_matrices=True` materialises
  an N×N `U` for a masked cloud of hundreds of thousands of points. Replaced with
  a 3×3 covariance + `np.linalg.eigh` (smallest eigenvector = plane normal); same
  normal/offset/inlier contract, no N×N allocation. Covered by a regression test
  that fails if full-matrix SVD is reused.
- **Support plane fitted from the object-only cloud (fixed).** The first real
  carton (GT 345/290/245 mm) came back 1132/1046/619 mm — a false success. Root
  cause: `build_masked_cloud` back-projected only SAM-mask (object) pixels, and
  `measure_from_cloud` fitted the support plane with RANSAC on that object-only
  cloud, so a large planar carton face was selected as the "floor" and the whole
  measurement was taken off the wrong reference. Fix: the pipeline now keeps
  `object_points_m` and `support_points_m` separate; a conservative image-space
  selector (`quality/support_region.py`) picks scene pixels around/below the
  object base (object pixels excluded) as support candidates; the plane is fitted
  from `support_points_m` only, and the up-axis is derived from it. When no
  trustworthy support candidate exists the engine returns the new typed failure
  `support_plane_not_found` instead of fabricating dimensions. No dimension was
  calibrated against the ground truth — GT is used for validation only.

## 17. Second real run (after 08ef2e3 — support/object cloud separation)

- **Date:** 2026-10-18 (second real run)  | **Environment:** Kaggle

| Sample | Pred L | Pred W | Pred H | Confidence | Level | Runtime (s) | Success |
|---|---|---|---|---|---|---|---|
| image_002 | 1409 | 848 | 470 | 0.596 | LOW | ~14.18 | true (but wrong) |

Diagnostics reported:
- object_point_count_raw 343476, object_point_count 315043
- support_candidate_point_count 389475, support_region_area_ratio 0.3170 (31.7%)
- support_region_strategy bbox_apron
- support_plane_inlier_ratio 0.6387 (63.9%)
- intrinsics_source assumed, fx=fy 753.449, assumed_fov_deg 65.0

Dimensional error vs GT (345 / 290 / 245 mm):

| Dim | Pred | GT | Abs err (mm) | % err |
|---|---|---|---|---|
| Length | 1409 | 345 | 1064 | +308% |
| Width | 848 | 290 | 558 | +192% |
| Height | 470 | 245 | 225 | +92% |

- CBM: pred 0.5616 m³, GT 0.0245 m³, abs err 0.5371, % err ~+2192%.
- **Accuracy: still FAILED.** The support/object cloud separation is structurally
  correct (a separate 389k-point support cloud was selected and the plane fitted
  to it with a 63.9% inlier ratio), but the dimensions remain 2–4× too large.
  Candidate causes not yet isolated: (A) wrong support plane, (B) depth scale,
  (C) assumed intrinsics (65° FOV, no EXIF/device focal), (D) PCA/OBB axis or
  outlier behaviour. The §18 diagnostics patch instruments all four.
- GT 345/290/245 is recorded here as validation evidence only; no production
  calculation reads it.

## 18. Diagnostics-only patch (no measurement change)

Added strong real-run diagnostics so the next decision is evidence-driven. The
measurement algorithm is unchanged (dimensions, thresholds, FOV, RANSAC, support
selector, PCA/OBB, depth scaling, detector prompt and confidence logic are all
untouched). With `--debug`:

- `support_region_overlay.png` — object/SAM region vs support-candidate region.
- `support_plane_inliers_overlay.png` — RANSAC plane inliers vs support outliers
  vs object pixels (pixel↔point correspondence retained).

`measurement.json` now also carries: support plane normal/offset/inlier
count+ratio; object and support depth percentiles (p01/p05/p50/p95/p99, plus
object min/max); object-above-plane distance percentiles and max; raw OBB
extents/axes, up vector, per-axis up-alignment, selected vertical axis index,
horizontal extents and computed height before mm conversion; and image-space
bbox/mask/size diagnostics. These describe the existing measurement; they do not
alter it.

## 19. Post-intrinsics-fix run and depth-model benchmarks (M8 decision evidence)

All three runs below use the **same** image, SAM mask, support selector, corrected
intrinsics (fx=fy 1004.5988, 65° long-image-axis FOV fallback), RANSAC and
support-plane geometry diagnostic. No measurement algorithm was changed to produce
them, and no dimension was tuned against the GT (345 / 290 / 245 mm — validation
only).

### A. Depth Anything V2 Small — post-intrinsics-fix run (current production stack)

| Sample | Pred L | Pred W | Pred H | Confidence | Level |
|---|---|---|---|---|---|
| image_003 | 1057 | 884 | 368 | 0.6059 | **MEDIUM** |

- Production 3D PCA/OBB: **1057 / 884 / 368 mm**.
- Support-plane-constrained diagnostic: L P5–95 **588.2 mm**, W P5–95 **371.7 mm**,
  height P95 **363.8 mm**.
- intrinsics_source assumed, fx=fy **1004.5988**; support inlier ratio **0.6861**.
- Error vs GT: L +206%, W +205%, H +50%.
- **Confidence-calibration failure (address later):** the engine reported
  **MEDIUM (0.6059)** confidence despite >200% L/W errors. A grossly inaccurate
  result must not surface as MEDIUM. See §19D action item; do not change confidence
  code in this documentation commit.

### B. Depth Anything V2 Base — benchmark

| Robust footprint L | Robust footprint W | Height P95 | Support inlier ratio |
|---|---|---|---|
| 623.3 mm | 359.3 mm | 410.7 mm | 0.5276 |

- **Base did not improve the result** — footprint and height remain far from GT, and
  the support inlier ratio dropped vs Small. A larger DA-V2 variant is not the fix.

### C. MetricAnything Student — external benchmark (MetricAnything student model)

Same image, same SAM mask, same support selector, same corrected intrinsics, same
RANSAC, same geometry diagnostic.

- Current 3D PCA/OBB: 1334 / 1181 / 363 mm.
- Support-plane-constrained diagnostic (robust footprint): **496.0 / 316.7 mm**,
  height P95 **359.9 mm**.

| Dim | Robust value | GT | % err |
|---|---|---|---|
| Length | 496.0 mm | 345 mm | **+43.8%** |
| Width | 316.7 mm | 290 mm | **+9.2%** |
| Height (P95) | 359.9 mm | 245 mm | **+46.9%** |

**Robust-to-robust comparison (like-for-like, support-plane-constrained footprint
of both models — not the production 3D OBB):**

| Model | Robust L | L % err | Robust W | W % err |
|---|---|---|---|---|
| DA-V2 Small (§19A) | 588.2 mm | +70.5% | 371.7 mm | +28.2% |
| MetricAnything | 496.0 mm | +43.8% | 316.7 mm | +9.2% |

- MetricAnything **improved robust length error from +70.5% to +43.8% and robust
  width error from +28.2% to +9.2%**, but **height remained ~47% high**: it
  independently predicts essentially the same incorrect ~360 mm height as DA-V2
  (GT 245 mm). The footprint improvement is real; absolute metric height is not
  solved by changing the depth model.

### D. M8 conclusion and action items

Two independent monocular metric-depth models (DA-V2 and MetricAnything) predict
the **same** wrong carton height (~360 mm vs GT 245 mm) from the same single RGB
view. This is strong evidence that **changing the monocular metric-depth model
alone will not meet the MeasureX absolute-dimension accuracy requirement**. It also
confirms:

- unconstrained 3D PCA/OBB is unsuitable for partial single-view carton clouds;
- the support-plane-constrained footprint is structurally superior;
- the camera portrait-FOV bug is already fixed (8eb020f);
- support/object cloud separation is already fixed (08ef2e3).

Action items (do **not** implement in this documentation commit):

1. **Confidence calibration defect.** Assumed intrinsics and unvalidated metric
   scale must cap or block production-grade confidence; the 0.6059/MEDIUM result
   above must not be reachable for a >200%-error measurement. (Confidence code
   unchanged here.)
2. **Measurement method.** See `docs/ADR_RGB_METRIC_SCALE.md`: single-frame
   RGB-only metric depth is not accepted as the sole billing-grade metric source;
   the next research path is guided multi-frame capture with metric camera pose
   (M9 spike).

---
Flutter integration does **not** start automatically — it requires explicit owner
approval after reviewing this report (M6 Step 13).
