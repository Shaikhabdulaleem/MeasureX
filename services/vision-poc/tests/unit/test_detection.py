"""Tests for the model-free central-candidate detector."""

from __future__ import annotations

import numpy as np

from measurex_vision.detection import get_detector
from measurex_vision.detection.central_candidate import CentralCandidateDetector


def test_central_candidate_box_is_centred_and_in_bounds():
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    det = CentralCandidateDetector(box_fraction=0.6)
    (d,) = det.detect(image)
    x0, y0, x1, y1 = d.bbox_xyxy
    assert (x0, y0, x1, y1) == (40.0, 20.0, 160.0, 80.0)  # 0.6 of 200x100, centred
    assert d.label == "parcel"
    assert d.reason == "central_candidate"
    assert det.select_target([d]) is d


def test_central_candidate_rejects_bad_fraction():
    import pytest

    with pytest.raises(ValueError):
        CentralCandidateDetector(box_fraction=0.0)


def test_registry_returns_central_candidate():
    det = get_detector("central_candidate")
    assert isinstance(det, CentralCandidateDetector)
