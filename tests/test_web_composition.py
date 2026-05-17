from __future__ import annotations

import logging
import sqlite3
import time

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


class _FlakyRecordingManager:
    def __init__(self):
        self.poll_calls = 0
        self.stop_all_calls = 0

    def poll(self):
        self.poll_calls += 1
        if self.poll_calls == 1:
            raise RuntimeError("simulated poll failure")

    def stop_all(self):
        self.stop_all_calls += 1


def test_poller_logs_exception_and_keeps_running(caplog):
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize(connection)
    repository = CameraRepository(connection)
    manager = _FlakyRecordingManager()

    app = build_app(
        cameras=repository,
        discovery=None,
        recording_manager=manager,
        lifespan_poll_seconds=0.05,
    )

    with caplog.at_level(logging.ERROR, logger="ngc_cams_web.composition"):
        with TestClient(app):
            # Lifespan enter starts the poller; give it enough wall time to
            # tick at least twice so we see "raised on tick 1, recovered on
            # tick 2".
            time.sleep(0.25)

    assert any(
        "recording poll tick failed" in record.message
        for record in caplog.records
    ), "expected poller to log the swallowed RuntimeError"
    assert any(
        record.exc_info is not None for record in caplog.records
    ), "expected logger.exception to attach the traceback"
    assert manager.poll_calls >= 2, "poller must keep ticking after a failure"
    assert manager.stop_all_calls == 1, "lifespan shutdown must still call stop_all"
