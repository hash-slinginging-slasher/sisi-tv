"""HLS live streaming -- one ffmpeg per camera, shared by all viewers.

Replaces the per-viewer MJPEG transcoder with a single ffmpeg per camera
that writes rolling HLS (.m3u8 playlist + .ts segments) to a local temp
directory. The kiosk grid and any phones watching the same camera all
read from the same files -- CPU and RTSP bandwidth scale with cameras,
not viewers.

Output lives under ``%TEMP%\\sisi-tv-hls\\<camera>\\`` on the local SSD,
NOT the NAS recording root. HLS segments rotate every 2 seconds; SMB to
a NAS adds latency that breaks the rotation cadence.

Lifecycle:
  * First request for /cameras/{id}/live/index.m3u8 spawns ffmpeg.
  * Each request bumps ``last_requested_at``.
  * :meth:`poll` runs on the lifespan tick and shuts down ffmpeg for any
    camera not requested in ``idle_timeout_seconds``.
  * :meth:`shutdown_all` cleans up on app exit.
"""

from __future__ import annotations

import logging
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from ngc_cams.models import StoredCamera
from ngc_cams.recording.locator import find_ffmpeg_executable
from ngc_cams.recording.paths import safe_camera_dir_name

logger = logging.getLogger(__name__)

HLS_SEGMENT_DURATION = 2     # seconds per .ts segment
HLS_PLAYLIST_DEPTH = 4       # segments in the rolling playlist (8s window)
DEFAULT_IDLE_TIMEOUT_SECONDS = 30
GRACEFUL_TIMEOUT_SECONDS = 3
TERMINATE_TIMEOUT_SECONDS = 2

if sys.platform.startswith("win"):
    _CREATE_NEW_PROCESS_GROUP = subprocess.CREATE_NEW_PROCESS_GROUP
else:
    _CREATE_NEW_PROCESS_GROUP = 0


def build_hls_command(
    rtsp_url: str,
    output_dir: Path,
    ffmpeg: str = "ffmpeg",
) -> list[str]:
    """ffmpeg argv to mux RTSP into a rolling HLS playlist under ``output_dir``.

    ``-c copy`` because we don't want to transcode 6 cameras simultaneously
    on a kiosk CPU. The camera should already emit H.264 -- most ONVIF cams
    let you pick H.264 for a sub-stream even if the main stream is H.265.
    """
    playlist = output_dir / "index.m3u8"
    segment_pattern = output_dir / "seg_%05d.ts"
    return [
        ffmpeg,
        "-loglevel",
        "error",
        "-rtsp_transport",
        "tcp",
        # Match recording resilience: stalled RTSP -> ffmpeg exits,
        # idle-timeout reaps it, next request respawns.
        # ffmpeg 8 renamed -stimeout -> -timeout for RTSP; -rw_timeout is
        # HTTP-only and is rejected on an RTSP input in ffmpeg 8.
        "-timeout",
        "10000000",  # 10s socket timeout (microseconds)
        "-i",
        rtsp_url,
        "-c",
        "copy",
        "-an",
        "-f",
        "hls",
        "-hls_time",
        str(HLS_SEGMENT_DURATION),
        "-hls_list_size",
        str(HLS_PLAYLIST_DEPTH),
        # delete_segments: ffmpeg unlinks .ts files older than the rolling
        # window so the temp dir stays small. omit_endlist: never signal
        # EOF in the playlist -- it's a live feed.
        # Note: `independent_segments` was tempting but it makes ffmpeg WAIT
        # for a keyframe at every segment boundary. Most ONVIF cameras send
        # keyframes every 5-10s, so a 2s segment with this flag stalls
        # forever (alive ffmpeg, zero playlist files written, route returns
        # 503 in a loop). Skip the flag; hls.js plays fine without it.
        "-hls_flags",
        "delete_segments+omit_endlist",
        "-hls_segment_type",
        "mpegts",
        "-hls_segment_filename",
        str(segment_pattern),
        str(playlist),
    ]


@dataclass
class _Stream:
    camera_id: int
    rtsp_url: str
    output_dir: Path
    process: Any = None  # subprocess.Popen-like
    last_requested_at: datetime = field(default_factory=datetime.now)

    @property
    def playlist_path(self) -> Path:
        return self.output_dir / "index.m3u8"

    @property
    def is_alive(self) -> bool:
        return self.process is not None and self.process.poll() is None


class LiveStreamManager:
    """Per-camera HLS ffmpeg pool with idle-timeout shutdown."""

    def __init__(
        self,
        hls_root: Path,
        ffmpeg_resolver: Callable[[], str | None] = find_ffmpeg_executable,
        popen_factory: Callable[..., Any] = subprocess.Popen,
        clock: Callable[[], datetime] = datetime.now,
        idle_timeout_seconds: int = DEFAULT_IDLE_TIMEOUT_SECONDS,
    ) -> None:
        self._hls_root = hls_root
        self._ffmpeg_resolver = ffmpeg_resolver
        self._popen_factory = popen_factory
        self._clock = clock
        self._idle_timeout_seconds = idle_timeout_seconds
        self._streams: dict[int, _Stream] = {}

    # --- Public API --------------------------------------------------

    def request_playlist(self, camera: StoredCamera) -> Path | None:
        """Return path to ``index.m3u8`` for ``camera`` after touching the idle
        timer and (re)spawning ffmpeg if needed. Returns None if ffmpeg isn't
        installed or the playlist hasn't appeared yet (caller should return
        503 so the browser retries)."""
        stream = self._streams.get(camera.id)
        now = self._clock()
        if stream is None or not stream.is_alive:
            stream = self._spawn(camera)
            if stream is None:
                return None
        stream.last_requested_at = now
        if not stream.playlist_path.exists():
            return None
        return stream.playlist_path

    def segment_path(self, camera_id: int, segment_name: str) -> Path | None:
        """Resolve a segment filename ('seg_00042.ts') to its on-disk path.
        Returns None if the camera has no active stream or the filename
        escapes the camera's HLS dir (path-traversal defense)."""
        stream = self._streams.get(camera_id)
        if stream is None:
            return None
        # Defense in depth: only allow filenames the segment muxer would have
        # written. Block anything with directory separators or that's not a .ts.
        if "/" in segment_name or "\\" in segment_name or ".." in segment_name:
            return None
        if not segment_name.endswith(".ts"):
            return None
        candidate = stream.output_dir / segment_name
        try:
            resolved = candidate.resolve()
        except OSError:
            return None
        if stream.output_dir.resolve() not in resolved.parents:
            return None
        if not candidate.exists():
            return None
        # Bump idle timer too -- if segments are being fetched, the stream
        # is still in use.
        stream.last_requested_at = self._clock()
        return candidate

    def poll(self) -> None:
        """Shut down streams idle for more than ``idle_timeout_seconds``.
        Called from the FastAPI lifespan poll loop next to RecordingManager.poll."""
        now = self._clock()
        for cam_id, stream in list(self._streams.items()):
            if not stream.is_alive:
                logger.info("hls stream for camera %s exited; reaping", cam_id)
                self._reap(cam_id)
                continue
            idle = (now - stream.last_requested_at).total_seconds()
            if idle >= self._idle_timeout_seconds:
                logger.info(
                    "hls stream for camera %s idle %.0fs; shutting down",
                    cam_id, idle,
                )
                self._stop(cam_id)

    def shutdown_all(self) -> None:
        """Stop every running stream. Called on app shutdown."""
        for cam_id in list(self._streams.keys()):
            self._stop(cam_id)

    def is_streaming(self, camera_id: int) -> bool:
        stream = self._streams.get(camera_id)
        return stream is not None and stream.is_alive

    # --- Internals ---------------------------------------------------

    def _spawn(self, camera: StoredCamera) -> _Stream | None:
        ffmpeg_path = self._ffmpeg_resolver()
        if ffmpeg_path is None:
            logger.error("hls: ffmpeg not found on PATH; cannot start stream for camera %s",
                         camera.id)
            return None
        output_dir = self._hls_root / safe_camera_dir_name(camera.name)
        # Clean any leftover .ts/.m3u8 from a previous run so the playlist
        # doesn't accidentally reference deleted segments.
        if output_dir.exists():
            try:
                shutil.rmtree(output_dir)
            except OSError:
                pass
        output_dir.mkdir(parents=True, exist_ok=True)
        command = build_hls_command(camera.rtsp_url, output_dir, ffmpeg=ffmpeg_path)
        try:
            process = self._popen_factory(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_CREATE_NEW_PROCESS_GROUP,
            )
        except (FileNotFoundError, OSError) as exc:
            logger.error("hls: failed to spawn ffmpeg for camera %s: %s", camera.id, exc)
            return None
        stream = _Stream(
            camera_id=camera.id,
            rtsp_url=camera.rtsp_url,
            output_dir=output_dir,
            process=process,
            last_requested_at=self._clock(),
        )
        self._streams[camera.id] = stream
        logger.info("hls: started stream for camera %s -> %s", camera.id, output_dir)
        return stream

    def _stop(self, camera_id: int) -> None:
        stream = self._streams.pop(camera_id, None)
        if stream is None:
            return
        process = stream.process
        if process is None or process.poll() is not None:
            self._cleanup_dir(stream.output_dir)
            return
        graceful_signal = (
            signal.CTRL_BREAK_EVENT
            if sys.platform.startswith("win") and hasattr(signal, "CTRL_BREAK_EVENT")
            else signal.SIGINT
        )
        try:
            process.send_signal(graceful_signal)
        except (OSError, ValueError):
            pass
        try:
            process.wait(timeout=GRACEFUL_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except OSError:
                pass
            try:
                process.wait(timeout=TERMINATE_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                pass
        self._cleanup_dir(stream.output_dir)

    def _reap(self, camera_id: int) -> None:
        stream = self._streams.pop(camera_id, None)
        if stream is not None:
            self._cleanup_dir(stream.output_dir)

    def _cleanup_dir(self, output_dir: Path) -> None:
        try:
            shutil.rmtree(output_dir)
        except OSError:
            pass
