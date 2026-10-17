"""SAM 2 segmenter (Apache-2.0, commercial OK — MODELS.md).

torch and the sam2 package are imported lazily so importing this module needs
neither."""

from __future__ import annotations

import os

import numpy as np

from .base import Segmenter


class Sam2Segmenter(Segmenter):
    def __init__(self, checkpoint_path: str | None = None, model_cfg: str | None = None,
                 device: str = "auto") -> None:
        self.checkpoint_path = checkpoint_path or os.environ.get("MEASUREX_SAM2_CHECKPOINT")
        self.model_cfg = model_cfg or os.environ.get("MEASUREX_SAM2_CONFIG")
        self.device = device
        self._predictor = None

    def _resolve_device(self) -> str:
        if self.device != "auto":
            return self.device
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"

    def _load(self) -> None:
        if self._predictor is not None:
            return
        from sam2.build_sam import build_sam2  # type: ignore[import-not-found]
        from sam2.sam2_image_predictor import SAM2ImagePredictor  # type: ignore[import-not-found]

        model = build_sam2(self.model_cfg, self.checkpoint_path, device=self._resolve_device())
        self._predictor = SAM2ImagePredictor(model)

    def segment(self, image: np.ndarray, box_xyxy: tuple[float, float, float, float]) -> np.ndarray:
        self._load()
        assert self._predictor is not None
        self._predictor.set_image(image)
        masks, scores, _ = self._predictor.predict(
            box=np.asarray(box_xyxy, dtype=float)[None, :], multimask_output=False
        )
        # masks: (1, H, W) for a single box; take the best.
        best = int(np.argmax(scores))
        return np.asarray(masks[best], dtype=bool)

    def release(self) -> None:
        """Drop the loaded model to free RAM/VRAM (low-memory pipeline mode)."""
        from .._memory import free_torch_memory

        self._predictor = None
        free_torch_memory()
