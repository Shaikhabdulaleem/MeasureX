"""Robust temporal stabilization of per-frame dimensions.

Fuse several noisy single-frame L/W/H into one stable measurement: reject
outlier frames (MAD), take the per-dimension median, and report the spread
(VISION_ENGINE_POC.md §8). Pure — no model/GPU."""

from __future__ import annotations

import numpy as np

from ..contracts import Dimensions
from .stabilizer import StabilizedDimensions, TemporalStabilizer

_DIMS = ("length_mm", "width_mm", "height_mm")


class RobustTemporalStabilizer(TemporalStabilizer):
    def __init__(self, mad_k: float = 3.0) -> None:
        self.mad_k = mad_k

    def _inliers(self, values: np.ndarray) -> np.ndarray:
        """Boolean mask of frames within mad_k scaled-MAD of the per-dim median."""
        keep = np.ones(values.shape[0], dtype=bool)
        for col in range(values.shape[1]):
            v = values[:, col]
            med = np.median(v)
            mad = np.median(np.abs(v - med)) * 1.4826
            if mad > 0:
                keep &= np.abs(v - med) <= self.mad_k * mad
            else:
                # Degenerate agreement (majority identical): anything off the
                # median is an outlier.
                keep &= v == med
        return keep

    def stabilize(self, per_frame: list[Dimensions]) -> StabilizedDimensions:
        if not per_frame:
            raise ValueError("per_frame must be non-empty")
        values = np.array([[getattr(d, name) for name in _DIMS] for d in per_frame], dtype=float)

        keep = self._inliers(values)
        survivors = values[keep] if keep.any() else values

        med = np.median(survivors, axis=0)
        spread = (survivors.max(axis=0) - survivors.min(axis=0)).astype(int)

        # Orientation rule: longer horizontal is length. Medians are per-dim, so
        # re-order the two horizontals to guarantee length >= width.
        length_mm, width_mm = sorted((round(float(med[0])), round(float(med[1]))), reverse=True)
        dims = Dimensions(length_mm=length_mm, width_mm=width_mm, height_mm=round(float(med[2])))
        return StabilizedDimensions(
            dimensions=dims,
            spread_mm={"length": int(spread[0]), "width": int(spread[1]), "height": int(spread[2])},
            frame_count=int(survivors.shape[0]),
        )
