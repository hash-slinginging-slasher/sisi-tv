from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from ngc_cams.cameras import CameraRepository
from ngc_cams.db import initialize
from ngc_cams.onvif.discovery import DiscoveryService
from ngc_cams_web.composition import build_app


class _FakeDiscovery(DiscoveryService):
    def __init__(self):  # bypass parent ctor
        self.calls: list[int] = []

    def discover(self, timeout=5):
        self.calls.append(timeout)
        return []


def _build_test_app():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize(connection)
    repository = CameraRepository(connection)
    discovery = _FakeDiscovery()
    app = build_app(
        cameras=repository,
        discovery=discovery,
        recording_manager=None,
    )
    return app, repository, discovery


def test_healthz_returns_ok():
    app, _, _ = _build_test_app()
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
