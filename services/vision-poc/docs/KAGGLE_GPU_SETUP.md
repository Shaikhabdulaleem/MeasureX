# Kaggle Notebook (T4) — MeasureX Vision GPU validation (FALLBACK)

Kaggle is the **fallback** GPU environment. The **primary** is Lightning AI
Studio — [`LIGHTNING_GPU_SETUP.md`](LIGHTNING_GPU_SETUP.md). Colab is no longer
used.

This runs the **same `services/vision-poc` code** as Lightning — same stack, same
commands, same outputs. There is no second implementation and no mocked
inference. The only differences are how you start the GPU, where files live, and
that Kaggle notebook cells shell out with a leading `!`.

Real test stack (identical to Lightning):

```
Grounding DINO -> SAM 2 -> Depth Anything V2 Small
  -> masked point cloud -> support plane -> L/W/H
  -> temporal stabilization (video) -> benchmark
```

Depth Anything V2 Small is the preferred depth provider
(`--provider depth_anything_v2`). **Depth Pro stays research-only and optional** —
do not use it for the normal test. No ArUco / marker mat / known-size reference,
no LiDAR / ARCore / ARKit.

---

## 0. Start a T4 notebook

1. New Notebook → **Settings → Accelerator → GPU T4 ×2** (one T4 is enough).
2. **Settings → Internet → On** (needed for `git clone`, `pip`, and the Hugging
   Face auto-downloads).

The T4 has ~15 GB VRAM — the whole stack fits comfortably with Depth Anything V2
Small.

## 1. Clone, check out `main`, install

Use Kaggle's **base environment** — do **not** create a venv. The base image
already ships a CUDA-enabled `torch`, `numpy` 2.x, `opencv`, `timm`, etc.; a venv
would throw those away and force a slow, fragile reinstall. Kaggle's Python is
currently **3.13**, which is fine (the package needs ≥ 3.11). Run in a cell:

```python
!git clone https://github.com/Shaikhabdulaleem/MeasureX.git /kaggle/working/MeasureX
%cd /kaggle/working/MeasureX
!git checkout main
%cd services/vision-poc
!pip install -e ".[dev,seg,depth]"
```

> **Do not add the `vision` extra on Kaggle.** It pulls `open3d` (~400 MB, and
> the engine never imports it) and `opencv-python-headless`, which collides with
> Kaggle's preinstalled `opencv-python` and makes pip **downgrade numpy to
> 1.26**, breaking the preinstalled torch/opencv (both built for numpy 2.x).
> `cv2` for video is already present from the base image.

Kaggle's torch is already CUDA-enabled, so do **not** reinstall it. If a previous
attempt already downgraded numpy (you'll see `numpy 1.26.4 ... incompatible`
errors, or a "compiled against numpy 2.x" warning on `import torch`), restore it:

```python
!pip install -U "numpy>=2"
```

> **Working directory:** Kaggle resets the shell's cwd to `/kaggle/working` if the
> kernel restarts between cells, so `!python scripts/...` can fail with
> `No such file or directory`. Start every cell that runs a relative command with
> `%cd /kaggle/working/MeasureX/services/vision-poc` (shown below) so the cell is
> self-contained.

> **Never reinstall `torch` alone.** Kaggle's `torch` and `torchvision` are a
> matched pair; reinstalling one (e.g. a `--index-url .../cu121` torch install)
> desyncs them and `transformers` then fails to import with
> `RuntimeError: operator torchvision::nms does not exist`. If that happens,
> reinstall the matching pair from one index, e.g.
> `!pip install "torch==2.5.1" "torchvision==0.20.1" --index-url https://download.pytorch.org/whl/cu121`
> (torchvision 0.20.1 matches torch 2.5.1 — pick the match for your torch).

## 2. Weights

Same as Lightning. SAM 2 is a manual download; Grounding DINO and Depth Anything
V2 Small auto-download from Hugging Face on first run.

```python
import os
from huggingface_hub import hf_hub_download
ckpt = hf_hub_download("facebook/sam2.1-hiera-small", "sam2.1_hiera_small.pt",
                       local_dir="/kaggle/working/weights")
os.environ["MEASUREX_SAM2_CHECKPOINT"] = ckpt
os.environ["MEASUREX_SAM2_CONFIG"] = "configs/sam2.1/sam2.1_hiera_s.yaml"
```

Depth Pro (optional, research only, Apple-ASCL, **not for production**):
`!python scripts/download_models.py` — skip it for the normal test.

## 3. Verify GPU + sanity check

```python
%cd /kaggle/working/MeasureX/services/vision-poc
!nvidia-smi
import torch; print("cuda:", torch.cuda.is_available())
!python scripts/check_gpu_environment.py        # expect READY
```

## 4. Upload the image and video

On Kaggle, uploads come in as **Datasets** mounted read-only under
`/kaggle/input/<your-dataset>/`. Add your `box.jpg` and short `box.mp4` as a
dataset (Notebook sidebar → **Add Input → Upload**), then copy them into the
writable working tree:

```python
%cd /kaggle/working/MeasureX/services/vision-poc
!mkdir -p data/samples
!cp /kaggle/input/<your-dataset>/box.jpg data/samples/
!cp /kaggle/input/<your-dataset>/box.mp4 data/samples/
```

## 5. Image + video measurement

```python
%cd /kaggle/working/MeasureX/services/vision-poc
!python -m measurex_vision.cli image data/samples/box.jpg \
  --detector grounding_dino --segmenter sam2 --provider depth_anything_v2 --debug

!python -m measurex_vision.cli video data/samples/box.mp4 \
  --detector grounding_dino --segmenter sam2 --provider depth_anything_v2 \
  --max-frames 8 --debug
```

The image JSON / `outputs/measurement.json` carries **Length / Width / Height mm**
(`dimensions`), **confidence** + `confidence_level`, **runtime** (`timing_ms`) and
**diagnostics** — exactly as documented in the Lightning guide §9.

## 6. Outputs

Artifacts go to `services/vision-poc/outputs/` (i.e.
`/kaggle/working/MeasureX/services/vision-poc/outputs/`), which persists to the
notebook's **Output** tab for download. The debug artifact set
(`mask_overlay.png`, `mask.npy`, `depth_color.png`, `depth_masked_color.png`,
`points.npy`, `measurement.json`, …) is the same table as Lightning §11 — the
engine writes one combined `mask_overlay.png` for detection + segmentation +
measurement overlay; do not modify the engine to split it.

## 7. M5 benchmark

```python
%cd /kaggle/working/MeasureX/services/vision-poc
!python scripts/benchmark.py data/benchmark/manifest.csv \
  --detector grounding_dino --segmenter sam2 --provider depth_anything_v2 \
  --false-success-tolerance-pct 10 --output-dir outputs/benchmark
```

See [`../data/README.md`](../data/README.md) for the manifest + ground-truth
layout. Reports land in `outputs/benchmark/`.
