from __future__ import annotations

import sqlite3

from ngc_cams.models import Camera, RecordMode, StoredCamera


class CameraRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def add(self, camera: Camera) -> StoredCamera:
        cursor = self._connection.execute(
            """
            INSERT INTO cameras (
                name, rtsp_url, username, password, sub_stream_url,
                ptz_enabled, record_mode, retention_days
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                camera.name,
                camera.rtsp_url,
                camera.username,
                camera.password,
                camera.sub_stream_url,
                int(camera.ptz_enabled),
                camera.record_mode.value,
                camera.retention_days,
            ),
        )
        self._connection.commit()
        return StoredCamera(id=cursor.lastrowid, **camera.__dict__)

    def list(self) -> list[StoredCamera]:
        rows = self._connection.execute(
            """
            SELECT id, name, rtsp_url, username, password, sub_stream_url,
                   ptz_enabled, record_mode, retention_days
            FROM cameras
            ORDER BY name COLLATE NOCASE
            """
        )
        return [self._from_row(row) for row in rows]

    def get(self, camera_id: int) -> StoredCamera | None:
        row = self._connection.execute(
            """
            SELECT id, name, rtsp_url, username, password, sub_stream_url,
                   ptz_enabled, record_mode, retention_days
            FROM cameras
            WHERE id = ?
            """,
            (camera_id,),
        ).fetchone()
        return None if row is None else self._from_row(row)

    def update(self, camera_id: int, camera: Camera) -> StoredCamera:
        cursor = self._connection.execute(
            """
            UPDATE cameras
            SET name = ?,
                rtsp_url = ?,
                username = ?,
                password = ?,
                sub_stream_url = ?,
                ptz_enabled = ?,
                record_mode = ?,
                retention_days = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                camera.name,
                camera.rtsp_url,
                camera.username,
                camera.password,
                camera.sub_stream_url,
                int(camera.ptz_enabled),
                camera.record_mode.value,
                camera.retention_days,
                camera_id,
            ),
        )
        self._connection.commit()
        if cursor.rowcount == 0:
            raise KeyError(f"Camera {camera_id} does not exist.")
        stored = self.get(camera_id)
        if stored is None:
            raise KeyError(f"Camera {camera_id} does not exist.")
        return stored

    def delete(self, camera_id: int) -> bool:
        cursor = self._connection.execute("DELETE FROM cameras WHERE id = ?", (camera_id,))
        self._connection.commit()
        return cursor.rowcount > 0

    @staticmethod
    def _from_row(row: sqlite3.Row) -> StoredCamera:
        return StoredCamera(
            id=row["id"],
            name=row["name"],
            rtsp_url=row["rtsp_url"],
            username=row["username"],
            password=row["password"],
            sub_stream_url=row["sub_stream_url"],
            ptz_enabled=bool(row["ptz_enabled"]),
            record_mode=RecordMode(row["record_mode"]),
            retention_days=row["retention_days"],
        )
