"""MetricPoseProvider — the boundary between M9's portable core and whatever
supplies metric camera poses.

The core depends on this abstraction, never on ARCore/ARKit directly, because the
test device (Samsung Galaxy A16 4G / SM-A165F/DS) is **not** confirmed on the
ARCore certified-device list. A provider must honestly report whether a metric
pose source is available; when it is not, a METRIC request fails with
``metric_pose_unavailable`` rather than silently falling back to monocular depth
and mislabelling the result as METRIC. The RGB-only M8 path stays ESTIMATE.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum

from .schema import CaptureBundle, load_bundle


class TrackingState(str, Enum):
    TRACKING = "tracking"
    LIMITED = "limited"
    UNAVAILABLE = "unavailable"


class MetricPoseProvider(ABC):
    """Supplies a validated metric capture bundle (frames, intrinsics, metric
    poses, gravity, optional support plane)."""

    pose_source: str = "unknown"

    @abstractmethod
    def metric_pose_available(self) -> bool:
        """True only when a genuine metric pose source backs this provider."""

    @abstractmethod
    def load(self) -> CaptureBundle:
        """Return the capture bundle. Only valid when metric pose is available."""


class OfflineManifestProvider(MetricPoseProvider):
    """Reads a ``capture.json`` bundle recorded offline (any source of metric
    poses — ARCore/ARKit/VIO/externally measured). This is the provider the M9
    research spike actually uses."""

    pose_source = "external_metric_pose"

    def __init__(self, manifest_path: str) -> None:
        self.manifest_path = manifest_path

    def metric_pose_available(self) -> bool:
        return True

    def load(self) -> CaptureBundle:
        return load_bundle(self.manifest_path)


class ARCoreMetricPoseProvider(MetricPoseProvider):
    """Future Android adapter (ARCore VIO). Not implemented in the Python spike.

    ``metric_pose_available`` must reflect a real runtime check on the device —
    the A16 4G may report False, and the core must handle that cleanly."""

    pose_source = "arcore"

    def metric_pose_available(self) -> bool:  # pragma: no cover - platform stub
        return False

    def load(self) -> CaptureBundle:  # pragma: no cover - platform stub
        raise NotImplementedError("ARCore pose capture is a mobile-side adapter, not part of the spike")


class ARKitMetricPoseProvider(MetricPoseProvider):
    """Future iOS adapter (ARKit VIO). Not implemented in the Python spike."""

    pose_source = "arkit"

    def metric_pose_available(self) -> bool:  # pragma: no cover - platform stub
        return False

    def load(self) -> CaptureBundle:  # pragma: no cover - platform stub
        raise NotImplementedError("ARKit pose capture is a mobile-side adapter, not part of the spike")
