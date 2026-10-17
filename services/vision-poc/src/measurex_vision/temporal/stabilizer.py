"""TemporalStabilizer provider interface — fuse per-frame dimensions.

The concrete robust-statistics implementation uses median, MAD outlier rejection
and per-dimension spread reporting.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..contracts import Dimensions


@dataclass(frozen=True)
class StabilizedDimensions:
    dimensions: Dimensions       # stabilized L/W/H
    spread_mm: dict[str, int]    # {"length", "width", "height"} spread across frames
    frame_count: int             # number of accepted frames


class TemporalStabilizer(ABC):
    @abstractmethod
    def stabilize(self, per_frame: list[Dimensions]) -> StabilizedDimensions:
        """Combine per-frame dimensions into one stabilized result with spread."""
