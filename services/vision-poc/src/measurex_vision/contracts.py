"""Base domain contracts for the MeasureX vision POC.

These are the only values the engine returns across its boundary. Vision code
works in float metres internally; the integer-millimetre conversion happens here
and nowhere else, matching MeasureX's "integer base units" rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Union


class ConfidenceLevel(str, Enum):
    """Coarse trust buckets. Thresholds are experimental until the benchmark
    (VISION_ENGINE_POC.md §9)."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    FAILED = "failed"


class FailureCode(str, Enum):
    """Typed reasons the engine refuses to produce a measurement.

    Never invent dimensions when geometry is weak — return one of these instead
    (VISION_DECISION.md §7, CLAUDE.md "Output safety")."""

    NO_TARGET = "no_target"
    MULTIPLE_TARGETS = "multiple_targets"
    OBJECT_NOT_FULLY_VISIBLE = "object_not_fully_visible"
    SEGMENTATION_UNSTABLE = "segmentation_unstable"
    DEPTH_INVALID = "depth_invalid"
    POINTCLOUD_SPARSE = "pointcloud_sparse"
    GEOMETRY_DEGENERATE = "geometry_degenerate"
    TEMPORAL_INSTABILITY = "temporal_instability"


# Default worker-facing guidance per failure code (English baseline; i18n later).
GUIDANCE: dict[FailureCode, str] = {
    FailureCode.NO_TARGET: "No shipment detected. Point the camera at the parcel.",
    FailureCode.MULTIPLE_TARGETS: "More than one item in view. Isolate the shipment and retry.",
    FailureCode.OBJECT_NOT_FULLY_VISIBLE: "Move back until the whole shipment is visible.",
    FailureCode.SEGMENTATION_UNSTABLE: "Hold steady and keep the shipment fully in frame.",
    FailureCode.DEPTH_INVALID: "Too dark or reflective to read depth. Improve lighting and retry.",
    FailureCode.POINTCLOUD_SPARSE: "Not enough surface detail. Move a little closer and retry.",
    FailureCode.GEOMETRY_DEGENERATE: "Could not fit a box. Capture again from a slight angle.",
    FailureCode.TEMPORAL_INSTABILITY: "Readings unstable. Hold the phone steady and retry.",
}


@dataclass(frozen=True)
class Dimensions:
    """Bounding L/W/H in integer millimetres (the persisted base unit).

    Orientation rule: length = longest horizontal, width = shorter horizontal,
    height = vertical — so ``length_mm >= width_mm`` always holds.
    """

    length_mm: int
    width_mm: int
    height_mm: int

    def __post_init__(self) -> None:
        for name in ("length_mm", "width_mm", "height_mm"):
            val = getattr(self, name)
            # bool is an int subclass — reject it explicitly.
            if not isinstance(val, int) or isinstance(val, bool):
                raise TypeError(f"{name} must be int (base unit = mm), got {type(val).__name__}")
            if val < 0:
                raise ValueError(f"{name} must be >= 0")
        if self.length_mm < self.width_mm:
            raise ValueError("length_mm must be >= width_mm (orientation rule)")

    def to_dict(self) -> dict[str, int]:
        return {
            "length_mm": self.length_mm,
            "width_mm": self.width_mm,
            "height_mm": self.height_mm,
        }


# (score_at_least, level) in descending order. Experimental — not calibrated.
_LEVEL_THRESHOLDS: tuple[tuple[float, ConfidenceLevel], ...] = (
    (0.85, ConfidenceLevel.HIGH),
    (0.60, ConfidenceLevel.MEDIUM),
    (0.0, ConfidenceLevel.LOW),
)


@dataclass(frozen=True)
class Confidence:
    """A 0..1 trust score plus its coarse level."""

    score: float
    level: ConfidenceLevel

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"confidence score must be in [0, 1], got {self.score}")

    @classmethod
    def from_score(cls, score: float) -> "Confidence":
        for threshold, level in _LEVEL_THRESHOLDS:
            if score >= threshold:
                return cls(score=float(score), level=level)
        return cls(score=float(score), level=ConfidenceLevel.LOW)

    def to_dict(self) -> dict[str, Any]:
        return {"confidence": self.score, "confidence_level": self.level.value}


@dataclass
class Diagnostics:
    """Open bag of per-run evidence (depth_valid_ratio, mask_area_ratio, frame
    counts, dimension spread, assumptions made, ...). Deliberately free-form:
    the useful fields differ by pipeline stage and firm up with the benchmark."""

    assumptions: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = dict(self.extra)
        if self.assumptions:
            out["assumptions"] = list(self.assumptions)
        return out


@dataclass(frozen=True)
class MeasurementSuccess:
    """A trustworthy measurement. ``success`` is always True."""

    dimensions: Dimensions
    confidence: Confidence
    diagnostics: Diagnostics = field(default_factory=Diagnostics)
    model_versions: dict[str, str] = field(default_factory=dict)
    timing_ms: dict[str, float] = field(default_factory=dict)
    method: str = "rgb_ai"

    @property
    def success(self) -> bool:
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": True,
            "dimensions": self.dimensions.to_dict(),
            **self.confidence.to_dict(),
            "method": self.method,
            "model_versions": dict(self.model_versions),
            "timing_ms": dict(self.timing_ms),
            "diagnostics": self.diagnostics.to_dict(),
        }


@dataclass(frozen=True)
class MeasurementFailure:
    """An explicit refusal. ``success`` is always False."""

    failure_code: FailureCode
    user_guidance: str = ""
    diagnostics: Diagnostics = field(default_factory=Diagnostics)

    def __post_init__(self) -> None:
        if not self.user_guidance:
            # frozen dataclass: set via object.__setattr__
            object.__setattr__(self, "user_guidance", GUIDANCE[self.failure_code])

    @property
    def success(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": False,
            "failure_code": self.failure_code.value,
            "user_guidance": self.user_guidance,
            "diagnostics": self.diagnostics.to_dict(),
        }


# The engine returns exactly one of these.
MeasurementResult = Union[MeasurementSuccess, MeasurementFailure]
