"""M9 multi-frame metric reconstruction (offline research spike).

Recovers absolute metric L/W/H from multiple RGB frames + known metric camera
poses + intrinsics + object masks via a metric visual hull — absolute scale comes
from the camera poses, never from monocular depth. See
``docs/M9_MULTIVIEW_METRIC_SPIKE.md``.
"""

from __future__ import annotations

from .pipeline import reconstruct, reconstruct_from_provider
from .pose_provider import (
    ARCoreMetricPoseProvider,
    ARKitMetricPoseProvider,
    MetricPoseProvider,
    OfflineManifestProvider,
)
from .schema import (
    CaptureBundle,
    ContractError,
    FailureCode,
    MetricReconstructionError,
    ReconstructionConfig,
    ViewFrame,
    load_bundle,
    validate_bundle,
)

__all__ = [
    "ARCoreMetricPoseProvider",
    "ARKitMetricPoseProvider",
    "CaptureBundle",
    "ContractError",
    "FailureCode",
    "MetricPoseProvider",
    "MetricReconstructionError",
    "OfflineManifestProvider",
    "ReconstructionConfig",
    "ViewFrame",
    "load_bundle",
    "reconstruct",
    "reconstruct_from_provider",
    "validate_bundle",
]
