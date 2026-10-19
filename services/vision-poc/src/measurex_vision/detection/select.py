"""Pure target-selection helpers — no models, fully testable.

Grounding DINO can emit several overlapping boxes for one object (e.g. a `box`
and a `carton` hit on the same carton). Dedupe those, then decide whether there
is one clear shipment or genuinely multiple (VISION_ENGINE_POC.md §2: never
silently pick between two similarly strong targets)."""

from __future__ import annotations

from .base import Detection


def iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    """Intersection-over-union of two xyxy boxes."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def dedupe(detections: list[Detection], iou_thresh: float = 0.6) -> list[Detection]:
    """NMS-style merge: keep the highest-scoring box of each overlapping cluster."""
    kept: list[Detection] = []
    for det in sorted(detections, key=lambda d: d.score, reverse=True):
        if all(iou(det.bbox_xyxy, k.bbox_xyxy) < iou_thresh for k in kept):
            kept.append(det)
    return kept


def classify_target(
    detections: list[Detection],
    *,
    ambiguous_ratio: float = 0.8,
    iou_thresh: float = 0.6,
) -> tuple[str, Detection | None]:
    """Return ("none"|"single"|"multiple", target).

    A second *distinct* box scoring >= ambiguous_ratio x the top score means two
    plausible shipments -> "multiple" (caller returns MULTIPLE_TARGETS)."""
    kept = dedupe(detections, iou_thresh)
    if not kept:
        return "none", None
    kept.sort(key=lambda d: d.score, reverse=True)
    top = kept[0]
    if any(other.score >= ambiguous_ratio * top.score for other in kept[1:]):
        return "multiple", None
    return "single", top
