from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ngc_cams.db import lock_for


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
        self._lock = lock_for(connection)

    def add(
        self,
        camera_id: int,
        path: Path,
        started_at: datetime,
        duration_seconds: int | None,
        has_audio: bool,
    ) -> StoredSegment:
        with self._lock:
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

    def delete_older_than(self, camera_id: int, cutoff: datetime) -> list[Path]:
        """Delete every segment row for ``camera_id`` whose ``started_at`` is
        before ``cutoff``. Returns the file paths the rows referenced so the
        caller can unlink them on disk."""
        cutoff_iso = cutoff.isoformat(timespec="seconds")
        with self._lock:
            rows = self._connection.execute(
                "SELECT path FROM recording_segments "
                "WHERE camera_id = ? AND started_at < ? ORDER BY started_at",
                (camera_id, cutoff_iso),
            ).fetchall()
            self._connection.execute(
                "DELETE FROM recording_segments WHERE camera_id = ? AND started_at < ?",
                (camera_id, cutoff_iso),
            )
            self._connection.commit()
        return [Path(row["path"]) for row in rows]

    def list_by_camera(self, camera_id: int) -> list[StoredSegment]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT id, camera_id, path, started_at, duration_seconds, has_audio
                FROM recording_segments
                WHERE camera_id = ?
                ORDER BY started_at
                """,
                (camera_id,),
            ).fetchall()
        return [self._row_to_segment(row) for row in rows]

    def get_by_id(self, segment_id: int) -> StoredSegment | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT id, camera_id, path, started_at, duration_seconds, has_audio
                FROM recording_segments
                WHERE id = ?
                """,
                (segment_id,),
            ).fetchone()
        return None if row is None else self._row_to_segment(row)

    def list_all(self) -> list[StoredSegment]:
        """All segments across cameras, oldest first. Used by the storage-cap
        enforcer that drops the oldest segments first."""
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT id, camera_id, path, started_at, duration_seconds, has_audio
                FROM recording_segments
                ORDER BY started_at
                """
            ).fetchall()
        return [self._row_to_segment(row) for row in rows]

    def delete_by_id(self, segment_id: int) -> Path | None:
        """Delete a single segment row. Returns the file path it referenced
        (so the caller can unlink it), or ``None`` if no row matched."""
        with self._lock:
            row = self._connection.execute(
                "SELECT path FROM recording_segments WHERE id = ?", (segment_id,)
            ).fetchone()
            if row is None:
                return None
            self._connection.execute(
                "DELETE FROM recording_segments WHERE id = ?", (segment_id,)
            )
            self._connection.commit()
        return Path(row["path"])

    @staticmethod
    def _row_to_segment(row: sqlite3.Row) -> StoredSegment:
        return StoredSegment(
            id=row["id"],
            camera_id=row["camera_id"],
            path=Path(row["path"]),
            started_at=datetime.fromisoformat(row["started_at"]),
            duration_seconds=row["duration_seconds"],
            has_audio=bool(row["has_audio"]),
        )
