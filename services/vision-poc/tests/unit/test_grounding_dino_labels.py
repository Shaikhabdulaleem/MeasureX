"""Grounding DINO label selection across Transformers output shapes (M8).

``_select_labels`` must prefer ``text_labels`` (transformers >= 4.51), fall back
to ``labels`` (older), and never apply a boolean test to a value that may be a
tensor — whose truth value is ambiguous and raises. numpy arrays raise the same
ambiguity, so they stand in for tensors here."""

from __future__ import annotations

import numpy as np

from measurex_vision.detection.grounding_dino import _select_labels


def test_prefers_text_labels_when_present():
    results = {"text_labels": ["box", "pallet"], "labels": ["wrong", "wrong"]}
    assert _select_labels(results, 2) == ["box", "pallet"]


def test_falls_back_to_labels_when_no_text_labels():
    assert _select_labels({"labels": ["carton"]}, 1) == ["carton"]


def test_tensor_like_labels_do_not_trigger_boolean_ambiguity():
    # A multi-element array would raise on bool(); selection must not test it.
    labels = np.array([0, 1, 2])
    out = _select_labels({"labels": labels}, 3)
    assert [int(x) for x in out] == [0, 1, 2]


def test_tensor_like_text_labels_win_over_labels():
    out = _select_labels({"text_labels": np.array([5, 6]), "labels": np.array([0, 0])}, 2)
    assert [int(x) for x in out] == [5, 6]


def test_missing_both_falls_back_to_placeholder():
    assert _select_labels({"boxes": [1, 2]}, 2) == ["object", "object"]
