from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from ngc_cams.cameras import CameraRepository
from ngc_cams.segments import SegmentRepository


def _default_remove(path: Path) -> None:
    path.unlink(missing_ok=True)


def prune_camera(
    segments: SegmentRepository,
    *,
    camera_id: int,
    retention_days: int,
    now: datetime,
    file_remover: Callable[[Path], None] = _default_remove,
) -> list[Path]:
    """Delete recording_segments rows older than ``retention_days`` for one camera.

    For every deleted row, the matching file is removed from disk via
    ``file_remover``. Disk removal errors (missing file, permission denied,
    etc.) are swallowed so a flaky file system never prevents DB cleanup.
    Returns the paths the deleted rows referenced (in chronological order).
    """
    cutoff = now - timedelta(days=retention_days)
    deleted = segments.delete_older_than(camera_id, cutoff)
    for path in deleted:
        try:
            file_remover(path)
        except OSError:
            pass
    return deleted


def prune_all(
    cameras: CameraRepository,
    segments: SegmentRepository,
    *,
    now: datetime,
    file_remover: Callable[[Path], None] = _default_remove,
    retention_days_override: int | None = None,
) -> dict[int, list[Path]]:
    """Run :func:`prune_camera` for every camera.

    By default each camera's own ``retention_days`` applies. Pass
    ``retention_days_override`` to enforce a single global value (the SISI-TV
    Settings page sets this — the per-camera DB column stays in place but
    becomes effectively inert).
    """
    return {
        camera.id: prune_camera(
            segments,
            camera_id=camera.id,
            retention_days=(
                retention_days_override
                if retention_days_override is not None
                else camera.retention_days
            ),
            now=now,
            file_remover=file_remover,
        )
        for camera in cameras.list()
    }


def _default_stat(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def enforce_storage_cap(
    segments: SegmentRepository,
    *,
    storage_limit_bytes: int,
    file_remover: Callable[[Path], None] = _default_remove,
    stat_fn: Callable[[Path], int] = _default_stat,
) -> list[Path]:
    """Drop oldest segments until total on-disk size <= ``storage_limit_bytes``.

    Disabled when ``storage_limit_bytes <= 0``. Iterates the DB in
    ``started_at`` order so the oldest day's recording goes first when the
    cap is hit. Missing files (file deleted manually but row still present)
    cost 0 bytes via ``stat_fn`` so we still clean up the orphan row.
    """
    if storage_limit_bytes <= 0:
        return []
    rows = segments.list_all()
    sizes = [(seg, stat_fn(seg.path)) for seg in rows]
    total = sum(size for _, size in sizes)
    deleted: list[Path] = []
    for seg, size in sizes:
        if total <= storage_limit_bytes:
            break
        path = segments.delete_by_id(seg.id)
        if path is None:
            continue
        try:
            file_remover(path)
        except OSError:
            pass
        total -= size
        deleted.append(path)
    return deleted
