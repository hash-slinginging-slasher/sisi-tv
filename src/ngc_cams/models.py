from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RecordMode(StrEnum):
    OFF = "off"
    VIDEO_ONLY = "video_only"
    VIDEO_AUDIO = "video_audio"


@dataclass(frozen=True)
class Camera:
    name: str
    rtsp_url: str
    username: str | None = None
    password: str | None = None
    sub_stream_url: str | None = None
    ptz_enabled: bool = False
    record_mode: RecordMode = RecordMode.OFF
    retention_days: int = 7
    display_rotation: int = 0  # 0, 90, 180, or 270 -- applied via CSS only


@dataclass(frozen=True)
class StoredCamera(Camera):
    id: int = 0
