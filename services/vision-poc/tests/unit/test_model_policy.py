"""Tests for the model/license metadata and the production-use gate (M8 Step 6)."""

from __future__ import annotations

import pytest

from measurex_vision.depth import get_depth_estimator
from measurex_vision.models import (
    MODEL_REGISTRY,
    ProductionPolicyError,
    assert_production_allowed,
    get_metadata,
)


def test_depth_pro_is_never_production_allowed():
    assert MODEL_REGISTRY["depth_pro"].production_allowed is False
    assert MODEL_REGISTRY["depth_pro"].commercial_use is False


def test_depth_anything_v2_is_production_allowed():
    meta = MODEL_REGISTRY["depth_anything_v2"]
    assert meta.production_allowed is True
    assert meta.commercial_use is True


def test_assert_rejects_research_only_model():
    with pytest.raises(ProductionPolicyError):
        assert_production_allowed("depth_pro")


def test_assert_allows_commercial_model():
    assert assert_production_allowed("depth_anything_v2").key == "depth_anything_v2"


def test_unknown_key_raises_value_error():
    with pytest.raises(ValueError):
        get_metadata("totally_made_up")


def test_registry_gate_blocks_depth_pro_in_production():
    # The registry refuses a non-production model before constructing it.
    with pytest.raises(ProductionPolicyError):
        get_depth_estimator("depth_pro", production=True)


def test_registry_gate_allows_depth_pro_outside_production():
    # Research/benchmark path stays usable (lazy construction, no torch import).
    est = get_depth_estimator("depth_pro", production=False, checkpoint_path="/nonexistent.pt")
    assert type(est).__name__ == "DepthProEstimator"


def test_every_metadata_separates_checkpoint_license():
    # Checkpoint/weight license is recorded separately from code license.
    for meta in MODEL_REGISTRY.values():
        assert meta.checkpoint_license
        assert meta.code_license
