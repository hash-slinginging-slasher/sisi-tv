from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class StoredSegment:
    id: int
    camera_id: int
    path: Path
    started_at: datetime
    duration_seconds: int | None
    has_audio: bool


class SegmentRepository:
    """Append-only access to ``recording_segments``.

    The recording manager calls :meth:`add` once per segment that ffmpeg finishes
    writing. Retention cleanup (a separate kanban card) reads back via
    :meth:`list_by_camera`.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def add(
        self,
        camera_id: int,
        path: Path,
        started_at: datetime,
        duration_seconds: int | None,
        has_audio: bool,
    ) -> StoredSegment:
        cursor = self._connection.execute(
            """
            INSERT INTO recording_segments (
                camera_id, path, started_at, duration_seconds, has_audio
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                camera_id,
                str(path),
                started_at.isoformat(timespec="seconds"),
                duration_seconds,
                int(has_audio),
            ),
        )
        self._connection.commit()
        return StoredSegment(
            id=cursor.lastrowid,
            camera_id=camera_id,
            path=path,
            started_at=started_at,
            duration_seconds=duration_seconds,
            has_audio=has_audio,
        )

    def list_by_camera(self, camera_id: int) -> list[StoredSegment]:
        rows = self._connection.execute(
            """
            SELECT id, camera_id, path, started_at, duration_seconds, has_audio
            FROM recording_segments
            WHERE camera_id = ?
            ORDER BY started_at
            """,
            (camera_id,),
        )
        return [
            StoredSegment(
                id=row["id"],
                camera_id=row["camera_id"],
                path=Path(row["path"]),
                started_at=datetime.fromisoformat(row["started_at"]),
                duration_seconds=row["duration_seconds"],
                has_audio=bool(row["has_audio"]),
            )
            for row in rows
        ]
