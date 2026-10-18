# Model / license manifest — MeasureX vision POC

Every model or checkpoint must be recorded here **before** its weights are
downloaded (CLAUDE.md "Commercial/license discipline", VISION_DECISION.md §8).
Weights are never committed to this repository.

> **Code source of truth:** this table is mirrored in
> `src/measurex_vision/models.py` (`MODEL_REGISTRY`), which the provider
> registries enforce. Keep the two in sync. `get_*(..., production=True)` refuses
> any provider whose `production_allowed` is not `true`.

> **Production gate:** a checkpoint whose weight license forbids commercial use
> must not enter a production path. Such a model may be used for the POC and the
> benchmark only. The `DepthEstimator` interface exists so a
> commercially-licensed model can replace it before productionization. No
> production-safe default selects Depth Pro.

## Depth estimation

| Field              | Depth Pro                                                     | Depth Anything V2 (metric)                                                        |
| ------------------ | ------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Role               | Metric depth — **POC/benchmark baseline**                     | Metric depth — **commercial-path, low memory**                                    |
| Model / repo       | https://github.com/apple/ml-depth-pro                         | `depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf` (via transformers)      |
| Weights            | https://huggingface.co/apple/DepthPro                         | Hugging Face (Metric Indoor Small)                                                 |
| Version / commit   | checkpoint `depth_pro.pt` (record exact revision on download) | record HF revision on download                                                    |
| Code license       | Apple sample-code license (see repo)                          | Apache-2.0                                                                         |
| **Weight license** | **Apple-ASCL — research only**                                | **Apache-2.0** (confirm exact checkpoint + data provenance)                        |
| **Commercial use** | **NO**                                                        | **YES** (confirm per checkpoint)                                                   |
| PRODUCTION_ALLOWED | **false**                                                     | **true** (scale via CameraIntrinsicsResolver; confirm checkpoint revision)        |
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
| Weights            | HF `facebook/sam2-hiera-*` (record exact revision on download) |
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
| Checkpoint source      | Hugging Face `IDEA-Research/grounding-dino-tiny`                  |
| Code repo              | https://github.com/IDEA-Research/GroundingDINO                    |
| Code license           | Apache-2.0                                                        |
| **Weight license**     | **Apache-2.0** (confirm exact checkpoint)                        |
| **Commercial use**     | **YES**                                                          |
| **PRODUCTION_ALLOWED** | **true** (confirm checkpoint at productionization)               |
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
