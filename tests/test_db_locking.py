"""Concurrency hardening for the shared sqlite3 connection.

Routes run on Starlette's threadpool, the lifespan poller runs on the event
loop, and `RecordingManager._ingest_new_segments` is invoked from the poller.
All three share one connection (with `check_same_thread=False`). Without the
per-connection lock, multi-statement repo methods like `CameraRepository.update`
(`UPDATE ... ; SELECT ...`) can interleave between threads, producing stale
reads or `database is locked` errors.

These tests hammer the repos from many threads and assert: no exceptions, every
write took effect, and the final row count is exactly what we expected.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from ngc_cams.cameras import CameraRepository
from ngc_cams.db import connect, initialize, lock_for
from ngc_cams.models import Camera, RecordMode
from ngc_cams.segments import SegmentRepository


def test_lock_for_returns_same_instance_per_connection(tmp_path):
    connection = connect(tmp_path / "db.sqlite3")
    initialize(connection)
    lock_a = lock_for(connection)
    lock_b = lock_for(connection)
    assert lock_a is lock_b


def test_lock_for_attaches_lock_to_raw_sqlite_connection(tmp_path):
    """`sqlite3.connect(":memory:")` style tests must still get a lock."""
    import sqlite3

    raw = sqlite3.connect(":memory:")
    raw.row_factory = sqlite3.Row
    initialize(raw)
    lock = lock_for(raw)
    assert isinstance(lock, type(threading.RLock()))
    assert lock is lock_for(raw)  # idempotent


def test_concurrent_record_mode_toggles_dont_corrupt_state(tmp_path):
    """Concrete reproduction of the TOCTOU the lock prevents.

    Without the lock, `update()` does `execute(UPDATE)` -> `commit()` ->
    `self.get(camera_id)`. If two threads call `update` simultaneously, one's
    `get()` can read the *other's* mid-flight state.
    """
    connection = connect(tmp_path / "db.sqlite3")
    initialize(connection)
    cameras = CameraRepository(connection)
    stored = cameras.add(Camera(name="Cam", rtsp_url="rtsp://x/main"))

    def toggle_once() -> RecordMode:
        current = cameras.get(stored.id)
        assert current is not None
        next_mode = (
            RecordMode.VIDEO_ONLY if current.record_mode == RecordMode.OFF else RecordMode.OFF
        )
        result = cameras.update(stored.id, replace(current, record_mode=next_mode))
        return result.record_mode

    errors: list[BaseException] = []

    def worker(_: int) -> None:
        try:
            for _ in range(20):
                toggle_once()
        except BaseException as exc:  # noqa: BLE001 — surface any thread crash
            errors.append(exc)

    with ThreadPoolExecutor(max_workers=8) as pool:
        for fut in as_completed([pool.submit(worker, i) for i in range(8)]):
            fut.result()

    assert errors == [], f"thread crashes: {errors!r}"
    # 8 workers * 20 toggles = 160 total state changes. Final mode is either
    # OFF or VIDEO_ONLY depending on parity, but the row must still exist and
    # be readable — that's what would have broken under stale reads.
    final = cameras.get(stored.id)
    assert final is not None
    assert final.record_mode in (RecordMode.OFF, RecordMode.VIDEO_ONLY)


def test_concurrent_segment_inserts_all_persist(tmp_path):
    """Every insert from every thread must survive."""
    connection = connect(tmp_path / "db.sqlite3")
    initialize(connection)
    cameras = CameraRepository(connection)
    stored = cameras.add(Camera(name="Cam", rtsp_url="rtsp://x/main"))
    segments = SegmentRepository(connection)

    THREADS = 6
    PER_THREAD = 25
    errors: list[BaseException] = []

    def worker(thread_idx: int) -> None:
        try:
            for i in range(PER_THREAD):
                segments.add(
                    camera_id=stored.id,
                    # `path` has a UNIQUE constraint — keep thread+i unique
                    path=Path(f"D:/rec/cam/{thread_idx}-{i}.mp4"),
                    started_at=datetime(2026, 5, 17, thread_idx, i % 60, 0),
                    duration_seconds=600,
                    has_audio=False,
                )
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        for fut in as_completed([pool.submit(worker, t) for t in range(THREADS)]):
            fut.result()

    assert errors == [], f"thread crashes: {errors!r}"
    assert len(segments.list_by_camera(stored.id)) == THREADS * PER_THREAD


def test_lock_for_serializes_explicit_callers(tmp_path):
    """`lock_for` returns a real `RLock` that genuinely serializes contention.

    Tests that go through repo methods (above) prove the lock works under load;
    this one isolates the helper itself: two threads each acquire the same
    lock around a non-atomic read-modify-write, and the final count must match
    the number of increments.
    """
    connection = connect(tmp_path / "db.sqlite3")
    lock = lock_for(connection)
    counter = {"value": 0}
    iterations = 5_000

    def worker() -> None:
        for _ in range(iterations):
            with lock:
                # read-modify-write — without a lock this loses updates.
                counter["value"] = counter["value"] + 1

    with ThreadPoolExecutor(max_workers=4) as pool:
        for fut in as_completed([pool.submit(worker) for _ in range(4)]):
            fut.result()

    assert counter["value"] == 4 * iterations
