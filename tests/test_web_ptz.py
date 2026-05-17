from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from ngc_cams.cameras import CameraRepository
from ngc_cams.db import initialize
from ngc_cams.models import Camera
from ngc_cams.onvif.ptz import PTZError
from ngc_cams_web.composition import build_app


class _PTZSpy:
    def __init__(self) -> None:
        self.moves: list[dict] = []
        self.stops: list[dict] = []
        self.move_error: Exception | None = None

    def move(self, *, host, port, username, password, direction):
        if self.move_error:
            raise self.move_error
        self.moves.append(
            {
                "host": host,
                "port": port,
                "username": username,
                "password": password,
                "direction": direction,
            }
        )

    def stop(self, *, host, port, username, password):
        self.stops.append(
            {"host": host, "port": port, "username": username, "password": password}
        )


def _build(ptz=None):
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    initialize(connection)
    repo = CameraRepository(connection)
    app = build_app(
        cameras=repo,
        discovery=None,
        recording_manager=None,
    )
    # composition.py attaches a real PTZService; swap it for the spy when
    # a test wants to assert on calls.
    if ptz is not None:
        app.state.ptz_service = ptz
    return app, repo


def test_ptz_move_routes_call_service_with_camera_credentials():
    spy = _PTZSpy()
    app, repo = _build(spy)
    stored = repo.add(
        Camera(
            name="Pan",
            rtsp_url="rtsp://192.168.1.77/live",
            username="admin",
            password="secret",
            ptz_enabled=True,
        )
    )

    with TestClient(app) as client:
        response = client.post(f"/cameras/{stored.id}/ptz/up")

    assert response.status_code == 200
    assert spy.moves == [
        {
            "host": "192.168.1.77",
            "port": 80,
            "username": "admin",
            "password": "secret",
            "direction": "up",
        }
    ]


def test_ptz_stop_route_calls_service_stop():
    spy = _PTZSpy()
    app, repo = _build(spy)
    stored = repo.add(
        Camera(
            name="Pan",
            rtsp_url="rtsp://192.168.1.77/live",
            ptz_enabled=True,
        )
    )

    with TestClient(app) as client:
        response = client.post(f"/cameras/{stored.id}/ptz/stop")

    assert response.status_code == 200
    assert len(spy.stops) == 1
    assert spy.stops[0]["host"] == "192.168.1.77"


def test_ptz_route_returns_404_for_unknown_camera():
    spy = _PTZSpy()
    app, _ = _build(spy)
    with TestClient(app) as client:
        response = client.post("/cameras/9999/ptz/up")
    assert response.status_code == 404


def test_ptz_route_returns_409_when_camera_not_ptz_enabled():
    spy = _PTZSpy()
    app, repo = _build(spy)
    stored = repo.add(
        Camera(name="Fixed", rtsp_url="rtsp://x/main", ptz_enabled=False)
    )
    with TestClient(app) as client:
        response = client.post(f"/cameras/{stored.id}/ptz/up")
    assert response.status_code == 409
    assert spy.moves == []


def test_ptz_route_returns_422_for_unknown_direction():
    spy = _PTZSpy()
    app, repo = _build(spy)
    stored = repo.add(
        Camera(name="Pan", rtsp_url="rtsp://x/main", ptz_enabled=True)
    )
    with TestClient(app) as client:
        response = client.post(f"/cameras/{stored.id}/ptz/sideways")
    assert response.status_code == 422
    assert spy.moves == []


def test_ptz_route_returns_502_when_service_raises_ptz_error():
    spy = _PTZSpy()
    spy.move_error = PTZError("camera unreachable")
    app, repo = _build(spy)
    stored = repo.add(
        Camera(name="Pan", rtsp_url="rtsp://x/main", ptz_enabled=True)
    )
    with TestClient(app) as client:
        response = client.post(f"/cameras/{stored.id}/ptz/up")
    assert response.status_code == 502
    assert "camera unreachable" in response.text


