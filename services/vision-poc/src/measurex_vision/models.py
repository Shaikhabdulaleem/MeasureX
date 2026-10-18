"""Model / license metadata and the production-use gate.

The code-level counterpart to ``MODELS.md``: every provider the engine can load
records its licensing and whether it is approved for the production measurement
path. Two concepts are kept separate (VISION_DECISION.md §8, M8 Step 6):

* ``commercial_use`` — the code/weights are *commercially licensed* (permissive
  license, OK to ship legally).
* ``production_approved`` — the provider is *approved for real production
  measurement quality*.

A provider can be commercially licensed yet NOT production-approved. The
model-free fallbacks (``central_candidate``, ``box_mask``) carry the permissive
MeasureX license but are CI / development / synthetic-test aids only — they are
never an approved real production detector/segmenter. Depth Pro is neither
commercially usable nor production-approved (Apple-ASCL, research only).

Production mode must refuse any provider whose ``production_approved`` is not
true. Keep this table in sync with ``MODELS.md``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelMetadata:
    key: str                  # provider name used by the registries
    provider: str
    repository: str           # upstream code repository
    model_id: str             # HF repo id / loader identifier (pinned by revision)
    revision: str             # exact pinned revision/commit — frozen, not "on download"
    checkpoint: str           # weight/checkpoint filename
    checkpoint_sha256: str    # weight SHA256 when practical ("" otherwise)
    code_license: str
    checkpoint_license: str   # recorded separately from the code license
    commercial_use: bool      # commercially licensed (OK to ship legally)
    production_approved: bool  # approved for real production measurement quality


# A model-free provider (geometry/heuristic only) carries no weights, so it is
# commercially unencumbered — but it is a CI/dev/test aid, NOT approved for real
# production measurement. ``production_approved`` is therefore False.
_MODEL_FREE = {
    "repository": "(in-repo, no weights)",
    "model_id": "n/a",
    "revision": "n/a",
    "checkpoint": "n/a",
    "checkpoint_sha256": "n/a",
    "code_license": "MeasureX",
    "checkpoint_license": "n/a",
    "commercial_use": True,
    "production_approved": False,
}

MODEL_REGISTRY: dict[str, ModelMetadata] = {
    # Depth
    "depth_pro": ModelMetadata(
        key="depth_pro",
        provider="Apple ml-depth-pro",
        repository="https://github.com/apple/ml-depth-pro",
        model_id="apple/DepthPro",
        revision="record on download",  # research-only, never ships — not pinned
        checkpoint="depth_pro.pt",
        checkpoint_sha256="",
        code_license="Apple sample-code license",
        checkpoint_license="Apple-ASCL (research only)",
        commercial_use=False,
        production_approved=False,  # research/benchmark baseline only — never ships
    ),
    "depth_anything_v2": ModelMetadata(
        key="depth_anything_v2",
        provider="Depth Anything V2 (Metric, Indoor, Small)",
        repository="https://github.com/DepthAnything/Depth-Anything-V2",
        model_id="depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf",
        revision="8078d68a9c75a972131914f6afd0c1723be0da7f",  # pinned HF commit
        checkpoint="model.safetensors",
        checkpoint_sha256="",  # pinned by HF revision; record on first download
        code_license="Apache-2.0",
        checkpoint_license="Apache-2.0",
        commercial_use=True,
        production_approved=True,  # commercial-path depth provider
    ),
    # Segmentation
    "sam2": ModelMetadata(
        key="sam2",
        provider="SAM 2.1 Small (Meta)",
        repository="https://github.com/facebookresearch/sam2",
        model_id="facebook/sam2.1-hiera-small",
        revision="ee5bba1d82bb8749febdf90f45e84b687142ba03",  # pinned HF commit
        checkpoint="sam2.1_hiera_small.pt",
        checkpoint_sha256="",  # pinned by HF revision; record on first download
        code_license="Apache-2.0 (eval code BSD-3-Clause)",
        checkpoint_license="Apache-2.0",
        commercial_use=True,
        production_approved=True,
    ),
    "box_mask": ModelMetadata(key="box_mask", provider="box-fill (model-free)", **_MODEL_FREE),
    # Detection
    "grounding_dino": ModelMetadata(
        key="grounding_dino",
        provider="Grounding DINO Tiny (IDEA-Research)",
        repository="https://github.com/IDEA-Research/GroundingDINO",
        model_id="IDEA-Research/grounding-dino-tiny",
        revision="a2bb814dd30d776dcf7e30523b00659f4f141c71",  # pinned HF commit
        checkpoint="model.safetensors",
        checkpoint_sha256="",  # pinned by HF revision; record on first download
        code_license="Apache-2.0",
        checkpoint_license="Apache-2.0",
        commercial_use=True,
        production_approved=True,
    ),
    "central_candidate": ModelMetadata(
        key="central_candidate", provider="central-object (model-free)", **_MODEL_FREE
    ),
}

# The approved real production stack. ``--production`` resolves to these when the
# caller does not override, and the registry gate refuses anything else.
PRODUCTION_STACK = {
    "detector": "grounding_dino",
    "segmenter": "sam2",
    "depth": "depth_anything_v2",
}


class ProductionPolicyError(RuntimeError):
    """Raised when a production path asks for a non-production-approved model."""


def get_metadata(key: str) -> ModelMetadata:
    try:
        return MODEL_REGISTRY[key]
    except KeyError:
        raise ValueError(f"no model metadata for {key!r}") from None


def assert_production_approved(key: str) -> ModelMetadata:
    """Return the metadata, or raise if the provider is not production-approved.

    A model-free fallback or a research-only checkpoint may be commercially
    licensed yet still fail here — production demands measurement-quality
    approval, not merely a permissive license."""
    meta = get_metadata(key)
    if not meta.production_approved:
        raise ProductionPolicyError(
            f"{key!r} is not approved for the production measurement path "
            f"(commercially licensed: {meta.commercial_use}; "
            f"checkpoint license: {meta.checkpoint_license}). "
            f"Use the approved production stack: {PRODUCTION_STACK}"
        )
    return meta
