from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ngc_cams.cameras import CameraRepository
from ngc_cams.db import connect, initialize
from ngc_cams.models import Camera, RecordMode
from ngc_cams.segments import SegmentRepository


def _seed_camera(connection) -> int:
    repo = CameraRepository(connection)
    stored = repo.add(
        Camera(
            name="Front gate",
            rtsp_url="rtsp://camera/main",
            record_mode=RecordMode.VIDEO_ONLY,
        )
    )
    return stored.id


def test_segment_repository_add_round_trips(tmp_path):
    connection = connect(tmp_path / "db.sqlite3")
    initialize(connection)
    camera_id = _seed_camera(connection)
    segments = SegmentRepository(connection)

    stored = segments.add(
        camera_id=camera_id,
        path=Path(r"D:\rec\front\2026-05-17\2026-05-17_06-00-00.mp4"),
        started_at=datetime(2026, 5, 17, 6, 0, 0),
        duration_seconds=600,
        has_audio=False,
    )

    assert stored.id > 0
    assert stored.camera_id == camera_id
    listed = segments.list_by_camera(camera_id)
    assert len(listed) == 1
    assert listed[0].path == Path(r"D:\rec\front\2026-05-17\2026-05-17_06-00-00.mp4")
    assert listed[0].duration_seconds == 600
    assert listed[0].has_audio is False


def test_segment_rows_cascade_delete_with_camera(tmp_path):
    connection = connect(tmp_path / "db.sqlite3")
    initialize(connection)
    camera_id = _seed_camera(connection)
    segments = SegmentRepository(connection)
    segments.add(
        camera_id=camera_id,
        path=Path(r"D:\rec\front\seg.mp4"),
        started_at=datetime(2026, 5, 17, 6, 0, 0),
        duration_seconds=600,
        has_audio=True,
    )

    CameraRepository(connection).delete(camera_id)

    assert segments.list_by_camera(camera_id) == []


def test_segment_repository_orders_by_started_at(tmp_path):
    connection = connect(tmp_path / "db.sqlite3")
    initialize(connection)
    camera_id = _seed_camera(connection)
    segments = SegmentRepository(connection)
    segments.add(
        camera_id=camera_id,
        path=Path(r"D:\rec\front\b.mp4"),
        started_at=datetime(2026, 5, 17, 7, 0, 0),
        duration_seconds=600,
        has_audio=False,
    )
    segments.add(
        camera_id=camera_id,
        path=Path(r"D:\rec\front\a.mp4"),
        started_at=datetime(2026, 5, 17, 6, 0, 0),
        duration_seconds=600,
        has_audio=False,
    )

    listed = segments.list_by_camera(camera_id)
    assert [s.path.name for s in listed] == ["a.mp4", "b.mp4"]
