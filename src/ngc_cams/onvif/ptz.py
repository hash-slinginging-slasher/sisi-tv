"""ONVIF PTZ wrapper.

UI-agnostic: the FastAPI route in ``ngc_cams_web/routes/ptz.py`` calls into
this. ONVIF discovery and stream-URI resolution stay in their own modules; we
keep the same injection seam as ``streams.get_stream_uris`` — an
``onvif_factory`` keyword argument so tests can swap in a fake ``ONVIFCamera``.

ContinuousMove + Stop both need a ``ProfileToken``, so each call resolves
profiles fresh from the camera. Cheap on a LAN; pooling is a follow-up.
"""

from __future__ import annotations

from typing import Any, Callable
from urllib.parse import urlparse


# Direction → ONVIF Velocity vector (Pan/Tilt/Zoom in normalized [-1, 1]).
# Conservative magnitudes for a press-and-hold UX: large enough to feel
# responsive, small enough to not slam against limits in one frame.
_VELOCITY = {
    "up": {"PanTilt": {"x": 0.0, "y": 0.5}},
    "down": {"PanTilt": {"x": 0.0, "y": -0.5}},
    "left": {"PanTilt": {"x": -0.5, "y": 0.0}},
    "right": {"PanTilt": {"x": 0.5, "y": 0.0}},
    "zoom_in": {"Zoom": {"x": 0.5}},
    "zoom_out": {"Zoom": {"x": -0.5}},
}

VALID_DIRECTIONS = frozenset(_VELOCITY)


class PTZError(RuntimeError):
    """Raised when ONVIF PTZ calls cannot complete (camera unreachable,
    no profiles, etc.). Routes turn this into a 502."""


def onvif_endpoint_from_rtsp(rtsp_url: str, default_port: int = 80) -> tuple[str, int]:
    """Best-effort host/port for the ONVIF service from a camera's RTSP URL.

    The DB schema doesn't store the ONVIF endpoint separately yet; nearly every
    camera serves ONVIF over HTTP on the same host as RTSP, with port 80 the
    overwhelming default. Cameras that listen on a non-standard ONVIF port will
    need an explicit field — file as a follow-up if it bites.
    """
    parsed = urlparse(rtsp_url)
    return (parsed.hostname or "", default_port)


class PTZService:
    """Thin wrapper around `ONVIFCamera.create_ptz_service()`.

    The default ``onvif_factory`` lazily imports ``onvif.ONVIFCamera`` so this
    module stays importable without the onvif-zeep dependency loaded (matches
    the pattern in ``streams.get_stream_uris``). Tests pass a fake factory.
    """

    def __init__(self, onvif_factory: Callable[..., Any] | None = None) -> None:
        self._onvif_factory = onvif_factory or _default_onvif_factory

    def move(
        self,
        *,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        direction: str,
    ) -> None:
        if direction not in _VELOCITY:
            raise ValueError(f"unknown PTZ direction: {direction!r}")
        ptz, token = self._open(host, port, username, password)
        try:
            ptz.ContinuousMove(
                {"ProfileToken": token, "Velocity": _VELOCITY[direction]}
            )
        except Exception as exc:  # noqa: BLE001 — wrap any onvif error
            raise PTZError(f"ContinuousMove failed: {exc}") from exc

    def stop(
        self,
        *,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
    ) -> None:
        ptz, token = self._open(host, port, username, password)
        try:
            ptz.Stop({"ProfileToken": token, "PanTilt": True, "Zoom": True})
        except Exception as exc:  # noqa: BLE001
            raise PTZError(f"Stop failed: {exc}") from exc

    def _open(
        self,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
    ) -> tuple[Any, str]:
        try:
            camera = self._onvif_factory(host, port, username or "", password or "")
        except Exception as exc:  # noqa: BLE001
            raise PTZError(f"could not reach ONVIF service at {host}:{port}: {exc}") from exc
        try:
            media = camera.create_media_service()
            profiles = media.GetProfiles()
        except Exception as exc:  # noqa: BLE001
            raise PTZError(f"could not list ONVIF media profiles: {exc}") from exc
        if not profiles:
            raise PTZError("camera reports no ONVIF media profiles")
        token = getattr(profiles[0], "token", None)
        if not token:
            raise PTZError("first ONVIF profile has no token")
        try:
            ptz = camera.create_ptz_service()
        except Exception as exc:  # noqa: BLE001
            raise PTZError(f"could not create PTZ service: {exc}") from exc
        return ptz, token


def _default_onvif_factory(host: str, port: int, username: str, password: str) -> Any:
    from onvif import ONVIFCamera

    return ONVIFCamera(host, port, username, password)
