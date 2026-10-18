"""Model / license metadata and the production-use gate.

The code-level counterpart to ``MODELS.md``: every provider the engine can load
records its licensing and whether it may run in a production path. Production
mode must refuse any provider whose ``production_allowed`` is not true — above
all Depth Pro, whose weights are research-only (VISION_DECISION.md §8, M8 Step 6).
Keep this table in sync with ``MODELS.md``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelMetadata:
    key: str                  # provider name used by the registries
    provider: str
    repository: str
    revision: str             # exact revision/commit — confirmed at download time
    checkpoint: str
    code_license: str
    checkpoint_license: str   # recorded separately from the code license
    commercial_use: bool
    production_allowed: bool


# A model-free provider (geometry/heuristic only) carries no weights, so it is
# trivially production-safe.
_MODEL_FREE = {
    "repository": "(in-repo, no weights)",
    "revision": "n/a",
    "checkpoint": "n/a",
    "code_license": "MeasureX",
    "checkpoint_license": "n/a",
    "commercial_use": True,
    "production_allowed": True,
}

MODEL_REGISTRY: dict[str, ModelMetadata] = {
    # Depth
    "depth_pro": ModelMetadata(
        key="depth_pro",
        provider="Apple ml-depth-pro",
        repository="https://github.com/apple/ml-depth-pro",
        revision="record on download",
        checkpoint="depth_pro.pt",
        code_license="Apple sample-code license",
        checkpoint_license="Apple-ASCL (research only)",
        commercial_use=False,
        production_allowed=False,  # research/benchmark baseline only — never ships
    ),
    "depth_anything_v2": ModelMetadata(
        key="depth_anything_v2",
        provider="Depth Anything V2 (Metric, Small)",
        repository="https://github.com/DepthAnything/Depth-Anything-V2",
        revision="record on download",
        checkpoint="depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf",
        code_license="Apache-2.0",
        checkpoint_license="Apache-2.0",
        commercial_use=True,
        production_allowed=True,  # commercial-path depth provider
    ),
    # Segmentation
    "sam2": ModelMetadata(
        key="sam2",
        provider="SAM 2 (Meta)",
        repository="https://github.com/facebookresearch/sam2",
        revision="record on download",
        checkpoint="facebook/sam2-hiera-*",
        code_license="Apache-2.0 (eval code BSD-3-Clause)",
        checkpoint_license="Apache-2.0",
        commercial_use=True,
        production_allowed=True,
    ),
    "box_mask": ModelMetadata(key="box_mask", provider="box-fill (model-free)", **_MODEL_FREE),
    # Detection
    "grounding_dino": ModelMetadata(
        key="grounding_dino",
        provider="Grounding DINO (IDEA-Research)",
        repository="https://github.com/IDEA-Research/GroundingDINO",
        revision="record on download",
        checkpoint="IDEA-Research/grounding-dino-tiny",
        code_license="Apache-2.0",
        checkpoint_license="Apache-2.0",
        commercial_use=True,
        production_allowed=True,
    ),
    "central_candidate": ModelMetadata(
        key="central_candidate", provider="central-object (model-free)", **_MODEL_FREE
    ),
}


class ProductionPolicyError(RuntimeError):
    """Raised when a production path asks for a non-production-allowed model."""


def get_metadata(key: str) -> ModelMetadata:
    try:
        return MODEL_REGISTRY[key]
    except KeyError:
        raise ValueError(f"no model metadata for {key!r}") from None


def assert_production_allowed(key: str) -> ModelMetadata:
    """Return the metadata, or raise if the provider may not run in production."""
    meta = get_metadata(key)
    if not meta.production_allowed:
        raise ProductionPolicyError(
            f"{key!r} is not production-allowed "
            f"(checkpoint license: {meta.checkpoint_license}); "
            "select a commercially-licensed provider for the production path"
        )
    return meta
