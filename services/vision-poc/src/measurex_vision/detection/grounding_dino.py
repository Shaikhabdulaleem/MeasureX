"""Grounding DINO open-vocabulary detector — the shipment target proposer.

Apache-2.0 (code + weights). Runs via `transformers`
(`AutoModelForZeroShotObjectDetection`, default `IDEA-Research/grounding-dino-tiny`)
so there are no CUDA-compiled custom ops. torch + transformers are imported
lazily — importing this module needs neither.
"""

from __future__ import annotations

import numpy as np

from .base import Detection, Detector

# Lowercase, period-separated, trailing period (required by Grounding DINO).
DEFAULT_PROMPT = "box. carton. parcel. package. pallet. shipment."


class GroundingDinoDetector(Detector):
    def __init__(
        self,
        model_id: str = "IDEA-Research/grounding-dino-tiny",
        prompt: str = DEFAULT_PROMPT,
        box_threshold: float = 0.35,
        text_threshold: float = 0.25,
        device: str = "auto",
    ) -> None:
        self.model_id = model_id
        self.prompt = prompt
        self.box_threshold = box_threshold
        self.text_threshold = text_threshold
        self.device = device
        self._model = None
        self._processor = None
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
        import torch
        from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor

        self._device = self._resolve_device()
        self._processor = AutoProcessor.from_pretrained(self.model_id)
        self._model = AutoModelForZeroShotObjectDetection.from_pretrained(self.model_id).to(
            self._device
        )
        self._torch = torch

    def detect(self, image: np.ndarray) -> list[Detection]:
        from PIL import Image

        self._load()
        assert self._processor is not None and self._model is not None
        pil = Image.fromarray(np.asarray(image, dtype=np.uint8))
        inputs = self._processor(images=pil, text=self.prompt, return_tensors="pt").to(self._device)
        with self._torch.no_grad():
            outputs = self._model(**inputs)
        post = self._processor.post_process_grounded_object_detection
        kwargs = {"text_threshold": self.text_threshold, "target_sizes": [pil.size[::-1]]}
        try:
            # transformers >= 4.51 renamed box_threshold -> threshold.
            results = post(outputs, inputs["input_ids"], threshold=self.box_threshold, **kwargs)[0]
        except TypeError:
            results = post(outputs, inputs["input_ids"], box_threshold=self.box_threshold, **kwargs)[0]

        detections: list[Detection] = []
        labels = results.get("labels") or results.get("text_labels") or []
        for box, score, label in zip(results["boxes"], results["scores"], labels):
            x0, y0, x1, y1 = (float(v) for v in box.tolist())
            detections.append(
                Detection(
                    bbox_xyxy=(x0, y0, x1, y1),
                    score=float(score),
                    label=str(label),
                    reason="grounding_dino",
                )
            )
        return detections

    def select_target(self, detections: list[Detection]) -> Detection:
        if not detections:
            raise ValueError("no detections to select from")
        return max(detections, key=lambda d: d.score)

    def release(self) -> None:
        """Drop the loaded model to free RAM/VRAM (low-memory pipeline mode)."""
        from .._memory import free_torch_memory

        self._model = None
        self._processor = None
        free_torch_memory()
