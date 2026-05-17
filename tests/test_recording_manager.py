from __future__ import annotations

import signal
import sys
from datetime import datetime
from pathlib import Path

import pytest

from ngc_cams.cameras import CameraRepository
from ngc_cams.db import connect, initialize
from ngc_cams.models import Camera, RecordMode, StoredCamera
from ngc_cams.recording.manager import RecordingManager
from ngc_cams.segments import SegmentRepository


class FakePopen:
    def __init__(self, args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.terminated = False
        self.killed = False
        self.signaled_with: int | None = None
        self._returncode: int | None = None

    def poll(self) -> int | None:
        return self._returncode

    def send_signal(self, sig: int) -> None:
        self.signaled_with = sig
        # Mirror ffmpeg's graceful-exit behaviour: clean shutdown on CTRL_BREAK/SIGINT.
        self._returncode = 0

    def terminate(self) -> None:
        self.terminated = True
        self._returncode = 0

    def kill(self) -> None:
        self.killed = True
        self._returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        return self._returncode if self._returncode is not None else 0

    def simulate_exit(self, returncode: int = 1) -> None:
        self._returncode = returncode


class FakeFactory:
    def __init__(self) -> None:
        self.processes: list[FakePopen] = []

    def __call__(self, args, **kwargs) -> FakePopen:
        process = FakePopen(args, **kwargs)
        self.processes.append(process)
        return process


@pytest.fixture()
def connection(tmp_path):
    conn = connect(tmp_path / "db.sqlite3")
    initialize(conn)
    yield conn
    conn.close()


@pytest.fixture()
def cameras_repo(connection):
    return CameraRepository(connection)


@pytest.fixture()
def segments_repo(connection):
    return SegmentRepository(connection)


def _add(repo: CameraRepository, name: str = "Front", mode: RecordMode = RecordMode.VIDEO_ONLY
         ) -> StoredCamera:
    return repo.add(Camera(name=name, rtsp_url=f"rtsp://camera/{name}", record_mode=mode))


def _make_manager(tmp_path, cameras_repo, segments_repo, factory, now=None,
                  ffmpeg_resolver=lambda: "ffmpeg"):
    clock = (lambda: now) if isinstance(now, datetime) else (now or datetime.now)
    return RecordingManager(
        cameras_repo,
        segments_repo,
        recording_root=tmp_path,
        popen_factory=factory,
        clock=clock,
        ffmpeg_resolver=ffmpeg_resolver,
    )


def test_start_spawns_ffmpeg_with_segment_list(tmp_path, cameras_repo, segments_repo):
    factory = FakeFactory()
    manager = _make_manager(tmp_path, cameras_repo, segments_repo, factory,
                            now=datetime(2026, 5, 17, 6, 0, 0))
    camera = _add(cameras_repo)

    manager.start(camera)

    assert len(factory.processes) == 1
    cmd = factory.processes[0].args
    assert cmd[0] == "ffmpeg"
    assert camera.rtsp_url in cmd
    assert "-segment_list" in cmd
    assert manager.is_recording(camera.id)


def test_start_creates_dated_output_directory(tmp_path, cameras_repo, segments_repo):
    factory = FakeFactory()
    manager = _make_manager(tmp_path, cameras_repo, segments_repo, factory,
                            now=datetime(2026, 5, 17))
    camera = _add(cameras_repo)
    manager.start(camera)
    assert (tmp_path / "Front" / "2026-05-17").is_dir()


def test_start_rejects_off_mode(tmp_path, cameras_repo, segments_repo):
    factory = FakeFactory()
    manager = _make_manager(tmp_path, cameras_repo, segments_repo, factory)
    camera = _add(cameras_repo, mode=RecordMode.OFF)
    with pytest.raises(ValueError):
        manager.start(camera)


def test_start_is_idempotent(tmp_path, cameras_repo, segments_repo):
    factory = FakeFactory()
    manager = _make_manager(tmp_path, cameras_repo, segments_repo, factory,
                            now=datetime(2026, 5, 17))
    camera = _add(cameras_repo)
    manager.start(camera)
    manager.start(camera)
    assert len(factory.processes) == 1


def test_apply_modes_starts_only_recording_cameras(tmp_path, cameras_repo, segments_repo):
    factory = FakeFactory()
    manager = _make_manager(tmp_path, cameras_repo, segments_repo, factory,
                            now=datetime(2026, 5, 17))
    _add(cameras_repo, name="On", mode=RecordMode.VIDEO_ONLY)
    _add(cameras_repo, name="Off", mode=RecordMode.OFF)
    manager.apply_modes()
    assert len(factory.processes) == 1


def test_apply_modes_stops_cameras_now_off(tmp_path, cameras_repo, segments_repo):
    factory = FakeFactory()
    manager = _make_manager(tmp_path, cameras_repo, segments_repo, factory,
                            now=datetime(2026, 5, 17))
    camera = _add(cameras_repo)
    manager.apply_modes()
    assert manager.is_recording(camera.id)
    cameras_repo.update(
        camera.id,
        Camera(name=camera.name, rtsp_url=camera.rtsp_url, record_mode=RecordMode.OFF),
    )
    manager.apply_modes()
    assert not manager.is_recording(camera.id)
    # Graceful path: signal sent, process exits cleanly, terminate/kill not reached.
    assert factory.processes[0].signaled_with is not None
    assert factory.processes[0].terminated is False
    assert factory.processes[0].killed is False


def test_stop_sends_graceful_signal_so_ffmpeg_flushes_trailer(
    tmp_path, cameras_repo, segments_repo
):
    factory = FakeFactory()
    manager = _make_manager(tmp_path, cameras_repo, segments_repo, factory,
                            now=datetime(2026, 5, 17))
    camera = _add(cameras_repo)
    manager.start(camera)
    manager.stop(camera.id)

    expected = (
        signal.CTRL_BREAK_EVENT
        if sys.platform.startswith("win") and hasattr(signal, "CTRL_BREAK_EVENT")
        else signal.SIGINT
    )
    assert factory.processes[0].signaled_with == expected


def test_start_passes_creationflags_on_windows(tmp_path, cameras_repo, segments_repo):
    factory = FakeFactory()
    manager = _make_manager(tmp_path, cameras_repo, segments_repo, factory,
                            now=datetime(2026, 5, 17))
    camera = _add(cameras_repo)
    manager.start(camera)

    flags = factory.processes[0].kwargs.get("creationflags", 0)
    if sys.platform.startswith("win"):
        import subprocess as _sp
        assert flags == _sp.CREATE_NEW_PROCESS_GROUP
    else:
        assert flags == 0


def test_stop_all_terminates_all_processes(tmp_path, cameras_repo, segments_repo):
    factory = FakeFactory()
    manager = _make_manager(tmp_path, cameras_repo, segments_repo, factory,
                            now=datetime(2026, 5, 17))
    _add(cameras_repo, name="A")
    _add(cameras_repo, name="B")
    manager.apply_modes()
    manager.stop_all()
    # Each child got a graceful shutdown signal and exited cleanly.
    assert all(p.signaled_with is not None for p in factory.processes)
    assert manager._recordings == {}  # type: ignore[attr-defined]


def test_poll_inserts_segments_from_csv(tmp_path, cameras_repo, segments_repo):
    factory = FakeFactory()
    manager = _make_manager(tmp_path, cameras_repo, segments_repo, factory,
                            now=datetime(2026, 5, 17, 6, 0, 0))
    camera = _add(cameras_repo)
    manager.start(camera)
    list_path = tmp_path / "Front" / "2026-05-17" / "segments.csv"
    list_path.write_text(
        "2026-05-17_06-00-00.mp4,0.000000,600.000000\n"
        "2026-05-17_06-10-00.mp4,0.000000,600.000000\n",
        encoding="utf-8",
    )

    manager.poll()

    rows = segments_repo.list_by_camera(camera.id)
    assert [r.started_at for r in rows] == [
        datetime(2026, 5, 17, 6, 0, 0),
        datetime(2026, 5, 17, 6, 10, 0),
    ]
    assert all(r.duration_seconds == 600 for r in rows)
    assert all(r.has_audio is False for r in rows)
    assert rows[0].path == Path(
        str(tmp_path / "Front" / "2026-05-17" / "2026-05-17_06-00-00.mp4")
    )


def test_poll_only_inserts_new_lines_each_tick(tmp_path, cameras_repo, segments_repo):
    factory = FakeFactory()
    manager = _make_manager(tmp_path, cameras_repo, segments_repo, factory,
                            now=datetime(2026, 5, 17, 6, 0, 0))
    camera = _add(cameras_repo)
    manager.start(camera)
    list_path = tmp_path / "Front" / "2026-05-17" / "segments.csv"

    list_path.write_text("2026-05-17_06-00-00.mp4,0.000000,600.000000\n", encoding="utf-8")
    manager.poll()
    assert len(segments_repo.list_by_camera(camera.id)) == 1

    with list_path.open("a", encoding="utf-8") as f:
        f.write("2026-05-17_06-10-00.mp4,0.000000,600.000000\n")
    manager.poll()
    assert len(segments_repo.list_by_camera(camera.id)) == 2


def test_poll_holds_partial_trailing_line_until_completed(tmp_path, cameras_repo, segments_repo):
    factory = FakeFactory()
    manager = _make_manager(tmp_path, cameras_repo, segments_repo, factory,
                            now=datetime(2026, 5, 17, 6, 0, 0))
    camera = _add(cameras_repo)
    manager.start(camera)
    list_path = tmp_path / "Front" / "2026-05-17" / "segments.csv"

    list_path.write_text(
        "2026-05-17_06-00-00.mp4,0.000000,600.000000\n"
        "2026-05-17_06-10-00.mp4,0.0",
        encoding="utf-8",
    )
    manager.poll()
    assert len(segments_repo.list_by_camera(camera.id)) == 1

    with list_path.open("a", encoding="utf-8") as f:
        f.write("00000,600.000000\n")
    manager.poll()
    assert len(segments_repo.list_by_camera(camera.id)) == 2


def test_poll_records_audio_flag_for_video_audio_mode(tmp_path, cameras_repo, segments_repo):
    factory = FakeFactory()
    manager = _make_manager(tmp_path, cameras_repo, segments_repo, factory,
                            now=datetime(2026, 5, 17, 6, 0, 0))
    camera = _add(cameras_repo, name="Loud", mode=RecordMode.VIDEO_AUDIO)
    manager.start(camera)
    list_path = tmp_path / "Loud" / "2026-05-17" / "segments.csv"
    list_path.write_text("2026-05-17_06-00-00.mp4,0.0,600.0\n", encoding="utf-8")

    manager.poll()
    rows = segments_repo.list_by_camera(camera.id)
    assert rows[0].has_audio is True


def test_start_swallows_filenotfound_and_marks_camera_failed(
    tmp_path, cameras_repo, segments_repo
):
    def raise_not_found(*args, **kwargs):
        raise FileNotFoundError(2, "The system cannot find the file specified")

    manager = _make_manager(
        tmp_path, cameras_repo, segments_repo, raise_not_found,
        now=datetime(2026, 5, 17),
    )
    camera = _add(cameras_repo)

    manager.start(camera)  # must not raise

    assert manager.ffmpeg_missing is True
    assert manager.is_recording(camera.id) is False
    # A second start() must not spawn either (camera is in the failed set).
    manager.start(camera)
    assert manager.is_recording(camera.id) is False


def test_apply_modes_does_not_crash_when_ffmpeg_missing(
    tmp_path, cameras_repo, segments_repo
):
    def raise_not_found(*args, **kwargs):
        raise FileNotFoundError(2, "ffmpeg missing")

    manager = _make_manager(
        tmp_path, cameras_repo, segments_repo, raise_not_found,
        now=datetime(2026, 5, 17),
    )
    _add(cameras_repo, name="A")
    _add(cameras_repo, name="B")

    manager.apply_modes()  # must not raise

    assert manager.ffmpeg_missing is True
    assert len(manager._recordings) == 0  # type: ignore[attr-defined]


def test_start_uses_resolved_ffmpeg_path_as_command(tmp_path, cameras_repo, segments_repo):
    factory = FakeFactory()
    manager = _make_manager(
        tmp_path, cameras_repo, segments_repo, factory,
        now=datetime(2026, 5, 17),
        ffmpeg_resolver=lambda: r"C:\tools\ffmpeg\bin\ffmpeg.exe",
    )
    camera = _add(cameras_repo)

    manager.start(camera)

    assert factory.processes[0].args[0] == r"C:\tools\ffmpeg\bin\ffmpeg.exe"


def test_start_skips_spawn_when_resolver_returns_none(tmp_path, cameras_repo, segments_repo):
    factory = FakeFactory()
    manager = _make_manager(
        tmp_path, cameras_repo, segments_repo, factory,
        now=datetime(2026, 5, 17),
        ffmpeg_resolver=lambda: None,
    )
    camera = _add(cameras_repo)

    manager.start(camera)

    assert manager.ffmpeg_missing is True
    assert manager.is_recording(camera.id) is False
    assert factory.processes == []  # popen_factory must not be called


def test_ffmpeg_available_reflects_resolver(tmp_path, cameras_repo, segments_repo):
    factory = FakeFactory()
    available = RecordingManager(
        cameras_repo, segments_repo, recording_root=tmp_path,
        popen_factory=factory, ffmpeg_resolver=lambda: "/usr/bin/ffmpeg",
    )
    missing = RecordingManager(
        cameras_repo, segments_repo, recording_root=tmp_path,
        popen_factory=factory, ffmpeg_resolver=lambda: None,
    )
    assert available.ffmpeg_available() is True
    assert missing.ffmpeg_available() is False


def test_poll_restarts_crashed_process_after_backoff(tmp_path, cameras_repo, segments_repo):
    factory = FakeFactory()
    fake_now = [datetime(2026, 5, 17, 6, 0, 0)]
    manager = RecordingManager(
        cameras_repo,
        segments_repo,
        recording_root=tmp_path,
        popen_factory=factory,
        clock=lambda: fake_now[0],
    )
    camera = _add(cameras_repo)
    manager.start(camera)
    factory.processes[0].simulate_exit(1)

    manager.poll()
    assert len(factory.processes) == 1  # backoff scheduled, not yet expired

    fake_now[0] = datetime(2026, 5, 17, 6, 0, 30)
    manager.poll()
    assert len(factory.processes) == 2  # restarted
    assert manager.is_recording(camera.id)


class _FakeDiskUsage:
    def __init__(self, free_bytes: int) -> None:
        self.total = 100 * 1_000_000_000
        self.used = self.total - free_bytes
        self.free = free_bytes


def test_disk_guard_blocks_start_when_free_below_threshold(
    tmp_path, cameras_repo, segments_repo, caplog
):
    factory = FakeFactory()
    # 5 GB free, guard says require 10 GB
    disk_calls: list[Path] = []

    def fake_disk_usage(path: Path) -> _FakeDiskUsage:
        disk_calls.append(path)
        return _FakeDiskUsage(free_bytes=5 * 1_000_000_000)

    manager = RecordingManager(
        cameras_repo,
        segments_repo,
        recording_root=tmp_path,
        popen_factory=factory,
        ffmpeg_resolver=lambda: "ffmpeg",
        disk_guard_free_gb=10,
        disk_usage_fn=fake_disk_usage,
    )
    camera = _add(cameras_repo)

    import logging as _logging
    with caplog.at_level(_logging.WARNING, logger="ngc_cams.recording.manager"):
        manager.start(camera)

    assert factory.processes == []
    assert not manager.is_recording(camera.id)
    assert camera.id not in manager._failed_camera_ids  # transient, not permanent
    assert disk_calls == [tmp_path]
    assert any(
        "Free disk under 10 GB" in record.message for record in caplog.records
    )


def test_disk_guard_logs_low_disk_warning_only_once(
    tmp_path, cameras_repo, segments_repo, caplog
):
    factory = FakeFactory()
    manager = RecordingManager(
        cameras_repo,
        segments_repo,
        recording_root=tmp_path,
        popen_factory=factory,
        ffmpeg_resolver=lambda: "ffmpeg",
        disk_guard_free_gb=10,
        disk_usage_fn=lambda _: _FakeDiskUsage(free_bytes=1 * 1_000_000_000),
    )
    camera = _add(cameras_repo)

    import logging as _logging
    with caplog.at_level(_logging.WARNING, logger="ngc_cams.recording.manager"):
        manager.start(camera)
        manager.start(camera)
        manager.start(camera)

    low_warnings = [
        record for record in caplog.records if "Free disk under" in record.message
    ]
    assert len(low_warnings) == 1, "warning should fire once per low-disk episode"


def test_disk_guard_resumes_and_logs_recovery_when_disk_returns(
    tmp_path, cameras_repo, segments_repo, caplog
):
    factory = FakeFactory()
    free_holder = [1 * 1_000_000_000]  # start low

    manager = RecordingManager(
        cameras_repo,
        segments_repo,
        recording_root=tmp_path,
        popen_factory=factory,
        ffmpeg_resolver=lambda: "ffmpeg",
        disk_guard_free_gb=10,
        disk_usage_fn=lambda _: _FakeDiskUsage(free_bytes=free_holder[0]),
    )
    camera = _add(cameras_repo)

    import logging as _logging
    with caplog.at_level(_logging.INFO, logger="ngc_cams.recording.manager"):
        manager.start(camera)  # blocked
        assert factory.processes == []
        free_holder[0] = 50 * 1_000_000_000  # disk recovered
        manager.start(camera)  # should spawn now

    assert len(factory.processes) == 1
    assert manager.is_recording(camera.id)
    assert any(
        "Free disk recovered" in record.message for record in caplog.records
    )


def test_disk_guard_disabled_when_threshold_none(
    tmp_path, cameras_repo, segments_repo
):
    factory = FakeFactory()
    # Even a "0 free" disk shouldn't block when guard is None.
    manager = RecordingManager(
        cameras_repo,
        segments_repo,
        recording_root=tmp_path,
        popen_factory=factory,
        ffmpeg_resolver=lambda: "ffmpeg",
        disk_guard_free_gb=None,
        disk_usage_fn=lambda _: _FakeDiskUsage(free_bytes=0),
    )
    camera = _add(cameras_repo)
    manager.start(camera)
    assert len(factory.processes) == 1


def test_disk_guard_does_not_block_when_disk_usage_call_fails(
    tmp_path, cameras_repo, segments_repo
):
    factory = FakeFactory()

    def failing(_path: Path) -> _FakeDiskUsage:
        raise OSError("disk gone")

    manager = RecordingManager(
        cameras_repo,
        segments_repo,
        recording_root=tmp_path,
        popen_factory=factory,
        ffmpeg_resolver=lambda: "ffmpeg",
        disk_guard_free_gb=10,
        disk_usage_fn=failing,
    )
    camera = _add(cameras_repo)
    manager.start(camera)
    # Fail-open: if we can't check, don't block recording.
    assert len(factory.processes) == 1
