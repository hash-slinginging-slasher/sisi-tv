from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from ngc_cams.cameras import CameraRepository
from ngc_cams.config import AppConfig
from ngc_cams.db import initialize
from ngc_cams.models import Camera
from ngc_cams.recording.paths import safe_camera_dir_name
from ngc_cams_web.composition import build_app


class _FakeSnapshotProcess:
    """Stand-in for ffmpeg's snapshot one-shot. Writes the JPEG output the
    route expects on disk so the round-trip is realistic."""

    def __init__(self, command, *, write_payload: bytes = b"\xff\xd8fakejpeg\xff\xd9",
                 returncode: int = 0):
        self.command = command
        self.write_payload = write_payload
        self.returncode = returncode
        self.killed = False
        # The output path is the last positional arg in build_snapshot_command.
        self.output_path = Path(command[-1])

    def wait(self, timeout=None) -> int:  # noqa: ARG002 — match Popen API
        if self.returncode == 0:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            self.output_path.write_bytes(self.write_payload)
        return self.returncode

    def kill(self) -> None:
        self.killed = True


def _build(tmp_path: Path, *, popen_factory=None, ffmpeg_resolver=None):
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    initialize(connection)
    repo = CameraRepository(connection)
    stored = repo.add(Camera(name="Front Door", rtsp_url="rtsp://x/main"))
    config = AppConfig(snapshot_root=tmp_path / "snaps")
    app = build_app(
        cameras=repo,
        discovery=None,
        recording_manager=None,
        config=config,
    )
    if popen_factory is not None:
        app.state.snapshot_popen_factory = popen_factory
    app.state.snapshot_ffmpeg_resolver = (
        ffmpeg_resolver if ffmpeg_resolver is not None else lambda: "/usr/bin/ffmpeg"
    )
    return app, repo, stored, config


def test_post_snapshot_spawns_ffmpeg_with_correct_args_and_writes_file(tmp_path):
    captured: list[_FakeSnapshotProcess] = []

    def factory(command, **_kwargs):
        proc = _FakeSnapshotProcess(command)
        captured.append(proc)
        return proc

    app, _, stored, config = _build(tmp_path, popen_factory=factory)

    with TestClient(app) as client:
        response = client.post(
            f"/cameras/{stored.id}/snapshot", follow_redirects=False
        )

    assert response.status_code == 303
    assert response.headers["location"] == f"/cameras/{stored.id}"
    assert len(captured) == 1
    cmd = captured[0].command
    assert cmd[0] == "/usr/bin/ffmpeg"
    assert "-rtsp_transport" in cmd and cmd[cmd.index("-rtsp_transport") + 1] == "tcp"
    assert cmd[cmd.index("-i") + 1] == stored.rtsp_url
    assert "-frames:v" in cmd and cmd[cmd.index("-frames:v") + 1] == "1"
    # JPEG actually landed on disk in the snapshot dir.
    cam_dir = config.snapshot_root / safe_camera_dir_name(stored.name)
    files = list(cam_dir.glob("*.jpg"))
    assert len(files) == 1
    assert files[0].read_bytes().startswith(b"\xff\xd8")


def test_post_snapshot_returns_502_when_ffmpeg_fails(tmp_path):
    def factory(command, **_kwargs):
        return _FakeSnapshotProcess(command, returncode=1)

    app, _, stored, _ = _build(tmp_path, popen_factory=factory)
    with TestClient(app) as client:
        response = client.post(f"/cameras/{stored.id}/snapshot")
    assert response.status_code == 502
    assert "ffmpeg exited 1" in response.text


def test_post_snapshot_returns_504_on_timeout(tmp_path):
    class _HangingProcess:
        def __init__(self, command):
            self.command = command
            self.killed = False
        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired(self.command, timeout)
        def kill(self):
            self.killed = True

    def factory(command, **_kwargs):
        return _HangingProcess(command)

    app, _, stored, _ = _build(tmp_path, popen_factory=factory)
    with TestClient(app) as client:
        response = client.post(f"/cameras/{stored.id}/snapshot")
    assert response.status_code == 504


def test_post_snapshot_returns_404_for_unknown_camera(tmp_path):
    app, _, _, _ = _build(tmp_path)
    with TestClient(app) as client:
        response = client.post("/cameras/9999/snapshot")
    assert response.status_code == 404


def test_post_snapshot_returns_503_when_ffmpeg_missing(tmp_path):
    app, _, stored, _ = _build(tmp_path, ffmpeg_resolver=lambda: None)
    with TestClient(app) as client:
        response = client.post(f"/cameras/{stored.id}/snapshot")
    assert response.status_code == 503


def test_get_snapshot_serves_jpeg_from_camera_dir(tmp_path):
    app, _, stored, config = _build(tmp_path)
    cam_dir = config.snapshot_root / safe_camera_dir_name(stored.name)
    cam_dir.mkdir(parents=True)
    target = cam_dir / "2026-05-17_12-34-56.jpg"
    target.write_bytes(b"\xff\xd8payload\xff\xd9")

    with TestClient(app) as client:
        response = client.get(f"/cameras/{stored.id}/snapshots/2026-05-17_12-34-56.jpg")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content.startswith(b"\xff\xd8")


def test_get_snapshot_rejects_filenames_outside_timestamp_pattern(tmp_path):
    """The route only accepts YYYY-MM-DD_HH-MM-SS.jpg. Anything else --
    including filenames with `..`, dot-paths, etc. -- gets 400.
    (Starlette already filters URLs with raw `/` in path params; this regex
    closes the last gap.)"""
    app, _, stored, _ = _build(tmp_path)
    bad_names = [
        "..bad.jpg",
        "secrets.jpg",
        ".jpg",
        "2026-05-17.jpg",
        "2026-05-17_12-34-56.JPG",  # uppercase ext
    ]
    with TestClient(app) as client:
        for name in bad_names:
            response = client.get(f"/cameras/{stored.id}/snapshots/{name}")
            assert response.status_code == 400, f"{name!r} should 400, got {response.status_code}"


def test_get_snapshot_rejects_non_jpg_filename(tmp_path):
    app, _, stored, _ = _build(tmp_path)
    with TestClient(app) as client:
        response = client.get(
            f"/cameras/{stored.id}/snapshots/2026-05-17_12-34-56.png"
        )
    assert response.status_code == 400


def test_get_snapshot_returns_404_when_file_missing(tmp_path):
    app, _, stored, _ = _build(tmp_path)
    with TestClient(app) as client:
        response = client.get(
            f"/cameras/{stored.id}/snapshots/2026-05-17_12-34-56.jpg"
        )
    assert response.status_code == 404


def test_camera_detail_lists_recent_snapshots(tmp_path):
    app, _, stored, config = _build(tmp_path)
    cam_dir = config.snapshot_root / safe_camera_dir_name(stored.name)
    cam_dir.mkdir(parents=True)
    (cam_dir / "2026-05-17_06-00-00.jpg").write_bytes(b"a")
    (cam_dir / "2026-05-17_07-00-00.jpg").write_bytes(b"b")

    with TestClient(app) as client:
        response = client.get(f"/cameras/{stored.id}")

    assert response.status_code == 200
    assert "/cameras/{}/snapshots/2026-05-17_06-00-00.jpg".format(stored.id) in response.text
    assert "/cameras/{}/snapshots/2026-05-17_07-00-00.jpg".format(stored.id) in response.text
    assert "Recent Snapshots" in response.text


def test_camera_detail_omits_gallery_when_no_snapshots(tmp_path):
    app, _, stored, _ = _build(tmp_path)
    with TestClient(app) as client:
        response = client.get(f"/cameras/{stored.id}")
    assert response.status_code == 200
    assert "Recent Snapshots" not in response.text
