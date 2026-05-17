from __future__ import annotations

from ngc_cams.onvif.discovery import DiscoveredCamera
from ngc_cams.discovery_runner import DiscoveryResult, run_discovery


class _FakeDiscovery:
    def __init__(self, result):
        self._result = result
        self.calls: list[int] = []

    def discover(self, timeout: int):
        self.calls.append(timeout)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def test_run_discovery_returns_camera_list_on_success():
    cams = [
        DiscoveredCamera(
            address="192.168.1.18",
            xaddr="http://192.168.1.18/onvif/device_service",
        )
    ]
    fake = _FakeDiscovery(cams)
    result = run_discovery(fake, timeout=3)
    assert result == DiscoveryResult(cameras=cams, error=None)
    assert fake.calls == [3]


def test_run_discovery_catches_exceptions_and_returns_error():
    fake = _FakeDiscovery(RuntimeError("network down"))
    result = run_discovery(fake, timeout=5)
    assert result.cameras == []
    assert result.error is not None
    assert "network down" in result.error


def test_run_discovery_resolves_stream_uris_when_resolver_provided():
    from ngc_cams.onvif.streams import StreamUris

    cams = [
        DiscoveredCamera(
            address="192.168.1.5",
            xaddr="http://192.168.1.5:8080/onvif/device_service",
        )
    ]
    fake = _FakeDiscovery(cams)
    resolver_calls: list[DiscoveredCamera] = []

    def fake_resolver(cam: DiscoveredCamera) -> StreamUris:
        resolver_calls.append(cam)
        return StreamUris(main="rtsp://192.168.1.5/main", sub="rtsp://192.168.1.5/sub")

    result = run_discovery(fake, timeout=3, resolve_streams=fake_resolver)
    assert resolver_calls == cams
    assert len(result.cameras) == 1
    assert result.cameras[0].address == "192.168.1.5"
    assert result.cameras[0].main_rtsp_url == "rtsp://192.168.1.5/main"
    assert result.cameras[0].sub_rtsp_url == "rtsp://192.168.1.5/sub"


def test_run_discovery_keeps_camera_when_resolver_raises():
    cams = [
        DiscoveredCamera(
            address="192.168.1.5",
            xaddr="http://192.168.1.5/onvif/device_service",
        )
    ]
    fake = _FakeDiscovery(cams)

    def failing_resolver(_cam):
        raise RuntimeError("401 unauthorized")

    result = run_discovery(fake, timeout=3, resolve_streams=failing_resolver)
    assert result.error is None
    assert len(result.cameras) == 1
    assert result.cameras[0].main_rtsp_url is None
    assert result.cameras[0].sub_rtsp_url is None
