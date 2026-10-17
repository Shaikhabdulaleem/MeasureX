# Model / license manifest — MeasureX vision POC

Every model or checkpoint must be recorded here **before** its weights are
downloaded (CLAUDE.md "Commercial/license discipline", VISION_DECISION.md §8).
Weights are never committed to this repository.

> **Production gate (`PRODUCTION_ALLOWED`):** a checkpoint whose weight license
> forbids commercial use must not enter a production path. Such a model may be
> used for the POC and the benchmark only. The provider interfaces exist so a
> commercially-licensed model can replace a research-only one before
> productionization. `pending` = license plausibly permissive but not yet
> confirmed on the exact checkpoint — do not productionize until confirmed.

VRAM / runtime figures are approximate; confirm on the first real GPU run.

## Depth Pro — metric depth (POC/benchmark baseline)

- **Purpose:** monocular metric depth (provides depth map + predicted focal length).
- **Upstream repo:** https://github.com/apple/ml-depth-pro
- **Version/commit:** install from `main` (record the resolved commit on download).
- **Checkpoint:** `depth_pro.pt`
- **Checkpoint source:** https://ml-site.cdn-apple.com/models/depth-pro/depth_pro.pt (HF mirror: https://huggingface.co/apple/DepthPro)
- **Code license:** Apple sample-code license (see repo)
- **Weight license:** **Apple-ASCL — research only**
- **Commercial use:** **NO**
- **PRODUCTION_ALLOWED:** **false**
- **Expected VRAM:** ~4–6 GB
- **Runtime hardware:** NVIDIA GPU (Colab T4 OK); very slow on CPU
- **Notes:** POC/benchmark baseline only. Do not ship in a MeasureX production build.

## SAM 2 — segmentation

- **Purpose:** shipment segmentation (box → pixel-accurate mask).
- **Upstream repo:** https://github.com/facebookresearch/sam2
- **Version/commit:** install from `main` (record resolved commit on download).
- **Checkpoint:** `sam2.1_hiera_large.pt` (config `configs/sam2.1/sam2.1_hiera_l.yaml`)
- **Checkpoint source:** https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_large.pt
- **Code license:** Apache-2.0 (eval code BSD-3-Clause)
- **Weight license:** **Apache-2.0**
- **Commercial use:** **YES**
- **PRODUCTION_ALLOWED:** **true**
- **Expected VRAM:** ~5–7 GB (hiera-large); smaller hiera variants use less
- **Runtime hardware:** NVIDIA GPU

## Depth Anything V2 Metric Small — commercial-path depth candidate (NOT YET IMPLEMENTED)

- **Purpose:** metric depth with a commercially-usable license (future replacement for Depth Pro).
- **Upstream repo:** https://github.com/DepthAnything/Depth-Anything-V2
- **Version/commit:** TBD at implementation.
- **Checkpoint:** Depth-Anything-V2 **Metric Small** (indoor/outdoor Small variant) — pick the exact HF repo at implementation, e.g. `depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf`.
- **Checkpoint source:** confirm on the exact Hugging Face repo at implementation.
- **Code license:** Apache-2.0
- **Weight license:** **Apache-2.0 per maintainer** for the Small models — **confirm on the exact checkpoint repo + training-data provenance** before relying on it. (Base/Large metric are CC-BY-NC — not usable.)
- **Commercial use:** likely YES for Small — confirm per checkpoint
- **PRODUCTION_ALLOWED:** **pending** (confirm license on the exact checkpoint)
- **Expected VRAM:** ~2 GB (Small)
- **Runtime hardware:** NVIDIA GPU; feasible on CPU, slower
- **Status:** deferred — `get_depth_estimator("depth_anything_v2")` raises `NotImplementedError`. Does not predict focal length, so an EXIF/FOV focal assumption is required when implemented.

## Grounding DINO — optional open-vocabulary detection

- **Purpose:** optional automatic shipment detection (default is the model-free central-candidate).
- **Upstream repo:** https://github.com/IDEA-Research/GroundingDINO
- **Checkpoint:** confirm exact checkpoint at adoption.
- **Code license:** Apache-2.0
- **Weight license:** **Apache-2.0** (confirm exact checkpoint)
- **Commercial use:** YES (confirm per checkpoint)
- **PRODUCTION_ALLOWED:** **pending** (confirm checkpoint)
- **Expected VRAM:** ~3–4 GB
- **Runtime hardware:** NVIDIA GPU
- **Status:** optional; not required for controlled carton tests (central-candidate default).

## Rule

Do not download or use a checkpoint with unclear licensing without flagging it
here first. Before productionizing any model, confirm the **weight** license of
the exact checkpoint (not just the code license) and set `PRODUCTION_ALLOWED`
accordingly with the resolved revision.
