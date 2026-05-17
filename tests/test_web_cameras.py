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


def test_post_add_with_record_enabled_starts_recording():
    app, repo, spy = _build_with_manager()
    with TestClient(app) as client:
        client.post(
            "/cameras/add",
            data={
                "name": "RecMe",
                "rtsp_url": "rtsp://x/main",
                "record_enabled": "1",
                "ptz_enabled": "1",
            },
            follow_redirects=False,
        )
    stored = repo.list()
    assert len(stored) == 1
    assert stored[0].record_mode == RecordMode.VIDEO_ONLY
    assert stored[0].ptz_enabled is True
    assert spy.apply_modes_calls == 1


def test_post_add_without_record_enabled_keeps_record_off():
    app, repo, spy = _build_with_manager()
    with TestClient(app) as client:
        client.post(
            "/cameras/add",
            data={"name": "Quiet", "rtsp_url": "rtsp://x/main"},
            follow_redirects=False,
        )
    stored = repo.list()
    assert stored[0].record_mode == RecordMode.OFF
    assert stored[0].ptz_enabled is False
    assert spy.apply_modes_calls == 0


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
        self.stop_calls: list[int] = []
        self.recording_ids: set[int] = set()

    def apply_modes(self):
        self.apply_modes_calls += 1

    def is_recording(self, camera_id: int) -> bool:
        return camera_id in self.recording_ids

    def stop(self, camera_id: int) -> None:
        self.stop_calls.append(camera_id)
        self.recording_ids.discard(camera_id)


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


def test_get_edit_form_renders_current_values():
    app, repo = _build()
    stored = repo.add(
        Camera(
            name="Old Name",
            rtsp_url="rtsp://192.168.1.77",
            ptz_enabled=True,
            record_mode=RecordMode.VIDEO_ONLY,
        )
    )
    with TestClient(app) as client:
        response = client.get(f"/cameras/{stored.id}/edit")
    assert response.status_code == 200
    assert 'value="Old Name"' in response.text
    assert 'value="rtsp://192.168.1.77"' in response.text
    # checkbox is pre-checked for ptz, select has video_only selected
    assert "checked" in response.text
    assert 'value="video_only"' in response.text
    assert "selected" in response.text


def test_get_edit_form_returns_404_for_unknown_id():
    app, _ = _build()
    with TestClient(app) as client:
        response = client.get("/cameras/9999/edit")
    assert response.status_code == 404


def test_post_edit_persists_changes_and_redirects_to_settings():
    app, repo, spy = _build_with_manager()
    stored = repo.add(Camera(name="Cam 1", rtsp_url="rtsp://192.168.1.77"))
    with TestClient(app) as client:
        response = client.post(
            f"/cameras/{stored.id}/edit",
            data={
                "name": "Front Door",
                "rtsp_url": "rtsp://192.168.1.77/live/ch00_0",
                "record_mode": "video_only",
                "ptz_enabled": "1",
            },
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert response.headers["location"] == "/settings"
    updated = repo.get(stored.id)
    assert updated.name == "Front Door"
    assert updated.rtsp_url == "rtsp://192.168.1.77/live/ch00_0"
    assert updated.record_mode == RecordMode.VIDEO_ONLY
    assert updated.ptz_enabled is True
    # apply_modes fires so the recording manager picks up new RTSP / mode.
    assert spy.apply_modes_calls == 1


def test_post_edit_unchecking_ptz_clears_it():
    app, repo, _ = _build_with_manager()
    stored = repo.add(
        Camera(name="x", rtsp_url="rtsp://x/main", ptz_enabled=True)
    )
    with TestClient(app) as client:
        client.post(
            f"/cameras/{stored.id}/edit",
            data={"name": "x", "rtsp_url": "rtsp://x/main", "record_mode": "off"},
            # ptz_enabled omitted from form => unchecked
            follow_redirects=False,
        )
    assert repo.get(stored.id).ptz_enabled is False


def test_post_edit_with_unknown_camera_returns_404():
    app, _, _ = _build_with_manager()
    with TestClient(app) as client:
        response = client.post(
            "/cameras/9999/edit",
            data={"name": "x", "rtsp_url": "rtsp://x/main"},
        )
    assert response.status_code == 404


def test_post_edit_stops_active_ffmpeg_when_rtsp_changes():
    """Editing the RTSP of a currently-recording camera should force a stop
    so apply_modes spawns a fresh ffmpeg against the new URL."""
    app, repo, spy = _build_with_manager()
    stored = repo.add(
        Camera(name="x", rtsp_url="rtsp://x/bare", record_mode=RecordMode.VIDEO_ONLY)
    )
    # Pretend the manager is mid-recording on this camera.
    spy.recording_ids.add(stored.id)

    with TestClient(app) as client:
        client.post(
            f"/cameras/{stored.id}/edit",
            data={
                "name": "x",
                "rtsp_url": "rtsp://x/main",  # different
                "record_mode": "video_only",
            },
            follow_redirects=False,
        )

    assert spy.stop_calls == [stored.id]
    assert spy.apply_modes_calls == 1


def test_post_edit_does_not_stop_when_rtsp_unchanged():
    app, repo, spy = _build_with_manager()
    stored = repo.add(
        Camera(name="x", rtsp_url="rtsp://x/main", record_mode=RecordMode.VIDEO_ONLY)
    )
    spy.recording_ids.add(stored.id)

    with TestClient(app) as client:
        client.post(
            f"/cameras/{stored.id}/edit",
            data={
                "name": "Renamed",  # only name changed
                "rtsp_url": "rtsp://x/main",
                "record_mode": "video_only",
            },
            follow_redirects=False,
        )

    assert spy.stop_calls == []  # no stop because RTSP didn't change
    assert spy.apply_modes_calls == 1


def test_post_edit_persists_display_rotation():
    app, repo, _ = _build_with_manager()
    stored = repo.add(Camera(name="x", rtsp_url="rtsp://x/main"))
    with TestClient(app) as client:
        client.post(
            f"/cameras/{stored.id}/edit",
            data={"name": "x", "rtsp_url": "rtsp://x/main", "display_rotation": "180"},
            follow_redirects=False,
        )
    assert repo.get(stored.id).display_rotation == 180


def test_post_edit_rejects_unknown_rotation_keeps_existing():
    app, repo, _ = _build_with_manager()
    stored = repo.add(
        Camera(name="x", rtsp_url="rtsp://x/main", display_rotation=90)
    )
    with TestClient(app) as client:
        client.post(
            f"/cameras/{stored.id}/edit",
            data={"name": "x", "rtsp_url": "rtsp://x/main", "display_rotation": "45"},
            follow_redirects=False,
        )
    assert repo.get(stored.id).display_rotation == 90


def test_camera_detail_applies_rotation_transform():
    app, repo = _build()
    stored = repo.add(
        Camera(name="x", rtsp_url="rtsp://x/main", display_rotation=270)
    )
    with TestClient(app) as client:
        response = client.get(f"/cameras/{stored.id}")
    assert "transform: rotate(270deg)" in response.text


def test_post_edit_invalid_record_mode_keeps_existing():
    app, repo, _ = _build_with_manager()
    stored = repo.add(
        Camera(name="x", rtsp_url="rtsp://x/main", record_mode=RecordMode.VIDEO_AUDIO)
    )
    with TestClient(app) as client:
        client.post(
            f"/cameras/{stored.id}/edit",
            data={
                "name": "x",
                "rtsp_url": "rtsp://x/main",
                "record_mode": "garbage_mode",
            },
            follow_redirects=False,
        )
    assert repo.get(stored.id).record_mode == RecordMode.VIDEO_AUDIO


def test_grid_renders_live_img_for_every_camera(tmp_path, monkeypatch):
    from ngc_cams import settings_store
    monkeypatch.setattr(settings_store, "default_settings_path",
                        lambda: tmp_path / "settings.json")
    app, repo = _build()
    for i in range(3):
        repo.add(Camera(name=f"Cam{i}", rtsp_url=f"rtsp://x/{i}"))
    with TestClient(app) as client:
        response = client.get("/grid")
    assert response.status_code == 200
    for i in range(1, 4):
        assert f'/cameras/{i}/live.mjpg' in response.text
        assert f'href="/cameras/{i}"' in response.text


def test_grid_shows_every_camera_no_cap(tmp_path, monkeypatch):
    """The 8-cell cap was removed when the layout became user-arrangeable."""
    from ngc_cams import settings_store
    monkeypatch.setattr(settings_store, "default_settings_path",
                        lambda: tmp_path / "settings.json")
    app, repo = _build()
    for i in range(10):
        repo.add(Camera(name=f"Cam{i}", rtsp_url=f"rtsp://x/{i}"))
    with TestClient(app) as client:
        response = client.get("/grid")
    assert response.status_code == 200
    assert response.text.count("/live.mjpg") == 10


def test_grid_respects_saved_order(tmp_path, monkeypatch):
    from ngc_cams import settings_store
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_store, "default_settings_path", lambda: settings_path)
    app, repo = _build()
    repo.add(Camera(name="First", rtsp_url="rtsp://x/1"))   # id=1
    repo.add(Camera(name="Second", rtsp_url="rtsp://x/2"))  # id=2
    repo.add(Camera(name="Third", rtsp_url="rtsp://x/3"))   # id=3
    # Save an explicit order: 3, 1, 2
    settings_store.save({"grid_order": [3, 1, 2]})

    with TestClient(app) as client:
        response = client.get("/grid")

    # The data-camera-id attributes appear in DOM order, so substring index
    # tells us the saved order took effect.
    i3 = response.text.index('data-camera-id="3"')
    i1 = response.text.index('data-camera-id="1"')
    i2 = response.text.index('data-camera-id="2"')
    assert i3 < i1 < i2


def test_grid_appends_unsaved_cameras_at_end(tmp_path, monkeypatch):
    """Cameras added after the order was saved go to the tail, not lost."""
    from ngc_cams import settings_store
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_store, "default_settings_path", lambda: settings_path)
    app, repo = _build()
    repo.add(Camera(name="A", rtsp_url="rtsp://x/1"))  # id=1
    repo.add(Camera(name="B", rtsp_url="rtsp://x/2"))  # id=2
    settings_store.save({"grid_order": [1]})  # only id=1 is in the saved order
    repo.add(Camera(name="C", rtsp_url="rtsp://x/3"))  # id=3 — added after save

    with TestClient(app) as client:
        response = client.get("/grid")

    i1 = response.text.index('data-camera-id="1"')
    i2 = response.text.index('data-camera-id="2"')
    i3 = response.text.index('data-camera-id="3"')
    assert i1 < i2 and i1 < i3


def test_grid_shows_empty_state_when_no_cameras(tmp_path, monkeypatch):
    from ngc_cams import settings_store
    monkeypatch.setattr(settings_store, "default_settings_path",
                        lambda: tmp_path / "settings.json")
    app, _ = _build()
    with TestClient(app) as client:
        response = client.get("/grid")
    assert response.status_code == 200
    assert "No cameras yet" in response.text
    assert "/live.mjpg" not in response.text


def test_grid_marks_recording_cameras(tmp_path, monkeypatch):
    from ngc_cams import settings_store
    monkeypatch.setattr(settings_store, "default_settings_path",
                        lambda: tmp_path / "settings.json")
    app, repo = _build()
    repo.add(Camera(name="OffCam", rtsp_url="rtsp://x/1"))
    repo.add(
        Camera(name="RecCam", rtsp_url="rtsp://x/2", record_mode=RecordMode.VIDEO_ONLY)
    )
    with TestClient(app) as client:
        response = client.get("/grid")
    assert response.status_code == 200
    assert response.text.count("REC</span>") == 1


def test_post_grid_layout_persists_order(tmp_path, monkeypatch):
    from ngc_cams import settings_store
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_store, "default_settings_path", lambda: settings_path)
    app, repo = _build()
    repo.add(Camera(name="A", rtsp_url="rtsp://x/1"))
    repo.add(Camera(name="B", rtsp_url="rtsp://x/2"))
    with TestClient(app) as client:
        response = client.post("/grid/layout", json={"order": [2, 1]})
    assert response.status_code == 200
    assert settings_store.load()["grid_order"] == [2, 1]


def test_post_grid_layout_persists_columns(tmp_path, monkeypatch):
    from ngc_cams import settings_store
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_store, "default_settings_path", lambda: settings_path)
    app, _ = _build()
    with TestClient(app) as client:
        response = client.post("/grid/layout", json={"columns": 4})
    assert response.status_code == 200
    assert settings_store.load()["grid_columns"] == 4


def test_post_grid_layout_accepts_auto_columns(tmp_path, monkeypatch):
    from ngc_cams import settings_store
    monkeypatch.setattr(settings_store, "default_settings_path",
                        lambda: tmp_path / "settings.json")
    app, _ = _build()
    with TestClient(app) as client:
        response = client.post("/grid/layout", json={"columns": "auto"})
    assert response.status_code == 200
    assert settings_store.load()["grid_columns"] == "auto"


def test_post_grid_layout_rejects_out_of_range_columns(tmp_path, monkeypatch):
    from ngc_cams import settings_store
    monkeypatch.setattr(settings_store, "default_settings_path",
                        lambda: tmp_path / "settings.json")
    app, _ = _build()
    with TestClient(app) as client:
        response = client.post("/grid/layout", json={"columns": 99})
    assert response.status_code == 400


def test_post_grid_layout_persists_feed_filter(tmp_path, monkeypatch):
    from ngc_cams import settings_store
    monkeypatch.setattr(settings_store, "default_settings_path",
                        lambda: tmp_path / "settings.json")
    app, _ = _build()
    with TestClient(app) as client:
        response = client.post("/grid/layout", json={"feed_filter": "vhs"})
    assert response.status_code == 200
    assert settings_store.load()["feed_filter"] == "vhs"


def test_post_grid_layout_rejects_unknown_filter(tmp_path, monkeypatch):
    from ngc_cams import settings_store
    monkeypatch.setattr(settings_store, "default_settings_path",
                        lambda: tmp_path / "settings.json")
    app, _ = _build()
    with TestClient(app) as client:
        # Unknown filter value gets silently dropped; since nothing else is
        # in the body, the endpoint replies 400 "nothing to save".
        response = client.post("/grid/layout", json={"feed_filter": "matrix"})
    assert response.status_code == 400
    assert "feed_filter" not in settings_store.load()


def test_grid_applies_saved_feed_filter_class(tmp_path, monkeypatch):
    from ngc_cams import settings_store
    monkeypatch.setattr(settings_store, "default_settings_path",
                        lambda: tmp_path / "settings.json")
    settings_store.save({"feed_filter": "fnaf"})
    app, repo = _build()
    repo.add(Camera(name="Cam", rtsp_url="rtsp://x/main"))
    with TestClient(app) as client:
        response = client.get("/grid")
    assert response.status_code == 200
    assert "fnaf-filter" in response.text
    # Dropdown selection reflects the saved value.
    assert 'value="fnaf" selected' in response.text


def test_grid_filter_dropdown_renders_all_options(tmp_path, monkeypatch):
    from ngc_cams import settings_store
    monkeypatch.setattr(settings_store, "default_settings_path",
                        lambda: tmp_path / "settings.json")
    app, repo = _build()
    repo.add(Camera(name="Cam", rtsp_url="rtsp://x/main"))
    with TestClient(app) as client:
        response = client.get("/grid")
    for opt in ("normal", "fnaf", "static", "vhs", "mgs"):
        assert f'value="{opt}"' in response.text


def test_camera_detail_applies_saved_feed_filter(tmp_path, monkeypatch):
    from ngc_cams import settings_store
    monkeypatch.setattr(settings_store, "default_settings_path",
                        lambda: tmp_path / "settings.json")
    settings_store.save({"feed_filter": "mgs"})
    app, repo = _build()
    stored = repo.add(Camera(name="Cam", rtsp_url="rtsp://x/main"))
    with TestClient(app) as client:
        response = client.get(f"/cameras/{stored.id}")
    assert response.status_code == 200
    assert "mgs-filter" in response.text
