from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable

from ngc_cams.onvif.discovery import DiscoveredCamera
from ngc_cams.onvif.streams import StreamUris

ResolveStreams = Callable[[DiscoveredCamera], StreamUris]


@dataclass(frozen=True)
class DiscoveryResult:
    cameras: list[DiscoveredCamera] = field(default_factory=list)
    error: str | None = None


def run_discovery(
    service,
    timeout: int,
    resolve_streams: ResolveStreams | None = None,
) -> DiscoveryResult:
    try:
        cameras = service.discover(timeout=timeout)
    except Exception as exc:  # noqa: BLE001 — UI worker must never propagate
        return DiscoveryResult(cameras=[], error=str(exc) or exc.__class__.__name__)
    if resolve_streams is None:
        return DiscoveryResult(cameras=list(cameras), error=None)
    resolved: list[DiscoveredCamera] = []
    for cam in cameras:
        try:
            uris = resolve_streams(cam)
        except Exception:  # noqa: BLE001 — per-device resolution failure must not abort discovery
            resolved.append(cam)
            continue
        resolved.append(replace(cam, main_rtsp_url=uris.main, sub_rtsp_url=uris.sub))
    return DiscoveryResult(cameras=resolved, error=None)
