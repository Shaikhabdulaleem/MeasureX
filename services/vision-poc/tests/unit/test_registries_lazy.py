"""Model-backed providers must construct without importing torch/model packages."""

from __future__ import annotations

import sys

import pytest

from measurex_vision.detection import get_detector
from measurex_vision.segmentation import get_segmenter


def test_sam2_constructs_without_torch():
    seg = get_segmenter("sam2", checkpoint_path="/nonexistent.pt")
    assert type(seg).__name__ == "Sam2Segmenter"
    assert "torch" not in sys.modules
    assert "sam2" not in sys.modules


def test_grounding_dino_constructs_without_torch():
    det = get_detector("grounding_dino", checkpoint_path="/nonexistent.pth")
    assert type(det).__name__ == "GroundingDinoDetector"
    assert "torch" not in sys.modules


def test_unknown_names_raise():
    with pytest.raises(ValueError):
        get_segmenter("nope")
    with pytest.raises(ValueError):
        get_detector("nope")
