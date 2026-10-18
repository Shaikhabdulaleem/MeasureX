# MeasureX Vision POC — Real GPU Validation Report

> **STATUS: M8 accuracy gate FAILED.** First real end-to-end Kaggle carton run
> completed the full pipeline but produced grossly wrong dimensions. Root cause
> identified and the architecture fixed (see §16); a re-run is pending. **M8 has
> not passed.** Sections still marked `____` await the re-run.

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

## 6. Video result (stabilized)
- Frames accepted: `__/__`  | Stabilized L/W/H: `__ / __ / __` mm
- Spread L/W/H: `__ / __ / __` mm  | Confidence: `____`  | Runtime: `__` ms

## 7. Single-frame vs stabilized
- Single-frame ranges — L: `__–__`  W: `__–__`  H: `__–__` mm
- Stabilized — L: `__`  W: `__`  H: `__` mm
- Did multi-frame reduce error vs the best single frame? `____`

## 8. Depth provider comparison
- Depth Pro: see above.
- Depth Anything V2 Small: **not implemented this milestone (deferred)** — leave blank.
  (When implemented, compare L/W/H error, CBM error, runtime, VRAM, failure rate,
  confidence, PRODUCTION_ALLOWED on the **same** image/video.)

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
- [x] B. Needs geometry/depth tuning
- [ ] C. Needs segmentation tuning
- [ ] D. Needs a different metric-depth provider
- [ ] E. Not currently accurate enough
- [ ] F. Promising enough to begin Flutter integration **after** a larger benchmark

**Rationale:** The first real run failed the accuracy gate because the support
plane was fitted from the object-only cloud (a carton face read as the floor),
not because depth or segmentation were bad. The support-plane architecture has
been fixed (§16); re-run with the same image, then with a phone image carrying
real EXIF/device intrinsics, before any further recommendation.

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

---
Flutter integration does **not** start automatically — it requires explicit owner
approval after reviewing this report (M6 Step 13).
