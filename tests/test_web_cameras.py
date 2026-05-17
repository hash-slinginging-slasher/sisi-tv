from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from ngc_cams.cameras import CameraRepository
from ngc_cams.db import initialize
from ngc_cams.models import Camera, RecordMode
from ngc_cams_web.composition import build_app


def _build():
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    initialize(connection)
    repo = CameraRepository(connection)
    app = build_app(
        cameras=repo,
        discovery=None,
        recording_manager=None,
        live_stream_manager=None,
    )
    return app, repo


def test_index_lists_each_camera_name():
    app, repo = _build()
    repo.add(Camera(name="Front Door", rtsp_url="rtsp://x/main"))
    repo.add(Camera(name="Backyard", rtsp_url="rtsp://y/main", record_mode=RecordMode.VIDEO_ONLY))

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "Front Door" in response.text
    assert "Backyard" in response.text


def test_index_when_no_cameras_shows_empty_state():
    app, _ = _build()
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "No cameras yet" in response.text
