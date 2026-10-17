"""Depth Pro metric-depth provider (Apple ml-depth-pro).

NOTE: Depth Pro weights are Apple-ASCL (research only, no commercial use) — see
MODELS.md. Used for the POC/benchmark baseline, never a production path.

torch and the ``depth_pro`` package are heavy and GPU-oriented, so they are
imported lazily inside ``estimate`` — importing this module (and running CI)
needs neither.
"""

from __future__ import annotations

import os

import numpy as np

from .base import DepthEstimator, DepthResult


class DepthProEstimator(DepthEstimator):
    def __init__(self, checkpoint_path: str | None = None, device: str = "auto") -> None:
        self.checkpoint_path = checkpoint_path or os.environ.get("MEASUREX_DEPTH_CHECKPOINT")
        self.device = device
        self._model = None
        self._transform = None
        self._device = None

    def _resolve_device(self) -> str:
        if self.device != "auto":
            return self.device
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    def _load(self) -> None:
        if self._model is not None:
            return
        import depth_pro  # type: ignore[import-not-found]
        import torch

        config = depth_pro.depth_pro.DEFAULT_MONODEPTH_CONFIG_DICT
        if self.checkpoint_path:
            config.checkpoint_uri = self.checkpoint_path
        model, transform = depth_pro.create_model_and_transforms(config=config)
        model.eval()
        self._device = self._resolve_device()
        self._model = model.to(self._device)
        self._transform = transform
        self._torch = torch

    def estimate(self, image: np.ndarray) -> DepthResult:
        self._load()
        assert self._model is not None and self._transform is not None
        # infer() does not move its input, so match the model's device.
        x = self._transform(image).to(self._device)
        with self._torch.no_grad():
            prediction = self._model.infer(x)
        depth_m = np.asarray(prediction["depth"].cpu(), dtype=float)
        focal_px = float(prediction["focallength_px"])
        valid = np.isfinite(depth_m) & (depth_m > 0)
        valid_ratio = float(valid.mean()) if depth_m.size else 0.0
        version = os.path.basename(self.checkpoint_path) if self.checkpoint_path else "depth_pro"
        return DepthResult(
            depth_m=depth_m,
            focal_px=focal_px,
            valid_ratio=valid_ratio,
            version=version,
        )

    def release(self) -> None:
        """Drop the loaded model to free RAM/VRAM (low-memory pipeline mode)."""
        from .._memory import free_torch_memory

        self._model = None
        self._transform = None
        free_torch_memory()
