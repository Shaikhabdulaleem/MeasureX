# Kaggle GPU fallback — MeasureX Vision POC validation

Use this **only if Google Colab will not allocate a GPU**. It runs the *same*
repository, models, test data, benchmark commands, and output format as
`notebooks/MeasureX_GPU_Validation.ipynb` — there is **no separate Kaggle
implementation**. Only the environment setup and file upload differ.

## 1. Create the notebook and enable GPU + Internet

1. kaggle.com → **Create → New Notebook**.
2. Right panel → **Settings → Accelerator → GPU** (T4 x2 or P100).
3. Right panel → **Settings → Internet → On** (required to clone the repo and
   download weights).

## 2. Same steps as the Colab notebook

Run these in notebook cells (identical to the Colab notebook, Kaggle working dir
is `/kaggle/working`):

```python
# GPU verify
!nvidia-smi
import torch; assert torch.cuda.is_available(), "No GPU — Settings > Accelerator > GPU"
print(torch.__version__, torch.cuda.get_device_name(0), torch.cuda.device_count())
```

```bash
%cd /kaggle/working
!rm -rf MeasureX
!git clone https://github.com/Shaikhabdulaleem/MeasureX.git
%cd MeasureX/services/vision-poc
!git checkout main
!pip install -q -e ".[depth,seg]"
```

```python
# Weights (research-only Depth Pro + Apache-2.0 SAM 2.1)
import os
os.makedirs("weights", exist_ok=True)
!python scripts/download_models.py
!wget -q -O weights/sam2.1_hiera_large.pt https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_large.pt
root = "/kaggle/working/MeasureX/services/vision-poc"
os.environ["MEASUREX_DEPTH_CHECKPOINT"] = f"{root}/weights/depth_pro.pt"
os.environ["MEASUREX_SAM2_CHECKPOINT"]  = f"{root}/weights/sam2.1_hiera_large.pt"
os.environ["MEASUREX_SAM2_CONFIG"]      = "configs/sam2.1/sam2.1_hiera_l.yaml"
os.environ["MEASUREX_VISION_OUTPUT_DIR"] = f"{root}/outputs"
for p in [os.environ["MEASUREX_DEPTH_CHECKPOINT"], os.environ["MEASUREX_SAM2_CHECKPOINT"]]:
    assert os.path.getsize(p) > 1_000_000, f"weight missing: {p}"
```

## 3. Upload your box photo/video (the only real difference from Colab)

Kaggle has no `files.upload()` widget. Instead:

1. **+ Add Data → Upload** → upload your JPG(s) and MP4 → it mounts read-only
   under `/kaggle/input/<your-dataset>/`.
2. Point the pipeline at them:

```python
import glob
img = (glob.glob("/kaggle/input/**/*.jpg", recursive=True)
       + glob.glob("/kaggle/input/**/*.png", recursive=True))[0]
vid = glob.glob("/kaggle/input/**/*.mp4", recursive=True)[0]
!python -m measurex_vision.cli image "$img" --provider depth_pro --segmenter sam2 --debug
!python -m measurex_vision.cli video "$vid" --provider depth_pro --segmenter sam2 --debug
```

## 4. Ground truth + benchmark (same as Colab)

```python
import csv, os, shutil, json
L, W, H = 600, 400, 350   # EDIT to your tape-measured mm (length >= width)
os.makedirs("data/benchmark/BOX_001", exist_ok=True)
json.dump({"object_id":"BOX_001","category":"carton","length_mm":L,"width_mm":W,"height_mm":H},
          open("data/benchmark/BOX_001/ground_truth.json","w"), indent=2)
base = "data/benchmark/objects/BOX_001/phoneA"; os.makedirs(base, exist_ok=True)
shutil.copy(img, f"{base}/image_001.jpg"); shutil.copy(vid, f"{base}/video_001.mp4")
with open("data/benchmark/manifest.csv","w",newline="") as fh:
    w=csv.writer(fh)
    w.writerow(["sample_id","object_id","category","phone_model","capture_type","file_path",
                "gt_length_mm","gt_width_mm","gt_height_mm","lighting","distance_band","notes"])
    w.writerow(["BOX_001_IMG_001","BOX_001","medium","phoneA","image","objects/BOX_001/phoneA/image_001.jpg",L,W,H,"warehouse","near","real box"])
    w.writerow(["BOX_001_VID_001","BOX_001","medium","phoneA","video","objects/BOX_001/phoneA/video_001.mp4",L,W,H,"warehouse","near","real box"])
!python scripts/benchmark.py data/benchmark/manifest.csv --false-success-tolerance-pct 10
print(open("outputs/benchmark/summary.json").read())
```

## 5. Results

Same as Colab: per-run artifacts and `measurement.json` under `outputs/`,
benchmark `results.csv` / `summary.json` / SVG charts under `outputs/benchmark/`.
Download via the Kaggle **Output** tab (files under `/kaggle/working` persist as
notebook output). Record the numbers in `docs/REAL_GPU_VALIDATION_REPORT.md`.

Models and their licenses are unchanged from Colab — Depth Pro is
**research-only**; see `MODELS.md`.
