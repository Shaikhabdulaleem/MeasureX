"""Depth Anything V2 (Metric, Small) depth provider — commercial-path candidate.

Apache-2.0 (confirm the exact checkpoint). ~100 MB, so the full GDINO + SAM 2 +
depth stack fits a free GPU, unlike Depth Pro. Runs via `transformers`
(`AutoModelForDepthEstimation`); torch + transformers are imported lazily.

Unlike Depth Pro, DA-V2 does **not** predict focal length, so we assume a camera
horizontal field of view (default 65 deg, typical phone main camera) and record
it in the result version. This affects the lateral (L/W) scale; height comes from
the metric depth. Calibrate per device later.
"""

from __future__ import annotations

import math

import numpy as np

from ..models import get_metadata
from .base import DepthEstimator, DepthResult

_META = get_metadata("depth_anything_v2")


class DepthAnythingV2Estimator(DepthEstimator):
    def __init__(
        self,
        model_id: str = _META.model_id,
        hfov_deg: float = 65.0,
        device: str = "auto",
        checkpoint_path: str | None = None,  # accepted for CLI parity; unused (HF model_id)
        revision: str = _META.revision,  # pinned HF commit — no silent main download
    ) -> None:
        self.model_id = model_id
        self.revision = revision
        self.hfov_deg = hfov_deg
        self.device = device
        self._model = None
        self._processor = None
        self._device = None

    def _resolve_device(self) -> str:
        if self.device != "auto":
            return self.device
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"

    def _load(self) -> None:
        if self._model is not None:
            return
        import torch
        from transformers import AutoImageProcessor, AutoModelForDepthEstimation

        self._device = self._resolve_device()
        self._processor = AutoImageProcessor.from_pretrained(self.model_id, revision=self.revision)
        self._model = AutoModelForDepthEstimation.from_pretrained(
            self.model_id, revision=self.revision
        ).to(self._device)
        self._torch = torch

    def estimate(self, image: np.ndarray) -> DepthResult:
        from PIL import Image

        self._load()
        assert self._model is not None and self._processor is not None
        pil = Image.fromarray(np.asarray(image, dtype=np.uint8))
        h, w = image.shape[:2]
        inputs = self._processor(images=pil, return_tensors="pt").to(self._device)
        with self._torch.no_grad():
            outputs = self._model(**inputs)

        try:
            post = self._processor.post_process_depth_estimation(outputs, target_sizes=[(h, w)])
            depth = post[0]["predicted_depth"]
        except (AttributeError, KeyError, TypeError):
            depth = self._torch.nn.functional.interpolate(
                outputs.predicted_depth.unsqueeze(1), size=(h, w), mode="bilinear", align_corners=False
            )[0, 0]

        depth_m = np.asarray(depth.detach().cpu(), dtype=float)
        focal_px = (w / 2.0) / math.tan(math.radians(self.hfov_deg / 2.0))
        valid = np.isfinite(depth_m) & (depth_m > 0)
        valid_ratio = float(valid.mean()) if depth_m.size else 0.0
        return DepthResult(
            depth_m=depth_m,
            focal_px=focal_px,
            valid_ratio=valid_ratio,
            version=f"{self.model_id}@{self.revision[:12]} (hfov={self.hfov_deg}deg)",
            focal_is_assumed=True,  # focal comes from an assumed FOV, not prediction
        )

    def release(self) -> None:
        from .._memory import free_torch_memory

        self._model = None
        self._processor = None
        free_torch_memory()
