from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from ngc_cams.cameras import CameraRepository
from ngc_cams.db import initialize
from ngc_cams.onvif.discovery import DiscoveredCamera
from ngc_cams_web.composition import build_app


class _FakeDiscoveryService:
    def __init__(self, cameras):
        self._cameras = cameras
        self.calls = 0

    def discover(self, timeout=5):
        self.calls += 1
        return list(self._cameras)


def _build(discovery):
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    initialize(connection)
    repo = CameraRepository(connection)
    app = build_app(
        cameras=repo,
        discovery=discovery,
        recording_manager=None,
    )
    # Composition root attaches a real ONVIF resolver that would try to
    # network-call the fake test addresses; disable it by default so each
    # test opts in to its own resolver shape.
    app.state.resolve_streams = None
    return app


def test_post_discover_returns_html_fragment_listing_each_address():
    fake = _FakeDiscoveryService([
        DiscoveredCamera(address="192.168.1.18", xaddr="http://192.168.1.18/onvif/device_service"),
        DiscoveredCamera(address="192.168.1.42", xaddr="http://192.168.1.42/onvif/device_service",
                         manufacturer="Hikvision"),
    ])
    app = _build(fake)
    with TestClient(app) as client:
        response = client.post("/discover")
    assert response.status_code == 200
    assert "192.168.1.18" in response.text
    assert "192.168.1.42" in response.text
    assert "Hikvision" in response.text
    # Fragment, not a full page
    assert "<html" not in response.text.lower()
    assert fake.calls == 1


def test_post_discover_shows_empty_state_when_none_found():
    app = _build(_FakeDiscoveryService([]))
    with TestClient(app) as client:
        response = client.post("/discover")
    assert response.status_code == 200
    assert "No cameras discovered" in response.text


def test_post_discover_shows_error_when_discovery_raises():
    class Boom:
        def discover(self, timeout):
            raise RuntimeError("network down")

    app = _build(Boom())
    with TestClient(app) as client:
        response = client.post("/discover")
    assert response.status_code == 200
    assert "network down" in response.text


def test_post_discover_renders_add_button_when_rtsp_resolves():
    """When `app.state.resolve_streams` enriches each camera with a main RTSP
    URL, the partial should render a one-click Add form per camera."""
    from ngc_cams.onvif.streams import StreamUris

    fake = _FakeDiscoveryService([
        DiscoveredCamera(address="192.168.1.18", xaddr="http://192.168.1.18/onvif/device_service",
                         manufacturer="IP-Camera"),
    ])
    app = _build(fake)
    app.state.resolve_streams = lambda cam: StreamUris(main=f"rtsp://{cam.address}/live/main")

    with TestClient(app) as client:
        response = client.post("/discover")

    assert response.status_code == 200
    assert "rtsp://192.168.1.18/live/main" in response.text
    assert 'action="/cameras/add"' in response.text
    assert 'value="rtsp://192.168.1.18/live/main"' in response.text
    # PTZ and recording should be on by default in the one-click Add form.
    assert 'name="ptz_enabled"' in response.text
    assert 'name="record_enabled"' in response.text


def test_post_discover_omits_add_button_when_rtsp_not_resolved():
    fake = _FakeDiscoveryService([
        DiscoveredCamera(address="192.168.1.99", xaddr="http://x/onvif"),
    ])
    app = _build(fake)
    with TestClient(app) as client:
        response = client.post("/discover")
    assert response.status_code == 200
    assert "192.168.1.99" in response.text
    assert 'action="/cameras/add"' not in response.text
