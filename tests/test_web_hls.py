"""Tests for ngc_cams_web.hls.LiveStreamManager and the /cameras/{id}/live/*
HLS route handlers. ffmpeg is faked via popen_factory so the tests don't shell
out to a real process; the fake also drops a synthetic index.m3u8 / segment
file on disk so FileResponse has something to serve.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from ngc_cams.cameras import CameraRepository
from ngc_cams.db import initialize
from ngc_cams.models import Camera
from ngc_cams_web.composition import build_app
from ngc_cams_web.hls import LiveStreamManager, build_hls_command


class _FakeHlsProcess:
    """Stands in for ffmpeg. Stays alive until .poll() returns the preset
    returncode (None means still running). Writes the playlist + first segment
    on construction so FileResponse can serve something."""

    def __init__(
        self,
        command,
        write_playlist: bool = True,
        returncode_on_poll: int | None = None,
    ):
        self.command = command
        self._returncode = returncode_on_poll
        self.terminated = False
        self.killed = False
        if write_playlist:
            # Last positional arg of build_hls_command is the playlist path.
            playlist = Path(command[-1])
            playlist.parent.mkdir(parents=True, exist_ok=True)
            playlist.write_text(
                "#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:2\n",
                encoding="utf-8",
            )
            # Drop one .ts so segment_path() tests have a real file.
            (playlist.parent / "seg_00000.ts").write_bytes(b"\x47" * 188)

    def poll(self):
        return self._returncode

    def send_signal(self, _sig):
        self._returncode = 0

    def terminate(self):
        self.terminated = True
        self._returncode = 0

    def kill(self):
        self.killed = True
        self._returncode = -9

    def wait(self, timeout=None):
        return self._returncode if self._returncode is not None else 0

    def simulate_exit(self, code: int = 0):
        self._returncode = code


def _make_manager(tmp_path, **overrides):
    spawned: list[_FakeHlsProcess] = []

    def factory(command, **_kwargs):
        proc = _FakeHlsProcess(command, **overrides)
        spawned.append(proc)
        return proc

    manager = LiveStreamManager(
        hls_root=tmp_path / "hls",
        ffmpeg_resolver=lambda: "/usr/bin/ffmpeg",
        popen_factory=factory,
    )
    return manager, spawned


def _stored_camera(name: str = "Front", camera_id: int = 1) -> Camera:
    """A Camera lookalike with an id attribute. The manager only reads .id,
    .name, .rtsp_url so a frozen dataclass with attributes works fine."""
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class _Cam:
        id: int
        name: str
        rtsp_url: str
    return _Cam(id=camera_id, name=name, rtsp_url="rtsp://x/main")


# --- build_hls_command ---------------------------------------------------


def test_build_hls_command_uses_rtsp_tcp_and_modern_timeout_flag():
    cmd = build_hls_command("rtsp://1.2.3.4/main", Path("C:/tmp/hls"), ffmpeg="ffmpeg")
    assert cmd[0] == "ffmpeg"
    assert "-rtsp_transport" in cmd
    assert cmd[cmd.index("-rtsp_transport") + 1] == "tcp"
    # ffmpeg 8 renamed -stimeout -> -timeout for RTSP, and -rw_timeout is
    # HTTP-only. Either of the old flags would crash ffmpeg 8 immediately.
    assert "-timeout" in cmd
    assert "-stimeout" not in cmd
    assert "-rw_timeout" not in cmd
    # Timeout must come before the input URL.
    assert cmd.index("-timeout") < cmd.index("-i")


def test_build_hls_command_emits_rolling_hls_flags():
    cmd = build_hls_command("rtsp://x/main", Path("C:/tmp/hls"))
    # Live feed -> rolling window with auto-cleanup, no end marker, mpegts.
    assert "-f" in cmd and cmd[cmd.index("-f") + 1] == "hls"
    flags = cmd[cmd.index("-hls_flags") + 1]
    assert "delete_segments" in flags
    assert "omit_endlist" in flags
    # `independent_segments` must NOT be present -- it forces ffmpeg to wait
    # for a keyframe at each segment boundary, which stalls indefinitely on
    # cameras with long GOPs (most ONVIF firmwares).
    assert "independent_segments" not in flags
    # Output: ends with the playlist path.
    assert cmd[-1].endswith("index.m3u8")


# --- LiveStreamManager.request_playlist ----------------------------------


def test_request_playlist_spawns_ffmpeg_once_and_returns_path(tmp_path):
    manager, spawned = _make_manager(tmp_path)
    cam = _stored_camera("Front")

    path = manager.request_playlist(cam)

    assert path is not None
    assert path.name == "index.m3u8"
    assert path.is_file()
    assert len(spawned) == 1
    # Second call reuses the same ffmpeg -- no respawn.
    manager.request_playlist(cam)
    assert len(spawned) == 1


def test_request_playlist_returns_none_when_ffmpeg_missing(tmp_path):
    manager = LiveStreamManager(
        hls_root=tmp_path / "hls",
        ffmpeg_resolver=lambda: None,  # ffmpeg not installed
    )
    assert manager.request_playlist(_stored_camera()) is None


def test_request_playlist_returns_none_until_playlist_exists(tmp_path):
    """If ffmpeg spawns but hasn't written the playlist yet, the route should
    get None so it can return 503 and hls.js retries."""
    manager, _ = _make_manager(tmp_path, write_playlist=False)
    assert manager.request_playlist(_stored_camera()) is None


def test_request_playlist_respawns_when_process_died(tmp_path):
    manager, spawned = _make_manager(tmp_path)
    cam = _stored_camera()
    manager.request_playlist(cam)
    assert len(spawned) == 1
    # Simulate ffmpeg crash; next request should respawn.
    spawned[0].simulate_exit(1)
    manager.request_playlist(cam)
    assert len(spawned) == 2


# --- LiveStreamManager.segment_path --------------------------------------


def test_segment_path_returns_existing_ts_file(tmp_path):
    manager, _ = _make_manager(tmp_path)
    cam = _stored_camera()
    manager.request_playlist(cam)
    path = manager.segment_path(cam.id, "seg_00000.ts")
    assert path is not None
    assert path.is_file()
    assert path.suffix == ".ts"


def test_segment_path_rejects_unknown_camera(tmp_path):
    manager, _ = _make_manager(tmp_path)
    # No stream started for cam 99
    assert manager.segment_path(99, "seg_00000.ts") is None


def test_segment_path_rejects_path_traversal(tmp_path):
    manager, _ = _make_manager(tmp_path)
    cam = _stored_camera()
    manager.request_playlist(cam)
    # Any of these should bounce to None instead of escaping the HLS dir.
    for bad in ("../seg.ts", "..\\seg.ts", "sub/seg.ts", "sub\\seg.ts", "seg.m3u8"):
        assert manager.segment_path(cam.id, bad) is None, f"{bad!r} should be rejected"


def test_segment_path_rejects_missing_file(tmp_path):
    manager, _ = _make_manager(tmp_path)
    cam = _stored_camera()
    manager.request_playlist(cam)
    assert manager.segment_path(cam.id, "seg_99999.ts") is None


# --- Idle timeout / poll -------------------------------------------------


def test_poll_shuts_down_idle_stream(tmp_path):
    now = datetime(2026, 5, 17, 18, 0, 0)
    manager, spawned = _make_manager(tmp_path)
    # Make the clock controllable so the idle timeout fires deterministically.
    manager._clock = lambda: now
    manager._idle_timeout_seconds = 30
    cam = _stored_camera()
    manager.request_playlist(cam)
    assert manager.is_streaming(cam.id)

    # Advance the clock past the idle window and tick poll.
    manager._clock = lambda: now + timedelta(seconds=31)
    manager.poll()

    assert not manager.is_streaming(cam.id)
    assert spawned[0].terminated or spawned[0].killed or spawned[0]._returncode == 0


def test_poll_reaps_dead_process_and_drops_stream(tmp_path):
    manager, spawned = _make_manager(tmp_path)
    cam = _stored_camera()
    manager.request_playlist(cam)
    spawned[0].simulate_exit(1)
    manager.poll()
    assert not manager.is_streaming(cam.id)


def test_shutdown_all_stops_every_stream(tmp_path):
    manager, _ = _make_manager(tmp_path)
    manager.request_playlist(_stored_camera("A", 1))
    manager.request_playlist(_stored_camera("B", 2))
    assert manager.is_streaming(1) and manager.is_streaming(2)
    manager.shutdown_all()
    assert not manager.is_streaming(1)
    assert not manager.is_streaming(2)


# --- /cameras/{id}/live/* route handlers ---------------------------------


def _build_app_with_manager(tmp_path, write_playlist=True):
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    initialize(conn)
    repo = CameraRepository(conn)
    stored = repo.add(Camera(name="Front", rtsp_url="rtsp://x/main"))
    manager, _ = _make_manager(tmp_path, write_playlist=write_playlist)
    app = build_app(
        cameras=repo,
        discovery=None,
        recording_manager=None,
        live_stream_manager=manager,
    )
    return app, stored, manager


def test_live_playlist_route_returns_m3u8(tmp_path):
    app, stored, _ = _build_app_with_manager(tmp_path)
    with TestClient(app) as client:
        response = client.get(f"/cameras/{stored.id}/live/index.m3u8")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/vnd.apple.mpegurl")
    assert response.text.startswith("#EXTM3U")
    assert "no-cache" in response.headers["cache-control"]


def test_live_playlist_route_returns_503_when_playlist_pending(tmp_path):
    """ffmpeg spawning but hasn't written index.m3u8 yet -- the playlist
    route surfaces 503 so hls.js retries instead of giving up."""
    app, stored, _ = _build_app_with_manager(tmp_path, write_playlist=False)
    with TestClient(app) as client:
        response = client.get(f"/cameras/{stored.id}/live/index.m3u8")
    assert response.status_code == 503


def test_live_playlist_route_404_unknown_camera(tmp_path):
    app, _, _ = _build_app_with_manager(tmp_path)
    with TestClient(app) as client:
        response = client.get("/cameras/9999/live/index.m3u8")
    assert response.status_code == 404


def test_live_segment_route_serves_ts(tmp_path):
    app, stored, _ = _build_app_with_manager(tmp_path)
    with TestClient(app) as client:
        # First touch the playlist so a stream exists for this camera.
        client.get(f"/cameras/{stored.id}/live/index.m3u8")
        response = client.get(f"/cameras/{stored.id}/live/seg_00000.ts")
    assert response.status_code == 200
    assert response.headers["content-type"] == "video/mp2t"
    assert response.content.startswith(b"\x47")  # MPEG-TS sync byte


def test_live_segment_route_404_for_unknown_segment(tmp_path):
    app, stored, _ = _build_app_with_manager(tmp_path)
    with TestClient(app) as client:
        client.get(f"/cameras/{stored.id}/live/index.m3u8")
        response = client.get(f"/cameras/{stored.id}/live/seg_99999.ts")
    assert response.status_code == 404


def test_live_segment_route_404_when_no_active_stream(tmp_path):
    """Segment URL requested before/after the playlist URL -> the camera has
    no LiveStreamManager entry yet, so 404 (not 5xx)."""
    app, stored, _ = _build_app_with_manager(tmp_path)
    with TestClient(app) as client:
        response = client.get(f"/cameras/{stored.id}/live/seg_00000.ts")
    assert response.status_code == 404


def test_live_routes_return_404_when_manager_not_wired(tmp_path):
    """Some test compositions (and the legacy MJPEG flow) build the app with
    live_stream_manager=None. The HLS routes should 404 cleanly, not 500."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    initialize(conn)
    repo = CameraRepository(conn)
    stored = repo.add(Camera(name="Front", rtsp_url="rtsp://x/main"))
    app = build_app(
        cameras=repo,
        discovery=None,
        recording_manager=None,
        live_stream_manager=None,
    )
    with TestClient(app) as client:
        r1 = client.get(f"/cameras/{stored.id}/live/index.m3u8")
        r2 = client.get(f"/cameras/{stored.id}/live/seg_00000.ts")
    assert r1.status_code == 404
    assert r2.status_code == 404
