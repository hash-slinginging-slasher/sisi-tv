from __future__ import annotations

import pytest

from ngc_cams.models import Camera, RecordMode, StoredCamera
from ngc_cams.ui.camera_form import CameraFormError, build_camera_from_fields, camera_id_for_row


def _valid_fields(**overrides):
    base = {
        "name": "Front gate",
        "rtsp_url": "rtsp://192.168.1.18/live/ch00_0",
        "sub_stream_url": "",
        "username": "",
        "password": "",
        "ptz_enabled": False,
        "record_mode": RecordMode.OFF,
        "retention_days": 7,
    }
    base.update(overrides)
    return base


def test_build_camera_from_fields_returns_camera_with_minimum_fields():
    camera = build_camera_from_fields(_valid_fields())
    assert isinstance(camera, Camera)
    assert camera.name == "Front gate"
    assert camera.rtsp_url == "rtsp://192.168.1.18/live/ch00_0"
    assert camera.username is None
    assert camera.password is None
    assert camera.sub_stream_url is None
    assert camera.record_mode == RecordMode.OFF
    assert camera.retention_days == 7


def test_build_camera_from_fields_strips_whitespace():
    camera = build_camera_from_fields(
        _valid_fields(name="  Front gate  ", rtsp_url="  rtsp://x  ")
    )
    assert camera.name == "Front gate"
    assert camera.rtsp_url == "rtsp://x"


def test_build_camera_from_fields_keeps_credentials_when_provided():
    camera = build_camera_from_fields(_valid_fields(username="admin", password="hunter2"))
    assert camera.username == "admin"
    assert camera.password == "hunter2"


def test_build_camera_from_fields_rejects_empty_name():
    with pytest.raises(CameraFormError, match="name"):
        build_camera_from_fields(_valid_fields(name="   "))


def test_build_camera_from_fields_rejects_empty_rtsp_url():
    with pytest.raises(CameraFormError, match="RTSP"):
        build_camera_from_fields(_valid_fields(rtsp_url=""))


def test_build_camera_from_fields_rejects_negative_retention():
    with pytest.raises(CameraFormError, match="retention"):
        build_camera_from_fields(_valid_fields(retention_days=-1))


def _stored(camera_id: int, name: str = "Cam") -> StoredCamera:
    return StoredCamera(id=camera_id, name=name, rtsp_url="rtsp://x")


def test_camera_id_for_row_returns_id_for_valid_index():
    rows = [_stored(11), _stored(22), _stored(33)]
    assert camera_id_for_row(rows, 1) == 22


def test_camera_id_for_row_returns_none_for_no_selection():
    rows = [_stored(11)]
    assert camera_id_for_row(rows, -1) is None


def test_camera_id_for_row_returns_none_for_out_of_range():
    rows = [_stored(11)]
    assert camera_id_for_row(rows, 5) is None


def test_build_camera_from_fields_rejects_unknown_record_mode():
    with pytest.raises(CameraFormError, match="record mode"):
        build_camera_from_fields(_valid_fields(record_mode="continuous"))


def test_build_camera_from_fields_rejects_non_integer_retention():
    with pytest.raises(CameraFormError, match="integer"):
        build_camera_from_fields(_valid_fields(retention_days="abc"))
