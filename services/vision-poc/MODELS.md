# Model / license manifest — MeasureX vision POC

Every model or checkpoint must be recorded here **before** its weights are
downloaded (CLAUDE.md "Commercial/license discipline", VISION_DECISION.md §8).
Weights are never committed to this repository.

> **Production gate:** a checkpoint whose weight license forbids commercial use
> must not enter a production path. Such a model may be used for the POC and the
> benchmark only. The `DepthEstimator` interface exists so a
> commercially-licensed model can replace it before productionization.

## Depth estimation

| Field              | Depth Pro                                                     | Depth Anything V2 (metric)                                                        |
| ------------------ | ------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Role               | Metric depth — **POC/benchmark baseline**                     | Commercial slot — **planned, not implemented**                                    |
| Code repo          | https://github.com/apple/ml-depth-pro                         | https://github.com/DepthAnything/Depth-Anything-V2                                |
| Weights            | https://huggingface.co/apple/DepthPro                         | (to confirm at adoption)                                                          |
| Version / commit   | checkpoint `depth_pro.pt` (record exact revision on download) | —                                                                                 |
| Code license       | Apple sample-code license (see repo)                          | Apache-2.0 (to confirm per checkpoint)                                            |
| **Weight license** | **Apple-ASCL — research only**                                | **to confirm** (metric checkpoints vary)                                          |
| **Commercial use** | **NO**                                                        | TBD at adoption                                                                   |
| Download source    | `scripts/download_models.py` → Hugging Face `apple/DepthPro`  | —                                                                                 |
| Status             | Active (research/benchmark; **not for production**)           | Planned — `get_depth_estimator("depth_anything_v2")` raises `NotImplementedError` |

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

## Detection (open-vocabulary, optional)

| Field              | Grounding DINO                                                                      |
| ------------------ | ----------------------------------------------------------------------------------- |
| Role               | Optional automatic shipment detection (default is the model-free central-candidate) |
| Code repo          | https://github.com/IDEA-Research/GroundingDINO                                      |
| Code license       | Apache-2.0                                                                          |
| **Weight license** | **Apache-2.0** (confirm exact checkpoint at adoption)                               |
| **Commercial use** | YES (confirm per checkpoint)                                                        |
| Status             | Optional — not required for controlled POC images                                   |

### Notes

- Depth Pro weights are **not licensed for commercial use**. They are integrated
  here solely to establish the camera-only accuracy baseline and run the
  benchmark. Do not ship them in a MeasureX production build.
- Before adopting Depth Anything V2 (or any commercial-path model), confirm the
  **weight** license of the specific metric checkpoint (not just the code
  license) and update this table with the exact revision and license.
