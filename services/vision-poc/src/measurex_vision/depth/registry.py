"""Depth provider selection — keeps model choice out of callers.

Both providers live behind the single ``DepthEstimator`` interface so a
commercially-licensed model can replace the research-only baseline later
(MODELS.md)."""

from __future__ import annotations

from typing import Any

from .base import DepthEstimator

KNOWN_PROVIDERS = ("depth_pro", "depth_anything_v2")


def get_depth_estimator(name: str, *, production: bool = False, **cfg: Any) -> DepthEstimator:
    if production:
        from ..models import assert_production_allowed

        assert_production_allowed(name)
    if name == "depth_pro":
        from .depth_pro import DepthProEstimator

        return DepthProEstimator(**cfg)
    if name == "depth_anything_v2":
        from .depth_anything_v2 import DepthAnythingV2Estimator

        return DepthAnythingV2Estimator(**cfg)
    raise ValueError(f"unknown depth provider {name!r}; known: {', '.join(KNOWN_PROVIDERS)}")
