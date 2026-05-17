from __future__ import annotations

from dataclasses import dataclass

import pytest

from ngc_cams.onvif.ptz import PTZError, PTZService, onvif_endpoint_from_rtsp


@dataclass
class _Profile:
    token: str


class _FakePTZ:
    def __init__(self) -> None:
        self.moves: list[dict] = []
        self.stops: list[dict] = []
        self.fail: Exception | None = None

    def ContinuousMove(self, body: dict) -> None:  # noqa: N802 — ONVIF naming
        if self.fail:
            raise self.fail
        self.moves.append(body)

    def Stop(self, body: dict) -> None:  # noqa: N802
        if self.fail:
            raise self.fail
        self.stops.append(body)


class _FakeMedia:
    def __init__(self, profiles: list[_Profile]) -> None:
        self._profiles = profiles

    def GetProfiles(self) -> list[_Profile]:  # noqa: N802
        return self._profiles


class _FakeCamera:
    def __init__(self, ptz: _FakePTZ, media: _FakeMedia) -> None:
        self._ptz = ptz
        self._media = media

    def create_ptz_service(self) -> _FakePTZ:
        return self._ptz

    def create_media_service(self) -> _FakeMedia:
        return self._media


def _factory(profiles: list[_Profile], ptz: _FakePTZ):
    calls: list[tuple] = []

    def factory(host, port, username, password):
        calls.append((host, port, username, password))
        return _FakeCamera(ptz, _FakeMedia(profiles))

    return factory, calls


def test_onvif_endpoint_from_rtsp_extracts_host_with_default_port():
    host, port = onvif_endpoint_from_rtsp("rtsp://192.168.1.77/live/ch00_0")
    assert host == "192.168.1.77"
    assert port == 80


def test_onvif_endpoint_from_rtsp_handles_explicit_rtsp_port():
    host, port = onvif_endpoint_from_rtsp("rtsp://10.0.0.5:8554/main")
    assert host == "10.0.0.5"
    assert port == 80  # RTSP port doesn't affect ONVIF port


def test_move_calls_continuous_move_with_right_velocity_for_up():
    ptz = _FakePTZ()
    factory, calls = _factory([_Profile(token="profile_1")], ptz)
    service = PTZService(onvif_factory=factory)

    service.move(
        host="192.168.1.77",
        port=80,
        username="admin",
        password="pw",
        direction="up",
    )

    assert calls == [("192.168.1.77", 80, "admin", "pw")]
    assert ptz.moves == [
        {
            "ProfileToken": "profile_1",
            "Velocity": {"PanTilt": {"x": 0.0, "y": 0.5}},
        }
    ]


@pytest.mark.parametrize(
    "direction,expected",
    [
        ("up", {"PanTilt": {"x": 0.0, "y": 0.5}}),
        ("down", {"PanTilt": {"x": 0.0, "y": -0.5}}),
        ("left", {"PanTilt": {"x": -0.5, "y": 0.0}}),
        ("right", {"PanTilt": {"x": 0.5, "y": 0.0}}),
        ("zoom_in", {"Zoom": {"x": 0.5}}),
        ("zoom_out", {"Zoom": {"x": -0.5}}),
    ],
)
def test_move_velocity_per_direction(direction, expected):
    ptz = _FakePTZ()
    factory, _ = _factory([_Profile(token="t")], ptz)
    service = PTZService(onvif_factory=factory)

    service.move(host="x", port=80, username=None, password=None, direction=direction)

    assert ptz.moves[0]["Velocity"] == expected


def test_move_rejects_unknown_direction():
    factory, _ = _factory([_Profile(token="t")], _FakePTZ())
    service = PTZService(onvif_factory=factory)
    with pytest.raises(ValueError):
        service.move(
            host="x", port=80, username=None, password=None, direction="sideways"
        )


def test_stop_uses_first_profile_token_and_stops_both_axes():
    ptz = _FakePTZ()
    factory, _ = _factory([_Profile(token="profile_1")], ptz)
    service = PTZService(onvif_factory=factory)

    service.stop(host="x", port=80, username=None, password=None)

    assert ptz.stops == [
        {"ProfileToken": "profile_1", "PanTilt": True, "Zoom": True}
    ]


def test_move_raises_ptz_error_when_no_profiles():
    factory, _ = _factory([], _FakePTZ())
    service = PTZService(onvif_factory=factory)
    with pytest.raises(PTZError, match="no ONVIF media profiles"):
        service.move(host="x", port=80, username=None, password=None, direction="up")


def test_move_wraps_factory_errors_as_ptz_error():
    def boom(host, port, username, password):
        raise ConnectionError("no route to host")

    service = PTZService(onvif_factory=boom)
    with pytest.raises(PTZError, match="could not reach ONVIF service"):
        service.move(host="x", port=80, username=None, password=None, direction="up")


def test_move_wraps_continuous_move_errors_as_ptz_error():
    ptz = _FakePTZ()
    ptz.fail = RuntimeError("camera said no")
    factory, _ = _factory([_Profile(token="t")], ptz)
    service = PTZService(onvif_factory=factory)
    with pytest.raises(PTZError, match="ContinuousMove failed"):
        service.move(host="x", port=80, username=None, password=None, direction="up")
