"""Tests for depth provider selection and the mock depth -> artifacts path."""

from __future__ import annotations

import pytest

from measurex_vision.depth import DepthEstimator, get_depth_estimator
from measurex_vision.visualization import save_depth_artifacts


def test_depth_pro_constructs_without_torch():
    # Must not import torch/depth_pro at construction time (lazy in estimate()).
    estimator = get_depth_estimator("depth_pro", checkpoint_path="/nonexistent.pt")
    assert isinstance(estimator, DepthEstimator)
    assert type(estimator).__name__ == "DepthProEstimator"


def test_depth_anything_v2_constructs():
    est = get_depth_estimator("depth_anything_v2")
    assert isinstance(est, DepthEstimator)
    assert type(est).__name__ == "DepthAnythingV2Estimator"


def test_unknown_provider_raises():
    with pytest.raises(ValueError):
        get_depth_estimator("totally_made_up")


def test_mock_estimate_to_artifacts(tmp_path, sample_image, mock_estimator):
    depth = mock_estimator.estimate(sample_image)
    assert depth.depth_m.shape == sample_image.shape[:2]
    assert 0.0 <= depth.valid_ratio <= 1.0

    paths = save_depth_artifacts(str(tmp_path), sample_image, depth)
    assert (tmp_path / "diagnostics.json").exists()
    assert "depth_color.png" in paths
