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


def test_segment_repository_delete_older_than_removes_rows_and_returns_paths(tmp_path):
    connection = connect(tmp_path / "db.sqlite3")
    initialize(connection)
    camera_id = _seed_camera(connection)
    segments = SegmentRepository(connection)
    old = segments.add(
        camera_id=camera_id,
        path=Path(r"D:\rec\front\old.mp4"),
        started_at=datetime(2026, 5, 10, 6, 0, 0),
        duration_seconds=600,
        has_audio=False,
    )
    fresh = segments.add(
        camera_id=camera_id,
        path=Path(r"D:\rec\front\fresh.mp4"),
        started_at=datetime(2026, 5, 17, 6, 0, 0),
        duration_seconds=600,
        has_audio=False,
    )

    removed = segments.delete_older_than(camera_id, datetime(2026, 5, 14, 0, 0, 0))

    assert removed == [Path(r"D:\rec\front\old.mp4")]
    remaining = segments.list_by_camera(camera_id)
    assert [s.id for s in remaining] == [fresh.id]
    assert old.id != fresh.id  # sanity


def test_segment_repository_delete_older_than_scopes_to_camera(tmp_path):
    connection = connect(tmp_path / "db.sqlite3")
    initialize(connection)
    camera_a = _seed_camera(connection)
    other = CameraRepository(connection).add(
        Camera(name="Other", rtsp_url="rtsp://other/main")
    )
    segments = SegmentRepository(connection)
    segments.add(
        camera_id=camera_a,
        path=Path(r"D:\rec\a\old.mp4"),
        started_at=datetime(2026, 5, 10, 6, 0, 0),
        duration_seconds=600,
        has_audio=False,
    )
    segments.add(
        camera_id=other.id,
        path=Path(r"D:\rec\b\also-old.mp4"),
        started_at=datetime(2026, 5, 10, 6, 0, 0),
        duration_seconds=600,
        has_audio=False,
    )

    removed = segments.delete_older_than(camera_a, datetime(2026, 5, 14, 0, 0, 0))

    assert removed == [Path(r"D:\rec\a\old.mp4")]
    assert len(segments.list_by_camera(other.id)) == 1


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
