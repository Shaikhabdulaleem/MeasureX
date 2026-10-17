"""Pipeline target handling: none / single / multiple shipments."""

from __future__ import annotations

import numpy as np

from measurex_vision.contracts import FailureCode, MeasurementFailure
from measurex_vision.detection.base import Detection, Detector
from measurex_vision.pipeline import MaskedCloud, build_masked_cloud
from measurex_vision.segmentation.box_mask import BoxMaskSegmenter


class FakeDetector(Detector):
    def __init__(self, detections):
        self._detections = detections

    def detect(self, image):
        return self._detections

    def select_target(self, detections):
        return max(detections, key=lambda d: d.score)


def _det(box, score):
    return Detection(bbox_xyxy=box, score=score, label="box", reason="fake")


def test_no_target(mock_estimator):
    image = np.zeros((60, 80, 3), dtype=np.uint8)
    out = build_masked_cloud(
        image, detector=FakeDetector([]), segmenter=BoxMaskSegmenter(), depth=mock_estimator
    )
    assert isinstance(out, MeasurementFailure)
    assert out.failure_code is FailureCode.NO_TARGET


def test_multiple_targets(mock_estimator):
    image = np.zeros((60, 80, 3), dtype=np.uint8)
    dets = [_det((5, 5, 30, 30), 0.90), _det((45, 30, 75, 55), 0.88)]  # two distinct, strong
    out = build_masked_cloud(
        image, detector=FakeDetector(dets), segmenter=BoxMaskSegmenter(), depth=mock_estimator
    )
    assert isinstance(out, MeasurementFailure)
    assert out.failure_code is FailureCode.MULTIPLE_TARGETS


def test_single_target_proceeds(mock_estimator):
    image = np.zeros((60, 80, 3), dtype=np.uint8)
    dets = [_det((5, 5, 70, 55), 0.90)]  # one clear box
    out = build_masked_cloud(
        image, detector=FakeDetector(dets), segmenter=BoxMaskSegmenter(), depth=mock_estimator
    )
    assert isinstance(out, MaskedCloud)


class ReleasableDetector(FakeDetector):
    released = False

    def release(self):
        self.released = True


def test_release_models_frees_the_model(mock_estimator):
    image = np.zeros((60, 80, 3), dtype=np.uint8)
    det = ReleasableDetector([_det((5, 5, 70, 55), 0.90)])
    out = build_masked_cloud(
        image, detector=det, segmenter=BoxMaskSegmenter(), depth=mock_estimator, release_models=True
    )
    assert isinstance(out, MaskedCloud)
    assert det.released is True
