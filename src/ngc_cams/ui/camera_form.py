from __future__ import annotations

from typing import Any

from ngc_cams.models import Camera, RecordMode, StoredCamera


class CameraFormError(ValueError):
    """Raised when form input cannot be turned into a Camera."""


def build_camera_from_fields(fields: dict[str, Any]) -> Camera:
    name = str(fields.get("name", "")).strip()
    if not name:
        raise CameraFormError("Camera name is required.")

    rtsp_url = str(fields.get("rtsp_url", "")).strip()
    if not rtsp_url:
        raise CameraFormError("RTSP URL is required.")

    try:
        retention_days = int(fields.get("retention_days", 7))
    except (TypeError, ValueError) as exc:
        raise CameraFormError("Retention days must be an integer.") from exc
    if retention_days < 0:
        raise CameraFormError("retention days must be zero or greater.")

    raw_mode = fields.get("record_mode", RecordMode.OFF)
    try:
        record_mode = RecordMode(raw_mode)
    except ValueError as exc:
        raise CameraFormError(f"Unknown record mode: {raw_mode!r}") from exc

    return Camera(
        name=name,
        rtsp_url=rtsp_url,
        username=_optional_str(fields.get("username")),
        password=_optional_str(fields.get("password")),
        sub_stream_url=_optional_str(fields.get("sub_stream_url")),
        ptz_enabled=bool(fields.get("ptz_enabled", False)),
        record_mode=record_mode,
        retention_days=retention_days,
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def camera_id_for_row(rows: list[StoredCamera], index: int) -> int | None:
    if index < 0 or index >= len(rows):
        return None
    return rows[index].id
