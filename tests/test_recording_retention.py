from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ngc_cams.cameras import CameraRepository
from ngc_cams.db import connect, initialize
from ngc_cams.models import Camera
from ngc_cams.recording.retention import prune_all, prune_camera
from ngc_cams.segments import SegmentRepository


def _seed(connection, *, retention_days: int = 7) -> int:
    repo = CameraRepository(connection)
    stored = repo.add(
        Camera(name="Cam", rtsp_url="rtsp://x/main", retention_days=retention_days)
    )
    return stored.id


def test_prune_camera_deletes_old_rows_and_invokes_file_remover(tmp_path):
    connection = connect(tmp_path / "db.sqlite3")
    initialize(connection)
    camera_id = _seed(connection, retention_days=7)
    segments = SegmentRepository(connection)
    old_path = tmp_path / "old.mp4"
    old_path.write_bytes(b"old")
    fresh_path = tmp_path / "fresh.mp4"
    fresh_path.write_bytes(b"fresh")
    segments.add(
        camera_id=camera_id,
        path=old_path,
        started_at=datetime(2026, 5, 1, 0, 0, 0),
        duration_seconds=600,
        has_audio=False,
    )
    segments.add(
        camera_id=camera_id,
        path=fresh_path,
        started_at=datetime(2026, 5, 16, 0, 0, 0),
        duration_seconds=600,
        has_audio=False,
    )

    removed_calls: list[Path] = []
    deleted = prune_camera(
        segments,
        camera_id=camera_id,
        retention_days=7,
        now=datetime(2026, 5, 17, 12, 0, 0),
        file_remover=removed_calls.append,
    )

    assert deleted == [old_path]
    assert removed_calls == [old_path]
    remaining = segments.list_by_camera(camera_id)
    assert [s.path for s in remaining] == [fresh_path]


def test_prune_camera_swallows_file_remover_errors(tmp_path):
    connection = connect(tmp_path / "db.sqlite3")
    initialize(connection)
    camera_id = _seed(connection, retention_days=7)
    segments = SegmentRepository(connection)
    segments.add(
        camera_id=camera_id,
        path=tmp_path / "missing.mp4",
        started_at=datetime(2026, 5, 1, 0, 0, 0),
        duration_seconds=600,
        has_audio=False,
    )

    def boom(_path: Path) -> None:
        raise OSError("disk gone")

    # Must not raise; row must still be deleted.
    deleted = prune_camera(
        segments,
        camera_id=camera_id,
        retention_days=7,
        now=datetime(2026, 5, 17, 12, 0, 0),
        file_remover=boom,
    )
    assert deleted == [tmp_path / "missing.mp4"]
    assert segments.list_by_camera(camera_id) == []


def test_prune_all_runs_per_camera_with_each_cameras_retention_days(tmp_path):
    connection = connect(tmp_path / "db.sqlite3")
    initialize(connection)
    repo = CameraRepository(connection)
    short = repo.add(Camera(name="Short", rtsp_url="rtsp://a", retention_days=3))
    long_ = repo.add(Camera(name="Long", rtsp_url="rtsp://b", retention_days=30))
    segments = SegmentRepository(connection)
    five_days_ago = datetime(2026, 5, 12, 0, 0, 0)
    segments.add(
        camera_id=short.id,
        path=tmp_path / "short_old.mp4",
        started_at=five_days_ago,
        duration_seconds=600,
        has_audio=False,
    )
    segments.add(
        camera_id=long_.id,
        path=tmp_path / "long_keeps.mp4",
        started_at=five_days_ago,
        duration_seconds=600,
        has_audio=False,
    )

    deleted = prune_all(
        repo,
        segments,
        now=datetime(2026, 5, 17, 0, 0, 0),
        file_remover=lambda p: None,
    )

    # Short camera's 5-day-old segment is past its 3-day retention; long's is not.
    assert deleted[short.id] == [tmp_path / "short_old.mp4"]
    assert deleted[long_.id] == []
    assert len(segments.list_by_camera(short.id)) == 0
    assert len(segments.list_by_camera(long_.id)) == 1
