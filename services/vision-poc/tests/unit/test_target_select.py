"""Tests for pure target-selection helpers (iou, dedupe, classify_target)."""

from __future__ import annotations

from measurex_vision.detection import classify_target, dedupe, iou
from measurex_vision.detection.base import Detection


def _d(box, score, label="box"):
    return Detection(bbox_xyxy=box, score=score, label=label, reason="test")


def test_iou():
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    # Half-overlap on x: inter 50, union 150 -> 1/3
    assert abs(iou((0, 0, 10, 10), (5, 0, 15, 10)) - (50 / 150)) < 1e-9


def test_dedupe_merges_overlapping_keeps_highest():
    dets = [_d((0, 0, 10, 10), 0.6, "box"), _d((1, 1, 11, 11), 0.9, "carton")]
    kept = dedupe(dets, iou_thresh=0.6)
    assert len(kept) == 1
    assert kept[0].score == 0.9  # the carton hit on the same object wins


def test_dedupe_keeps_distinct():
    dets = [_d((0, 0, 10, 10), 0.9), _d((100, 100, 110, 110), 0.8)]
    assert len(dedupe(dets)) == 2


def test_classify_none_single_multiple():
    assert classify_target([]) == ("none", None)

    kind, target = classify_target([_d((0, 0, 10, 10), 0.9)])
    assert kind == "single" and target is not None

    # Two distinct, both strong -> multiple.
    kind, target = classify_target(
        [_d((0, 0, 10, 10), 0.9), _d((100, 100, 120, 120), 0.85)]
    )
    assert kind == "multiple" and target is None

    # A weak second target (< 0.8 x top) -> still single.
    kind, target = classify_target(
        [_d((0, 0, 10, 10), 0.9), _d((100, 100, 120, 120), 0.3)]
    )
    assert kind == "single" and target.score == 0.9


def test_classify_overlapping_strong_is_single():
    # Two overlapping strong boxes on one object dedupe to one -> single.
    kind, target = classify_target([_d((0, 0, 10, 10), 0.9), _d((1, 1, 11, 11), 0.88)])
    assert kind == "single" and target is not None
