from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from ngc_cams.cameras import CameraRepository
from ngc_cams.db import initialize
from ngc_cams.models import Camera
from ngc_cams.segments import SegmentRepository
from ngc_cams_web.composition import build_app


def _build(tmp_path: Path):
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    initialize(connection)
    repo = CameraRepository(connection)
    segments = SegmentRepository(connection)
    stored = repo.add(Camera(name="Cam 1", rtsp_url="rtsp://x/main"))
    # Drop a real .mp4 on disk so FileResponse has something to serve.
    mp4 = tmp_path / "2026-05-17_15-57-54.mp4"
    mp4.write_bytes(b"\x00\x00\x00\x1cftypisom" + b"\x00" * 1024)
    saved = segments.add(
        camera_id=stored.id,
        path=mp4,
        started_at=datetime(2026, 5, 17, 15, 57, 54),
        duration_seconds=56,
        has_audio=False,
    )
    app = build_app(
        cameras=repo,
        discovery=None,
        recording_manager=None,
        segments=segments,
    )
    return app, repo, segments, stored, saved


def test_recording_detail_renders_video_tag_for_the_segment(tmp_path):
    app, _, _, stored, saved = _build(tmp_path)
    with TestClient(app) as client:
        response = client.get(f"/recordings/{saved.id}")
    assert response.status_code == 200
    assert "<video" in response.text
    assert f'src="/recordings/{saved.id}/file"' in response.text
    # Metadata block surfaces camera name (uppercased by template) + duration.
    assert stored.name.upper() in response.text
    assert "56" in response.text  # duration


def test_recording_detail_404_for_unknown_id(tmp_path):
    app, _, _, _, _ = _build(tmp_path)
    with TestClient(app) as client:
        response = client.get("/recordings/9999")
    assert response.status_code == 404


def test_recording_file_serves_mp4_with_correct_content_type(tmp_path):
    app, _, _, _, saved = _build(tmp_path)
    with TestClient(app) as client:
        response = client.get(f"/recordings/{saved.id}/file")
    assert response.status_code == 200
    assert response.headers["content-type"] == "video/mp4"
    assert response.content.startswith(b"\x00\x00\x00\x1cftypisom")


def test_recording_file_supports_byte_range_requests(tmp_path):
    """Browsers issue Range requests to scrub. FileResponse handles this
    automatically; this test pins that the route delivers 206 Partial."""
    app, _, _, _, saved = _build(tmp_path)
    with TestClient(app) as client:
        response = client.get(
            f"/recordings/{saved.id}/file", headers={"Range": "bytes=0-15"}
        )
    assert response.status_code == 206
    assert response.headers["content-range"].startswith("bytes 0-15/")
    assert len(response.content) == 16


def test_recording_file_404_when_file_deleted_under_us(tmp_path):
    """Row exists but the .mp4 was removed (manual cleanup, drive ejected)."""
    app, _, _, _, saved = _build(tmp_path)
    # Delete the file the row points at.
    saved.path.unlink()
    with TestClient(app) as client:
        response = client.get(f"/recordings/{saved.id}/file")
    assert response.status_code == 404


def test_events_page_links_each_row_to_the_recording_player(tmp_path):
    app, _, _, _, saved = _build(tmp_path)
    with TestClient(app) as client:
        response = client.get("/events")
    assert response.status_code == 200
    assert f'href="/recordings/{saved.id}"' in response.text
