"""Tests for the pure depth debug-export logic (no model/GPU)."""

from __future__ import annotations

import json

import numpy as np

from measurex_vision.depth.base import DepthResult
from measurex_vision.visualization import (
    colorize_depth,
    overlay_mask,
    save_cloud_artifacts,
    save_depth_artifacts,
)


def test_colorize_all_invalid_is_black():
    depth = np.full((4, 5), np.nan)
    out = colorize_depth(depth)
    assert out.shape == (4, 5, 3)
    assert out.dtype == np.uint8
    assert out.sum() == 0


def test_colorize_valid_gradient():
    depth = np.linspace(1.0, 2.0, 20, dtype=float).reshape(4, 5)
    out = colorize_depth(depth)
    assert out.shape == (4, 5, 3)
    assert out.dtype == np.uint8
    # Near and far ends map to different colours.
    assert not np.array_equal(out[0, 0], out[-1, -1])


def test_colorize_marks_nonpositive_invalid():
    depth = np.array([[1.0, 0.0], [-2.0, 2.0]])
    out = colorize_depth(depth)
    assert out[0, 1].sum() == 0  # zero depth -> black
    assert out[1, 0].sum() == 0  # negative depth -> black
    assert out[1, 1].sum() > 0  # valid -> coloured


def test_save_depth_artifacts(tmp_path, sample_image):
    depth = DepthResult(
        depth_m=np.linspace(1.0, 3.0, sample_image[..., 0].size, dtype=float).reshape(
            sample_image.shape[:2]
        ),
        focal_px=1234.0,
        valid_ratio=1.0,
        version="mock",
    )
    mask = np.zeros(sample_image.shape[:2], dtype=bool)
    mask[2:5, 3:7] = True

    paths = save_depth_artifacts(str(tmp_path), sample_image, depth, mask=mask)

    for name in (
        "image.png",
        "depth_color.png",
        "depth_raw.npy",
        "depth_masked.npy",
        "depth_masked_color.png",
        "diagnostics.json",
    ):
        assert name in paths
        assert (tmp_path / name).exists()

    diag = json.loads((tmp_path / "diagnostics.json").read_text())
    assert diag["focal_px"] == 1234.0
    assert diag["version"] == "mock"
    assert diag["depth_shape"] == list(sample_image.shape[:2])


def test_save_depth_artifacts_without_mask(tmp_path, sample_image, mock_estimator):
    depth = mock_estimator.estimate(sample_image)
    paths = save_depth_artifacts(str(tmp_path), sample_image, depth)
    assert "depth_masked.npy" not in paths
    assert (tmp_path / "depth_color.png").exists()


def test_overlay_and_cloud_artifacts(tmp_path, sample_image):
    mask = np.zeros(sample_image.shape[:2], dtype=bool)
    mask[2:6, 3:9] = True
    overlay = overlay_mask(sample_image, mask, bbox_xyxy=(3, 2, 9, 6))
    assert overlay.shape == sample_image.shape
    assert overlay.dtype == np.uint8

    points = np.random.default_rng(0).normal(size=(120, 3))
    save_cloud_artifacts(
        str(tmp_path), sample_image, mask, points, bbox_xyxy=(3, 2, 9, 6),
        diagnostics={"mask_area_ratio": float(mask.mean())},
    )
    for name in ("mask_overlay.png", "mask.npy", "points.npy", "cloud_diagnostics.json"):
        assert (tmp_path / name).exists()
    diag = json.loads((tmp_path / "cloud_diagnostics.json").read_text())
    assert diag["point_count"] == 120
