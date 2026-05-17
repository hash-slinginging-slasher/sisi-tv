from __future__ import annotations

import pytest

from ngc_cams.cameras import CameraRepository
from ngc_cams.db import connect, initialize
from ngc_cams.models import Camera, RecordMode


def test_initialize_creates_core_tables(tmp_path):
    connection = connect(tmp_path / "ngc-cams.sqlite3")
    initialize(connection)

    table_names = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }

    assert "cameras" in table_names
    assert "recording_segments" in table_names


def test_camera_repository_adds_lists_updates_and_deletes(tmp_path):
    connection = connect(tmp_path / "ngc-cams.sqlite3")
    initialize(connection)
    cameras = CameraRepository(connection)

    stored = cameras.add(
        Camera(
            name="Front gate",
            rtsp_url="rtsp://192.168.1.18/main",
            sub_stream_url="rtsp://192.168.1.18/sub",
            ptz_enabled=True,
            record_mode=RecordMode.VIDEO_AUDIO,
        )
    )

    assert stored.id > 0
    assert cameras.list()[0].name == "Front gate"

    updated = cameras.update(
        stored.id,
        Camera(
            name="Gate",
            rtsp_url="rtsp://192.168.1.18/main",
            record_mode=RecordMode.VIDEO_ONLY,
        ),
    )

    assert updated.name == "Gate"
    assert updated.record_mode == RecordMode.VIDEO_ONLY
    assert cameras.delete(stored.id) is True
    assert cameras.get(stored.id) is None


def test_camera_repository_update_missing_camera_raises(tmp_path):
    connection = connect(tmp_path / "ngc-cams.sqlite3")
    initialize(connection)

    with pytest.raises(KeyError):
        CameraRepository(connection).update(999, Camera(name="Missing", rtsp_url="rtsp://x"))
