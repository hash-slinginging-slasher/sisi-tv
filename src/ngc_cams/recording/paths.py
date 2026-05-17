from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from ngc_cams.models import Camera


_UNSAFE_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
_WHITESPACE = re.compile(r"\s+")


def safe_camera_dir_name(name: str) -> str:
    value = _UNSAFE_PATH_CHARS.sub("_", name.strip())
    value = _WHITESPACE.sub(" ", value).strip(" ._")
    return value or "camera"


def segment_output_pattern(root: Path, camera: Camera, when: datetime) -> Path:
    day = when.strftime("%Y-%m-%d")
    return root / safe_camera_dir_name(camera.name) / day / "%Y-%m-%d_%H-%M-%S.mp4"


def snapshot_output_path(root: Path, camera: Camera, when: datetime) -> Path:
    filename = when.strftime("%Y-%m-%d_%H-%M-%S.jpg")
    return root / safe_camera_dir_name(camera.name) / filename
