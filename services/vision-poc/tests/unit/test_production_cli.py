"""The ``--production`` CLI resolves the approved stack and gates research models.

Resolution and the registry gate are pure/lazy (no torch, no weights), so these
run in CI."""

from __future__ import annotations

import pytest

from measurex_vision.cli import (
    _depth_provider,
    _detector_name,
    _segmenter_name,
    build_parser,
)
from measurex_vision.depth import get_depth_estimator
from measurex_vision.detection import get_detector
from measurex_vision.models import ProductionPolicyError
from measurex_vision.segmentation import get_segmenter


def _args(*extra: str):
    return build_parser().parse_args(["image", "box.jpg", *extra])


def test_production_resolves_approved_stack():
    args = _args("--production")
    assert _detector_name(args) == "grounding_dino"
    assert _segmenter_name(args) == "sam2"
    assert _depth_provider(args) == "depth_anything_v2"


def test_non_production_defaults_to_dev_fallback():
    args = _args()
    assert _detector_name(args) == "central_candidate"
    assert _segmenter_name(args) == "sam2"
    assert _depth_provider(args) == "depth_pro"


def test_production_cannot_load_depth_pro():
    # Explicitly forcing the research model under --production is refused.
    args = _args("--production", "--provider", "depth_pro")
    with pytest.raises(ProductionPolicyError):
        get_depth_estimator(_depth_provider(args), production=args.production)


def test_production_cannot_use_central_candidate():
    args = _args("--production", "--detector", "central_candidate")
    with pytest.raises(ProductionPolicyError):
        get_detector(_detector_name(args), production=args.production)


def test_production_cannot_use_box_mask():
    args = _args("--production", "--segmenter", "box_mask")
    with pytest.raises(ProductionPolicyError):
        get_segmenter(_segmenter_name(args), production=args.production)
