from __future__ import annotations

import logging
import signal
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from ngc_cams.cameras import CameraRepository
from ngc_cams.models import RecordMode, StoredCamera
from ngc_cams.recording.ffmpeg import build_segment_command
from ngc_cams.recording.locator import find_ffmpeg_executable
from ngc_cams.recording.paths import segment_output_pattern
from ngc_cams.segments import SegmentRepository

logger = logging.getLogger(__name__)


SEGMENT_LIST_FILENAME = "segments.csv"
RESTART_BACKOFF_SECONDS = 5
GRACEFUL_TIMEOUT_SECONDS = 3
TERMINATE_TIMEOUT_SECONDS = 2

# On Windows we have to start ffmpeg in its own process group so a CTRL_BREAK_EVENT
# only signals ffmpeg, not our whole Python app.
if sys.platform.startswith("win"):
    _CREATE_NEW_PROCESS_GROUP = subprocess.CREATE_NEW_PROCESS_GROUP
else:
    _CREATE_NEW_PROCESS_GROUP = 0


@dataclass
class _Recording:
    camera: StoredCamera
    process: object
    segment_list_path: Path
    segment_list_offset: int = 0
    next_restart_after: datetime | None = None

    @property
    def has_audio(self) -> bool:
        return self.camera.record_mode == RecordMode.VIDEO_AUDIO


@dataclass
class _Stopping:
    recording: _Recording
    deadline: datetime
    killed: bool = False


class RecordingManager:
    """Owns ffmpeg subprocesses for cameras with ``record_mode != off``.

    Pure Python: Qt code in MainWindow calls :meth:`poll` from a QTimer and
    :meth:`stop_all` on shutdown. ``popen_factory`` is injected so tests can
    swap in a fake without touching real ffmpeg.
    """

    def __init__(
        self,
        cameras: CameraRepository,
        segments: SegmentRepository,
        recording_root: Path,
        segment_seconds: int = 600,
        popen_factory: Callable[..., object] = subprocess.Popen,
        clock: Callable[[], datetime] = datetime.now,
        ffmpeg_resolver: Callable[[], str | None] = find_ffmpeg_executable,
    ) -> None:
        self._cameras = cameras
        self._segments = segments
        self._recording_root = recording_root
        self._segment_seconds = segment_seconds
        self._popen_factory = popen_factory
        self._clock = clock
        self._ffmpeg_resolver = ffmpeg_resolver
        self._recordings: dict[int, _Recording] = {}
        # Cameras that failed to spawn this session; we don't retry them on every
        # poll/apply_modes — restarting the app gives the user a chance to fix it.
        self._failed_camera_ids: set[int] = set()
        # Recordings whose graceful shutdown is in flight. poll() reaps these
        # so the UI thread never blocks waiting on ffmpeg.
        self._stopping: list[_Stopping] = []
        self.ffmpeg_missing: bool = False

    def ffmpeg_available(self) -> bool:
        """True iff an ``ffmpeg`` executable can be resolved on PATH."""
        return self._ffmpeg_resolver() is not None

    def is_recording(self, camera_id: int) -> bool:
        return camera_id in self._recordings

    def start(self, camera: StoredCamera) -> None:
        if camera.id in self._recordings:
            return
        if camera.id in self._failed_camera_ids:
            return
        if camera.record_mode == RecordMode.OFF:
            raise ValueError("Cannot start recording for a camera in OFF mode.")
        ffmpeg_path = self._ffmpeg_resolver()
        if ffmpeg_path is None:
            self.ffmpeg_missing = True
            self._failed_camera_ids.add(camera.id)
            logger.error(
                "ffmpeg not found when starting recording for camera %s (%s). "
                "Install ffmpeg and put it on PATH, then restart the app.",
                camera.id, camera.name,
            )
            return
        now = self._clock()
        output_pattern = segment_output_pattern(self._recording_root, camera, now)
        output_pattern.parent.mkdir(parents=True, exist_ok=True)
        segment_list_path = output_pattern.parent / SEGMENT_LIST_FILENAME
        # Truncate so old lines from a previous run can't double-insert.
        segment_list_path.write_text("", encoding="utf-8")
        command = build_segment_command(
            camera.rtsp_url,
            output_pattern,
            camera.record_mode,
            segment_seconds=self._segment_seconds,
            segment_list=segment_list_path,
            ffmpeg=ffmpeg_path,
        )
        try:
            process = self._popen_factory(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_CREATE_NEW_PROCESS_GROUP,
            )
        except FileNotFoundError as exc:
            self.ffmpeg_missing = True
            self._failed_camera_ids.add(camera.id)
            logger.error(
                "ffmpeg not found when starting recording for camera %s (%s): %s. "
                "Install ffmpeg and put it on PATH, then restart the app.",
                camera.id, camera.name, exc,
            )
            return
        except OSError as exc:
            self._failed_camera_ids.add(camera.id)
            logger.error(
                "Failed to spawn ffmpeg for camera %s (%s): %s",
                camera.id, camera.name, exc,
            )
            return
        self._recordings[camera.id] = _Recording(
            camera=camera,
            process=process,
            segment_list_path=segment_list_path,
        )

    def stop(self, camera_id: int) -> None:
        """Begin shutdown for ``camera_id``. Non-blocking.

        Signals ffmpeg gracefully and parks the recording on the ``_stopping``
        queue; :meth:`poll` reaps it once the process exits or its deadline
        expires. The UI thread returns instantly so the Stop button never
        causes a "Not Responding" freeze.
        """
        recording = self._recordings.pop(camera_id, None)
        if recording is None:
            return
        process = recording.process
        if process.poll() is not None:
            # Already exited (e.g. crashed before stop) — just ingest the trailer.
            self._ingest_new_segments(recording)
            return
        self._send_graceful(process)
        self._stopping.append(
            _Stopping(
                recording=recording,
                deadline=self._clock() + timedelta(seconds=GRACEFUL_TIMEOUT_SECONDS),
            )
        )

    def stop_all(self) -> None:
        """Stop every active recording. Used on app shutdown.

        Briefly synchronous: signals everything, then waits up to the graceful
        timeout for processes to flush their MP4 trailers, then force-kills any
        laggards. Bounded total runtime ≈ ``GRACEFUL_TIMEOUT_SECONDS + 1``.
        """
        for camera_id in list(self._recordings.keys()):
            self.stop(camera_id)
        deadline = self._clock() + timedelta(seconds=GRACEFUL_TIMEOUT_SECONDS)
        for entry in list(self._stopping):
            process = entry.recording.process
            remaining = (deadline - self._clock()).total_seconds()
            if remaining > 0 and process.poll() is None:
                try:
                    process.wait(timeout=remaining)
                except subprocess.TimeoutExpired:
                    pass
            if process.poll() is None:
                try:
                    process.kill()
                except OSError:
                    pass
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
            self._ingest_new_segments(entry.recording)
        self._stopping.clear()

    def apply_modes(self) -> None:
        """Reconcile running ffmpegs against the cameras table."""
        cameras_by_id = {c.id: c for c in self._cameras.list()}
        for camera_id in list(self._recordings.keys()):
            camera = cameras_by_id.get(camera_id)
            if camera is None or camera.record_mode == RecordMode.OFF:
                self.stop(camera_id)
        for camera in cameras_by_id.values():
            if camera.record_mode == RecordMode.OFF:
                continue
            if camera.id in self._recordings:
                continue
            self.start(camera)

    def poll(self) -> None:
        """Tick: drain segment lists, restart crashes, reap stopping processes."""
        now = self._clock()
        for camera_id, recording in list(self._recordings.items()):
            self._ingest_new_segments(recording)
            returncode = recording.process.poll()
            if returncode is None:
                continue
            if recording.next_restart_after is None:
                recording.next_restart_after = now + timedelta(seconds=RESTART_BACKOFF_SECONDS)
                logger.warning(
                    "ffmpeg for camera %s exited with %s; restart scheduled",
                    camera_id,
                    returncode,
                )
                continue
            if now < recording.next_restart_after:
                continue
            camera = recording.camera
            del self._recordings[camera_id]
            self.start(camera)
        # Reap recordings whose graceful shutdown is in flight.
        remaining: list[_Stopping] = []
        for entry in self._stopping:
            process = entry.recording.process
            if process.poll() is not None:
                self._ingest_new_segments(entry.recording)
                continue
            if now < entry.deadline:
                remaining.append(entry)
                continue
            if not entry.killed:
                try:
                    process.kill()
                except OSError:
                    pass
                entry.killed = True
                entry.deadline = now + timedelta(seconds=TERMINATE_TIMEOUT_SECONDS)
                remaining.append(entry)
                continue
            # Already killed but still showing alive — give up tracking it.
            logger.warning(
                "Recording for camera %s did not exit after kill — dropping tracker",
                entry.recording.camera.id,
            )
            self._ingest_new_segments(entry.recording)
        self._stopping = remaining

    def _send_graceful(self, process: object) -> None:
        """Ask ffmpeg to close cleanly (Ctrl-Break on Windows, SIGINT on Unix).

        ffmpeg responds by finishing the current segment — closing the MP4 trailer
        so ``+faststart`` produces a playable file — before exiting.
        """
        graceful_signal = (
            signal.CTRL_BREAK_EVENT
            if sys.platform.startswith("win") and hasattr(signal, "CTRL_BREAK_EVENT")
            else signal.SIGINT
        )
        try:
            process.send_signal(graceful_signal)
        except (OSError, ValueError):
            pass

    def _ingest_new_segments(self, recording: _Recording) -> None:
        path = recording.segment_list_path
        if not path.exists():
            return
        try:
            with path.open("rb") as f:
                f.seek(recording.segment_list_offset)
                data = f.read()
        except OSError:
            return
        if not data:
            return
        consumed = 0
        while True:
            nl = data.find(b"\n", consumed)
            if nl == -1:
                break
            line = data[consumed:nl].decode("utf-8", errors="replace").strip()
            consumed = nl + 1
            self._record_segment_line(recording, line)
        recording.segment_list_offset += consumed

    def _record_segment_line(self, recording: _Recording, line: str) -> None:
        if not line:
            return
        parts = line.split(",")
        if len(parts) < 3:
            return
        filename, start_str, end_str = parts[0], parts[1], parts[2]
        try:
            duration: int | None = max(0, int(float(end_str) - float(start_str)))
        except ValueError:
            duration = None
        segment_path = Path(filename)
        if not segment_path.is_absolute():
            segment_path = recording.segment_list_path.parent / segment_path
        try:
            started_at = datetime.strptime(segment_path.stem, "%Y-%m-%d_%H-%M-%S")
        except ValueError:
            started_at = self._clock()
        self._segments.add(
            camera_id=recording.camera.id,
            path=segment_path,
            started_at=started_at,
            duration_seconds=duration,
            has_audio=recording.has_audio,
        )
