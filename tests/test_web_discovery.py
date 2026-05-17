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
    return build_app(
        cameras=repo,
        discovery=discovery,
        recording_manager=None,
        live_stream_manager=None,
    )


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
