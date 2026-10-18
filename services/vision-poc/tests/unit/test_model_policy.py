"""Tests for the model/license metadata and the production-use gate (M8 Step 6).

Two concepts are kept separate: ``commercial_use`` (commercially licensed) and
``production_approved`` (approved for real production measurement). A provider
can be the former without the latter."""

from __future__ import annotations

import pytest

from measurex_vision.depth import get_depth_estimator
from measurex_vision.detection import get_detector
from measurex_vision.models import (
    MODEL_REGISTRY,
    PRODUCTION_STACK,
    ProductionPolicyError,
    assert_production_approved,
    get_metadata,
)
from measurex_vision.segmentation import get_segmenter


def test_depth_pro_is_never_production_approved():
    assert MODEL_REGISTRY["depth_pro"].production_approved is False
    assert MODEL_REGISTRY["depth_pro"].commercial_use is False


def test_approved_production_stack_members():
    for key in ("grounding_dino", "sam2", "depth_anything_v2"):
        meta = MODEL_REGISTRY[key]
        assert meta.production_approved is True
        assert meta.commercial_use is True


def test_model_free_is_licensed_but_not_production_approved():
    # central_candidate / box_mask are commercially unencumbered (model-free) yet
    # are dev/CI/synthetic aids — never approved for real production measurement.
    for key in ("central_candidate", "box_mask"):
        meta = MODEL_REGISTRY[key]
        assert meta.commercial_use is True
        assert meta.production_approved is False


def test_assert_rejects_research_only_model():
    with pytest.raises(ProductionPolicyError):
        assert_production_approved("depth_pro")


def test_assert_rejects_model_free_fallbacks():
    for key in ("central_candidate", "box_mask"):
        with pytest.raises(ProductionPolicyError):
            assert_production_approved(key)


def test_assert_allows_approved_models():
    for key in PRODUCTION_STACK.values():
        assert assert_production_approved(key).key == key


def test_unknown_key_raises_value_error():
    with pytest.raises(ValueError):
        get_metadata("totally_made_up")


def test_registry_gate_blocks_depth_pro_in_production():
    with pytest.raises(ProductionPolicyError):
        get_depth_estimator("depth_pro", production=True)


def test_registry_gate_blocks_central_candidate_in_production():
    with pytest.raises(ProductionPolicyError):
        get_detector("central_candidate", production=True)


def test_registry_gate_blocks_box_mask_in_production():
    with pytest.raises(ProductionPolicyError):
        get_segmenter("box_mask", production=True)


def test_registry_gate_allows_depth_pro_outside_production():
    # Research/benchmark path stays usable (lazy construction, no torch import).
    est = get_depth_estimator("depth_pro", production=False, checkpoint_path="/nonexistent.pt")
    assert type(est).__name__ == "DepthProEstimator"


def test_every_metadata_separates_checkpoint_license():
    # Checkpoint/weight license is recorded separately from code license.
    for meta in MODEL_REGISTRY.values():
        assert meta.checkpoint_license
        assert meta.code_license


def test_approved_models_pin_an_exact_revision():
    # Production models must freeze a concrete revision — not "record on download".
    for key in PRODUCTION_STACK.values():
        rev = MODEL_REGISTRY[key].revision
        assert rev and rev != "n/a"
        assert "download" not in rev.lower()
        assert len(rev) >= 12  # a real commit hash, not a placeholder
