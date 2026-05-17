from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ngc_cams.cameras import CameraRepository
from ngc_cams.db import connect, initialize
from ngc_cams.models import Camera
from ngc_cams.recording.retention import enforce_storage_cap, prune_all, prune_camera
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


def test_prune_all_global_override_replaces_per_camera_retention(tmp_path):
    """retention_days_override (SISI-TV Settings page) forces every camera to
    the same retention regardless of the per-camera value in DB."""
    connection = connect(tmp_path / "db.sqlite3")
    initialize(connection)
    repo = CameraRepository(connection)
    short = repo.add(Camera(name="Short", rtsp_url="rtsp://a", retention_days=3))
    long_ = repo.add(Camera(name="Long", rtsp_url="rtsp://b", retention_days=30))
    segments = SegmentRepository(connection)
    five_days_ago = datetime(2026, 5, 12, 0, 0, 0)
    segments.add(camera_id=short.id, path=tmp_path / "s.mp4",
                 started_at=five_days_ago, duration_seconds=600, has_audio=False)
    segments.add(camera_id=long_.id, path=tmp_path / "l.mp4",
                 started_at=five_days_ago, duration_seconds=600, has_audio=False)

    # Global 2-day cap should prune BOTH cameras' 5-day-old segments, even
    # though the long camera's per-camera retention is 30.
    deleted = prune_all(
        repo,
        segments,
        now=datetime(2026, 5, 17, 0, 0, 0),
        file_remover=lambda p: None,
        retention_days_override=2,
    )
    assert deleted[short.id] == [tmp_path / "s.mp4"]
    assert deleted[long_.id] == [tmp_path / "l.mp4"]


def test_enforce_storage_cap_drops_oldest_until_under_limit(tmp_path):
    connection = connect(tmp_path / "db.sqlite3")
    initialize(connection)
    camera_id = _seed(connection, retention_days=30)
    segments = SegmentRepository(connection)
    # Three segments of 100 bytes each, oldest at 06:00.
    for i in range(3):
        path = tmp_path / f"{i}.mp4"
        path.write_bytes(b"x" * 100)
        segments.add(
            camera_id=camera_id,
            path=path,
            started_at=datetime(2026, 5, 17, 6 + i, 0, 0),
            duration_seconds=600,
            has_audio=False,
        )

    deleted = enforce_storage_cap(segments, storage_limit_bytes=210)

    # 3 files * 100 bytes = 300 total. Cap 210 means we drop oldest until <= 210.
    # Dropping 1 file -> 200 bytes <= 210 ✓
    assert deleted == [tmp_path / "0.mp4"]
    remaining = [s.path for s in segments.list_all()]
    assert remaining == [tmp_path / "1.mp4", tmp_path / "2.mp4"]
    assert not (tmp_path / "0.mp4").exists()


def test_enforce_storage_cap_no_op_when_under_limit(tmp_path):
    connection = connect(tmp_path / "db.sqlite3")
    initialize(connection)
    camera_id = _seed(connection)
    segments = SegmentRepository(connection)
    path = tmp_path / "small.mp4"
    path.write_bytes(b"x" * 50)
    segments.add(camera_id=camera_id, path=path,
                 started_at=datetime(2026, 5, 17, 6, 0, 0),
                 duration_seconds=600, has_audio=False)

    deleted = enforce_storage_cap(segments, storage_limit_bytes=1_000)

    assert deleted == []
    assert len(segments.list_all()) == 1
    assert path.exists()


def test_enforce_storage_cap_disabled_when_limit_zero(tmp_path):
    connection = connect(tmp_path / "db.sqlite3")
    initialize(connection)
    camera_id = _seed(connection)
    segments = SegmentRepository(connection)
    path = tmp_path / "keepme.mp4"
    path.write_bytes(b"x" * 100)
    segments.add(camera_id=camera_id, path=path,
                 started_at=datetime(2026, 5, 17, 6, 0, 0),
                 duration_seconds=600, has_audio=False)

    deleted = enforce_storage_cap(segments, storage_limit_bytes=0)

    assert deleted == []
    assert len(segments.list_all()) == 1


def test_enforce_storage_cap_uses_injected_file_remover_and_stat_fn(tmp_path):
    connection = connect(tmp_path / "db.sqlite3")
    initialize(connection)
    camera_id = _seed(connection)
    segments = SegmentRepository(connection)
    # File paths are irrelevant — we'll inject stat + remover.
    for i in range(3):
        segments.add(
            camera_id=camera_id,
            path=tmp_path / f"phantom{i}.mp4",
            started_at=datetime(2026, 5, 17, 6 + i, 0, 0),
            duration_seconds=600,
            has_audio=False,
        )

    remove_calls: list[Path] = []
    deleted = enforce_storage_cap(
        segments,
        storage_limit_bytes=150,  # 3 * 100 = 300; need to drop 2 files
        stat_fn=lambda _path: 100,
        file_remover=remove_calls.append,
    )
    assert len(deleted) == 2
    assert len(remove_calls) == 2
    assert [s.path.name for s in segments.list_all()] == ["phantom2.mp4"]
