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
) -> dict[int, list[Path]]:
    """Run :func:`prune_camera` for every camera using its own ``retention_days``."""
    return {
        camera.id: prune_camera(
            segments,
            camera_id=camera.id,
            retention_days=camera.retention_days,
            now=now,
            file_remover=file_remover,
        )
        for camera in cameras.list()
    }
