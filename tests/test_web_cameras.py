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


def test_post_add_creates_camera_and_redirects_to_index():
    app, repo = _build()
    with TestClient(app) as client:
        response = client.post(
            "/cameras/add",
            data={"name": "New Cam", "rtsp_url": "rtsp://1.2.3.4/main"},
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    stored = repo.list()
    assert len(stored) == 1
    assert stored[0].name == "New Cam"
    assert stored[0].rtsp_url == "rtsp://1.2.3.4/main"


def test_post_delete_removes_camera_and_redirects():
    app, repo = _build()
    stored = repo.add(Camera(name="Doomed", rtsp_url="rtsp://x/main"))
    with TestClient(app) as client:
        response = client.post(f"/cameras/{stored.id}/delete", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert repo.list() == []


def test_post_delete_unknown_id_returns_404():
    app, _ = _build()
    with TestClient(app) as client:
        response = client.post("/cameras/9999/delete", follow_redirects=False)
    assert response.status_code == 404


class _RecordingManagerSpy:
    def __init__(self):
        self.apply_modes_calls = 0

    def apply_modes(self):
        self.apply_modes_calls += 1


def _build_with_manager():
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    initialize(connection)
    repo = CameraRepository(connection)
    spy = _RecordingManagerSpy()
    app = build_app(
        cameras=repo,
        discovery=None,
        recording_manager=spy,
    )
    return app, repo, spy


def test_post_record_toggles_off_to_video_only():
    app, repo, spy = _build_with_manager()
    stored = repo.add(Camera(name="Cam", rtsp_url="rtsp://x/main"))
    assert stored.record_mode == RecordMode.OFF

    with TestClient(app) as client:
        response = client.post(f"/cameras/{stored.id}/record", follow_redirects=False)

    assert response.status_code == 303
    assert repo.get(stored.id).record_mode == RecordMode.VIDEO_ONLY
    assert spy.apply_modes_calls == 1


def test_post_record_toggles_video_only_back_to_off():
    app, repo, spy = _build_with_manager()
    stored = repo.add(
        Camera(name="Cam", rtsp_url="rtsp://x/main", record_mode=RecordMode.VIDEO_ONLY)
    )
    with TestClient(app) as client:
        client.post(f"/cameras/{stored.id}/record", follow_redirects=False)
    assert repo.get(stored.id).record_mode == RecordMode.OFF
    assert spy.apply_modes_calls == 1


def test_get_camera_detail_renders_live_img_and_record_button():
    app, repo = _build()
    stored = repo.add(Camera(name="Door", rtsp_url="rtsp://x/main"))
    with TestClient(app) as client:
        response = client.get(f"/cameras/{stored.id}")
    assert response.status_code == 200
    assert "Door" in response.text
    assert f'src="/cameras/{stored.id}/live.mjpg"' in response.text
    assert "Toggle record" in response.text


def test_get_camera_detail_returns_404_for_unknown_id():
    app, _ = _build()
    with TestClient(app) as client:
        response = client.get("/cameras/9999")
    assert response.status_code == 404


def test_grid_renders_live_img_for_every_camera_up_to_cap():
    app, repo = _build()
    for i in range(3):
        repo.add(Camera(name=f"Cam{i}", rtsp_url=f"rtsp://x/{i}"))
    with TestClient(app) as client:
        response = client.get("/grid")
    assert response.status_code == 200
    for i in range(1, 4):  # ids start at 1
        assert f'/cameras/{i}/live.mjpg' in response.text
        assert f'href="/cameras/{i}"' in response.text


def test_grid_caps_at_eight_and_shows_overflow_notice():
    app, repo = _build()
    for i in range(10):
        repo.add(Camera(name=f"Cam{i}", rtsp_url=f"rtsp://x/{i}"))
    with TestClient(app) as client:
        response = client.get("/grid")
    assert response.status_code == 200
    # Only the first 8 cameras have live.mjpg embeds.
    assert response.text.count("/live.mjpg") == 8
    # Overflow notice present.
    assert "capped at 8" in response.text
    assert "Showing 8 of 10" in response.text


def test_grid_shows_empty_state_when_no_cameras():
    app, _ = _build()
    with TestClient(app) as client:
        response = client.get("/grid")
    assert response.status_code == 200
    assert "No cameras yet" in response.text
    assert "/live.mjpg" not in response.text


def test_grid_marks_recording_cameras():
    app, repo = _build()
    repo.add(Camera(name="OffCam", rtsp_url="rtsp://x/1"))
    repo.add(
        Camera(name="RecCam", rtsp_url="rtsp://x/2", record_mode=RecordMode.VIDEO_ONLY)
    )
    with TestClient(app) as client:
        response = client.get("/grid")
    assert response.status_code == 200
    # The REC badge only appears for cameras with record_mode != off.
    assert response.text.count("REC</span>") == 1
