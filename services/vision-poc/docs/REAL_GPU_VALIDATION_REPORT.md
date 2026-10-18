# MeasureX Vision POC — Real GPU Validation Report

> **TEMPLATE.** Fill this in after running
> `notebooks/MeasureX_GPU_Validation.ipynb` (or the Kaggle fallback) on a real
> carton. Every value below is a placeholder — do not treat it as a result.
> No accuracy target is assumed; report actual numbers first, then recommend.

- **Date:** `____`
- **Run by:** `____`
- **Environment:** Colab / Kaggle (circle one)

## 1. GPU environment
- GPU name: `____`  | device count: `__`  | CUDA: `__`  | torch: `__`

## 2. Models / checkpoints used
| Model | Role | Checkpoint | Resolved commit/rev |
|---|---|---|---|
| Depth Pro | metric depth | depth_pro.pt | `____` |
| SAM 2.1 large | segmentation | sam2.1_hiera_large.pt | `____` |
| (detector) central-candidate | target | — (model-free) | — |

## 3. License / commercial status (from MODELS.md)
| Model | Weight license | Commercial | PRODUCTION_ALLOWED |
|---|---|---|---|
| Depth Pro | Apple-ASCL (research only) | No | **false** |
| SAM 2 | Apache-2.0 | Yes | true |
| Depth Anything V2 Small | Apache-2.0 (confirm) | likely | pending (not implemented) |

## 4. Real carton ground truth (tape-measured, mm)
- object_id: `____`  | Length: `____`  | Width: `____`  | Height: `____`

## 5. Image results (per photo)
| Sample | Pred L | Pred W | Pred H | Confidence | Level | Runtime (ms) | Success |
|---|---|---|---|---|---|---|---|
| image_001 | | | | | | | |

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
| Length | | | | |
| Width | | | | |
| Height | | | | |

## 10. CBM error
- Pred CBM: `____`  | GT CBM: `____`  | Abs err: `____`  | % err: `____`

## 11. Runtime
- Total: `__` ms  | detection `__` / segmentation `__` / depth `__` / geometry `__`

## 12. Failures
- Any `success:false`? failure_code(s): `____`  | observed cause: `____`

## 13. Debug observations
- Mask quality: `____`  | depth plausibility: `____`  | plane/up-axis: `____`
- Which stage dominated the error? `____`

## 14. Did confidence correlate with actual error?
- `____` (e.g. "low confidence runs had the largest error" / "no correlation")

## 15. Recommendation (pick one)
- [ ] A. Ready for wider benchmark
- [ ] B. Needs geometry/depth tuning
- [ ] C. Needs segmentation tuning
- [ ] D. Needs a different metric-depth provider
- [ ] E. Not currently accurate enough
- [ ] F. Promising enough to begin Flutter integration **after** a larger benchmark

**Rationale:** `____`

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

---
Flutter integration does **not** start automatically — it requires explicit owner
approval after reviewing this report (M6 Step 13).
