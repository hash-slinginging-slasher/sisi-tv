from __future__ import annotations

import io
import sqlite3

from fastapi.testclient import TestClient

from ngc_cams.cameras import CameraRepository
from ngc_cams.db import initialize
from ngc_cams.models import Camera
from ngc_cams_web.composition import build_app


class _FakeProcess:
    def __init__(self, payload: bytes):
        self.stdout = io.BytesIO(payload)
        self.killed = False
        self.terminated = False
        self._returncode: int | None = None

    def poll(self):
        return self._returncode

    def kill(self):
        self.killed = True
        self._returncode = -9

    def terminate(self):
        self.terminated = True
        self._returncode = -15

    def wait(self, timeout=None):
        self._returncode = self._returncode or 0
        return self._returncode


def _build_with_fake_ffmpeg(payload: bytes):
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    initialize(connection)
    repo = CameraRepository(connection)
    stored = repo.add(Camera(name="Cam", rtsp_url="rtsp://x/main"))
    process = _FakeProcess(payload)

    def fake_popen(command, **kwargs):
        return process

    app = build_app(
        cameras=repo,
        discovery=None,
        recording_manager=None,
    )
    app.state.live_popen_factory = fake_popen
    app.state.live_ffmpeg_resolver = lambda: "/usr/bin/ffmpeg"
    return app, stored.id, process


def test_live_route_streams_multipart_mjpeg():
    SOI = b"\xff\xd8"
    EOI = b"\xff\xd9"
    payload = SOI + b"AAAA" + EOI + SOI + b"BBBB" + EOI
    app, camera_id, process = _build_with_fake_ffmpeg(payload)

    with TestClient(app) as client:
        response = client.get(f"/cameras/{camera_id}/live.mjpg")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("multipart/x-mixed-replace")
    assert b"--frame" in response.content
    assert SOI + b"AAAA" + EOI in response.content
    assert SOI + b"BBBB" + EOI in response.content


def test_live_route_returns_404_for_unknown_camera():
    app, _, _ = _build_with_fake_ffmpeg(b"")
    with TestClient(app) as client:
        response = client.get("/cameras/9999/live.mjpg")
    assert response.status_code == 404


def test_live_route_returns_503_when_ffmpeg_not_installed():
    app, camera_id, _ = _build_with_fake_ffmpeg(b"")
    app.state.live_ffmpeg_resolver = lambda: None
    with TestClient(app) as client:
        response = client.get(f"/cameras/{camera_id}/live.mjpg")
    assert response.status_code == 503
