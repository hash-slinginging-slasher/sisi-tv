from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ngc_cams.models import Camera
from ngc_cams.recording.paths import (
    safe_camera_dir_name,
    segment_output_pattern,
    snapshot_output_path,
)


def test_safe_camera_dir_name_removes_windows_unsafe_characters():
    assert safe_camera_dir_name(' Front:Gate / Cam*1? ') == "Front_Gate _ Cam_1"


def test_safe_camera_dir_name_falls_back_for_empty_names():
    assert safe_camera_dir_name("  <>  ") == "camera"


def test_segment_output_pattern_groups_by_camera_and_day():
    pattern = segment_output_pattern(
        Path(r"D:\ngc-cams-recordings"),
        Camera(name="Front gate", rtsp_url="rtsp://camera/main"),
        datetime(2026, 5, 16, 13, 30),
    )

    assert pattern == Path(
        r"D:\ngc-cams-recordings\Front gate\2026-05-16\%Y-%m-%d_%H-%M-%S.mp4"
    )


def test_snapshot_output_path_uses_safe_dir_and_jpg_extension():
    path = snapshot_output_path(
        Path(r"D:\ngc-cams-snapshots"),
        Camera(name="Front gate", rtsp_url="rtsp://camera/main"),
        datetime(2026, 5, 17, 10, 30, 45),
    )

    assert path == Path(r"D:\ngc-cams-snapshots\Front gate\2026-05-17_10-30-45.jpg")


def test_snapshot_output_path_sanitizes_camera_name():
    path = snapshot_output_path(
        Path(r"D:\ngc-cams-snapshots"),
        Camera(name='Front:Gate / Cam*1?', rtsp_url="rtsp://camera/main"),
        datetime(2026, 5, 17, 10, 30, 45),
    )

    assert path == Path(r"D:\ngc-cams-snapshots\Front_Gate _ Cam_1\2026-05-17_10-30-45.jpg")
