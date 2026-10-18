# Model / license manifest — MeasureX vision POC

Every model or checkpoint must be recorded here **before** its weights are
downloaded (CLAUDE.md "Commercial/license discipline", VISION_DECISION.md §8).
Weights are never committed to this repository.

> **Code source of truth:** this table is mirrored in
> `src/measurex_vision/models.py` (`MODEL_REGISTRY`), which the provider
> registries enforce. Keep the two in sync. `get_*(..., production=True)` refuses
> any provider whose `production_approved` is not `true`.

> **Two separate concepts.** *Commercially licensed* (`commercial_use`) means the
> code/weights are legally shippable. *Production-approved* (`production_approved`)
> means the provider is approved for real production measurement quality. They are
> independent: the model-free fallbacks (`central_candidate`, `box_mask`) are
> commercially unencumbered yet are **CI / development / synthetic-test aids only**
> and are **not** production-approved. Depth Pro is neither.

> **Production gate.** `--production` resolves the approved real stack
> (**Grounding DINO Tiny → SAM 2.1 Small → Depth Anything V2 Metric Indoor Small**,
> plus `CameraIntrinsicsResolver` → geometry → temporal stabilization) and refuses
> `central_candidate`, `box_mask` and `depth_pro`. A checkpoint whose weight
> license forbids commercial use must never enter a production path.

> **Revision pinning.** Production model revisions are **frozen** to the exact HF
> commits below and passed into `from_pretrained(..., revision=...)`; production
> execution never silently downloads an updated `main`. Record the checkpoint
> SHA256 on first download.

## Depth estimation

| Field              | Depth Pro                                                     | Depth Anything V2 (metric)                                                        |
| ------------------ | ------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Role               | Metric depth — **POC/benchmark baseline**                     | Metric depth — **commercial-path, low memory**                                    |
| Model / repo       | https://github.com/apple/ml-depth-pro                         | `depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf` (via transformers)      |
| Weights            | https://huggingface.co/apple/DepthPro                         | Hugging Face (Metric Indoor Small)                                                 |
| Version / commit   | checkpoint `depth_pro.pt` (research only — not pinned)        | **pinned** HF commit `8078d68a9c75a972131914f6afd0c1723be0da7f` (`model.safetensors`) |
| Code license       | Apple sample-code license (see repo)                          | Apache-2.0                                                                         |
| **Weight license** | **Apple-ASCL — research only**                                | **Apache-2.0**                                                                     |
| **Commercial use** | **NO**                                                        | **YES**                                                                            |
| PRODUCTION_APPROVED | **false**                                                    | **true** (scale via CameraIntrinsicsResolver)                                     |
| Expected VRAM      | ~4–6 GB                                                        | ~1 GB (Small)                                                                      |
| Status             | Active (research/benchmark; **not for production**)           | **Active** — `--provider depth_anything_v2` (Small); production default           |

> **Scale note (Depth Anything V2):** DA-V2 does not predict focal length. Its
> `DepthResult.focal_is_assumed` is `True`, so the `CameraIntrinsicsResolver`
> (`geometry/intrinsics.py`) does not treat its focal as a measured scale source
> and falls back to EXIF / device profile / configured FOV / assumed FOV. An
> assumed-FOV result is reported as `intrinsics_source` and penalizes confidence.

## Segmentation

| Field              | SAM 2                                                          |
| ------------------ | -------------------------------------------------------------- |
| Role               | Shipment segmentation (box → mask)                             |
| Code repo          | https://github.com/facebookresearch/sam2                       |
| Model / weights    | HF `facebook/sam2.1-hiera-small`, **pinned** commit `ee5bba1d82bb8749febdf90f45e84b687142ba03`, checkpoint `sam2.1_hiera_small.pt` |
| Code license       | Apache-2.0 (eval code BSD-3-Clause)                            |
| **Weight license** | **Apache-2.0**                                                 |
| **Commercial use** | **YES**                                                        |
| Download source    | `scripts/download_models.py` (SAM 2 checkpoint)                |
| Status             | Active (segmenter)                                             |

## Detection (open-vocabulary) — shipment target proposer

| Field                  | Grounding DINO                                                     |
| ---------------------- | ----------------------------------------------------------------- |
| Role                   | Locate the shipment and hand SAM 2 a tight prompt box             |
| Model                  | `IDEA-Research/grounding-dino-tiny` (via `transformers`)          |
| Checkpoint source      | HF `IDEA-Research/grounding-dino-tiny`, **pinned** commit `a2bb814dd30d776dcf7e30523b00659f4f141c71` (`model.safetensors`) |
| Code repo              | https://github.com/IDEA-Research/GroundingDINO                    |
| Code license           | Apache-2.0                                                        |
| **Weight license**     | **Apache-2.0**                                                   |
| **Commercial use**     | **YES**                                                          |
| **PRODUCTION_APPROVED** | **true**                                                        |
| Expected VRAM          | ~1–2 GB (tiny)                                                    |
| Runtime hardware       | NVIDIA GPU; feasible on CPU, slower                              |
| Status                 | Active — target proposer (`--detector grounding_dino`)           |

### Notes

- Depth Pro weights are **not licensed for commercial use**. They are integrated
  here solely to establish the camera-only accuracy baseline and run the
  benchmark. Do not ship them in a MeasureX production build.
- Before adopting Depth Anything V2 (or any commercial-path model), confirm the
  **weight** license of the specific metric checkpoint (not just the code
  license) and update this table with the exact revision and license.
- **Model-free fallbacks.** `central_candidate` (detector) and `box_mask`
  (segmenter) carry no weights and are commercially unencumbered, but they are
  CI / development / synthetic-test aids **only** — `production_approved = false`.
  The production gate refuses them exactly as it refuses Depth Pro.
