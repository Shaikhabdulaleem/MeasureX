# Lightning AI Studio — MeasureX Vision GPU validation (PRIMARY)

This is the **primary** GPU environment for validating the camera-only vision
engine. (Kaggle is the fallback — see [`KAGGLE_GPU_SETUP.md`](KAGGLE_GPU_SETUP.md).)
Colab is no longer used.

The runtime environment changes here; **the Vision Engine does not**. You run the
exact same `services/vision-poc` code — no second implementation, no mocked
inference, no ArUco / marker mat / known-size reference object, and **no** LiDAR /
ARCore / ARKit requirement.

Real test stack:

```
Grounding DINO -> SAM 2 -> Depth Anything V2 Small
  -> masked point cloud -> support plane -> L/W/H
  -> temporal stabilization (video) -> benchmark
```

Depth Anything V2 Small is the **preferred depth provider** here: its
implementation is complete (`--provider depth_anything_v2`), weights are
Apache-2.0, and at ~1 GB VRAM the whole stack fits a single modest GPU. **Depth
Pro stays research-only and optional** — do not download or use it for the normal
GPU test.

---

## 0. One-time: start a Studio with a GPU

1. Open <https://lightning.ai> and create / open a **Studio**.
2. In the Studio, open the compute selector (top-right) and switch to a **GPU**
   machine. Any CUDA GPU with **≥ 8 GB VRAM** is enough (T4 / L4 / A10 all work).
3. Wait for the Studio to show the GPU as active.

Everything below runs in the **Studio terminal**.

## 1. Clone the repo and check out `main`

```bash
cd ~
git clone https://github.com/Shaikhabdulaleem/MeasureX.git
cd MeasureX
git checkout main
cd services/vision-poc
```

## 2. Python environment

Lightning Studio images ship Python ≥ 3.11 (3.12/3.13 are fine — the package
needs ≥ 3.11). **Prefer the Studio's base environment**, which already has a
CUDA-enabled `torch`: just use it. Create a venv only if you specifically want
isolation — a fresh venv has no preinstalled torch, so you'll pay for the CUDA
torch install in step 4:

```bash
python --version                  # expect 3.11+ ; use it directly
# optional isolation only:
# python -m venv .venv && source .venv/bin/activate
```

## 3. Install the vision package + the real model stack

```bash
pip install --upgrade pip
pip install -e ".[dev,seg,depth]"
python -c "import cv2" 2>/dev/null || pip install "opencv-python-headless>=4.9"
```

- `seg` → SAM 2 + Grounding DINO (via `transformers`) + `timm`
- `depth` → `torch`, `transformers`, Depth Anything V2 (via `transformers`); it
  also pulls Apple `depth_pro` as a package, but you never download its weights.
- `dev` → pytest / ruff
- OpenCV (`cv2`) is only needed to decode **video**; the second line installs it
  only if the image doesn't already have it.

> **Skip the `vision` extra.** It adds `open3d` (~400 MB and never imported by
> the engine — geometry is pure NumPy). On an image that already has numpy 2.x /
> opencv, requesting it can make pip downgrade numpy to 1.26 and break the
> preinstalled torch. If that already happened, run `pip install -U "numpy>=2"`.

## 4. PyTorch + CUDA

On the base environment torch is already CUDA-enabled — **skip this step**. Only in
a **fresh venv** (or if `python scripts/check_gpu_environment.py` in step 7 reports
**CUDA available: False**) install the CUDA build — and always reinstall
`torchvision` from the **same** index in the **same** command, or you get a
mismatched pair and `transformers` fails to import with
`RuntimeError: operator torchvision::nms does not exist`:

```bash
pip install --force-reinstall torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

> Never reinstall `torch` alone on a hosted base image: it desyncs the
> preinstalled `torchvision`. If you already did, install the matching pair, e.g.
> `pip install "torch==2.5.1" "torchvision==0.20.1" --index-url https://download.pytorch.org/whl/cu121`
> (torchvision 0.20.1 matches torch 2.5.1; pick the matching torchvision for your
> torch version).

## 5. Download the approved weights

Only SAM 2 needs a manual download; the other two auto-download from Hugging Face
on first run.

**SAM 2 (Apache-2.0)** — download the Small checkpoint and point two env vars at
the checkpoint and its matching config (the config ships inside the installed
`sam2` package):

```bash
mkdir -p weights
python - <<'PY'
from huggingface_hub import hf_hub_download
p = hf_hub_download("facebook/sam2.1-hiera-small", "sam2.1_hiera_small.pt",
                    local_dir="weights")
print("SAM 2 checkpoint:", p)
PY
export MEASUREX_SAM2_CHECKPOINT="$PWD/weights/sam2.1_hiera_small.pt"
export MEASUREX_SAM2_CONFIG="configs/sam2.1/sam2.1_hiera_s.yaml"   # resolved from the sam2 package
```

**Grounding DINO** (`IDEA-Research/grounding-dino-tiny`) and **Depth Anything V2
Small** (`depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf`) are fetched
automatically by `transformers` the first time you run a measurement, and cached
under `~/.cache/huggingface`.

**Depth Pro — optional, research only.** Skip it for the normal test. If you ever
need the research baseline: `python scripts/download_models.py` (Apple-ASCL,
**not for production** — see [`../MODELS.md`](../MODELS.md)).

## 6. Verify the GPU

```bash
nvidia-smi
python -c "import torch; print('cuda:', torch.cuda.is_available())"
```

Expect `nvidia-smi` to list the GPU and the second line to print `cuda: True`.

## 7. Runtime sanity check

```bash
python scripts/check_gpu_environment.py
```

It reports Python / torch / CUDA versions, CUDA availability, GPU model + VRAM,
host RAM, whether every required package imports, and whether the weights are in
place. It exits `0` and prints **READY** when the real stack can run.

## 8. Upload your test image and video

In Lightning, use the Studio's **file browser** (left sidebar): drag a `.jpg` box
photo and a short `.mp4` into the Studio. Put them under the (git-ignored)
samples folder so they don't get committed:

```bash
mkdir -p data/samples
# drag box.jpg and box.mp4 into services/vision-poc/data/samples/ in the file browser
ls data/samples
```

> Anything under `data/samples/`, `data/benchmark/`, `weights/`, and `outputs/`
> is git-ignored by design — uploaded media and weights never enter Git.

## 9. Run a real IMAGE measurement

```bash
python -m measurex_vision.cli image data/samples/box.jpg \
  --detector grounding_dino --segmenter sam2 --provider depth_anything_v2 \
  --debug
```

The printed JSON (and `outputs/measurement.json`) contains:

- **Length / Width / Height** — `dimensions.length_mm`, `width_mm`, `height_mm`
- **confidence** — `confidence` (0–1) and `confidence_level`
- **runtime** — `timing_ms` (per-stage and total milliseconds)
- **diagnostics** — `diagnostics` (valid-depth ratio, mask area, assumptions such
  as the HFOV used by Depth Anything V2, …)

On weak geometry the engine returns a typed `failure_code` instead of inventing
dimensions — that is correct behaviour, not an error.

## 10. Run a real VIDEO measurement (temporal stabilization)

```bash
python -m measurex_vision.cli video data/samples/box.mp4 \
  --detector grounding_dino --segmenter sam2 --provider depth_anything_v2 \
  --max-frames 8 --debug
```

Frames are sampled, each is measured through the same stack, and the results are
temporally stabilized into one L/W/H.

## 11. Where outputs are stored + the debug artifacts

All artifacts go to `services/vision-poc/outputs/` (override with
`MEASUREX_VISION_OUTPUT_DIR`). In Lightning, open that folder in the file browser
to view the PNGs, or download the folder. A `--debug` image run writes:

| Requirement in the brief   | File(s) written to `outputs/`                                   |
| -------------------------- | --------------------------------------------------------------- |
| detection overlay          | `mask_overlay.png` (the green box is the Grounding DINO detection) |
| segmentation mask          | `mask.npy` (boolean) + the green tint in `mask_overlay.png`      |
| depth map                  | `depth_color.png` + `depth_raw.npy`                              |
| masked depth               | `depth_masked_color.png` + `depth_masked.npy`                    |
| point cloud                | `points.npy` (masked 3-D points, metres)                         |
| final measurement overlay  | `mask_overlay.png` (box + mask on the input image)               |
| measurement.json           | `measurement.json` (the full success/failure payload)           |
| (extra) depth diagnostics  | `diagnostics.json`, `cloud_diagnostics.json`, `image.png`        |

> Note: the engine writes **one** combined overlay (`mask_overlay.png`) that shows
> both the detection box and the segmentation mask on the input image; it is not
> split into three separate overlay files. This is unchanged by the runtime — do
> not modify the engine to produce extra overlays.

## 12. Run the M5 benchmark

Populate a manifest with physically measured integer-mm ground truth (start from
`data/benchmark-manifest.example.csv`; see [`../data/README.md`](../data/README.md)),
place the media at the paths it references, then:

```bash
python scripts/benchmark.py data/benchmark/manifest.csv \
  --detector grounding_dino --segmenter sam2 --provider depth_anything_v2 \
  --false-success-tolerance-pct 10 \
  --output-dir outputs/benchmark
```

Reports (`results.csv`, `summary.json`, error-distribution and grouped SVG charts,
single- vs multi-frame comparison, failure-code counts) land in
`outputs/benchmark/`.

---

## Shortest path to your first real L/W/H in Lightning AI

From a fresh GPU Studio terminal (base environment, with its CUDA torch), with a
`box.jpg` ready to drag in:

```bash
git clone https://github.com/Shaikhabdulaleem/MeasureX.git
cd MeasureX && git checkout main && cd services/vision-poc
pip install --upgrade pip && pip install -e ".[dev,seg,depth]"
python -c "import cv2" 2>/dev/null || pip install "opencv-python-headless>=4.9"
python - <<'PY'
from huggingface_hub import hf_hub_download
hf_hub_download("facebook/sam2.1-hiera-small", "sam2.1_hiera_small.pt", local_dir="weights")
PY
export MEASUREX_SAM2_CHECKPOINT="$PWD/weights/sam2.1_hiera_small.pt"
export MEASUREX_SAM2_CONFIG="configs/sam2.1/sam2.1_hiera_s.yaml"
python scripts/check_gpu_environment.py            # expect READY
mkdir -p data/samples                              # drag box.jpg into data/samples/
python -m measurex_vision.cli image data/samples/box.jpg \
  --detector grounding_dino --segmenter sam2 --provider depth_anything_v2 --debug
```

The last command prints your first real MeasureX L/W/H (in `dimensions`), with
confidence, `timing_ms` and diagnostics, and writes the artifacts to `outputs/`.
