from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlparse, urlunparse

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ngc_cams.models import Camera, RecordMode, StoredCamera
from ngc_cams.recording.paths import snapshot_output_path
from ngc_cams.vlc_logging import redirect_fd_to_file, restore_fd, rotate_log_file


_VLC_INSTALL_CANDIDATES = (
    r"C:\Program Files\VideoLAN\VLC",
    r"C:\Program Files (x86)\VideoLAN\VLC",
)


def _register_vlc_dll_path() -> str | None:
    for path in _VLC_INSTALL_CANDIDATES:
        if (Path(path) / "libvlc.dll").exists():
            try:
                os.add_dll_directory(path)
            except (AttributeError, OSError):
                pass
            return path
    return None


def build_rtsp_url_with_credentials(
    rtsp_url: str, username: str | None, password: str | None
) -> str:
    if not username and not password:
        return rtsp_url
    parsed = urlparse(rtsp_url)
    if "@" in parsed.netloc:
        return rtsp_url
    user_part = quote(username or "", safe="")
    if password:
        user_part = f"{user_part}:{quote(password, safe='')}"
    return urlunparse(parsed._replace(netloc=f"{user_part}@{parsed.netloc}"))


class ViewerPanel(QWidget):
    """Embeds libvlc in a Qt frame for RTSP playback. Gracefully degrades when libvlc is missing."""

    record_toggled = pyqtSignal(object)  # StoredCamera

    def __init__(
        self,
        snapshot_root: Path | None = None,
        vlc_log_path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._instance = None
        self._player = None
        self._current_url: str | None = None
        self._current_camera: Camera | None = None
        self._libvlc_error: str | None = None
        self._snapshot_root = snapshot_root
        self._vlc_log_path = vlc_log_path
        self._stderr_saved_fd: int | None = None

        self._video_frame = QFrame()
        self._video_frame.setMinimumSize(640, 360)
        self._video_frame.setStyleSheet("background: #111;")
        # libvlc renders into the native HWND. Qt 6 uses "alien" widgets by default
        # (no real Win32 child window), so we have to force a native handle and
        # tell Qt not to repaint over libvlc's surface.
        self._video_frame.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self._video_frame.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors, True)
        self._video_frame.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)

        self._status_label = QLabel("No camera selected")
        self._status_label.setStyleSheet("color: #aaa; font-size: 11px;")
        self._status_label.setWordWrap(True)

        self._snapshot_btn = QPushButton("Snapshot")
        self._snapshot_btn.setEnabled(False)
        self._snapshot_btn.clicked.connect(self._on_snapshot)

        self._record_btn = QPushButton("Record")
        self._record_btn.setEnabled(False)
        self._record_btn.clicked.connect(self._on_record_toggle)

        controls = QHBoxLayout()
        controls.addWidget(self._snapshot_btn)
        controls.addWidget(self._record_btn)
        for label_text in ["Grid", "Playback"]:
            btn = QPushButton(label_text)
            btn.setEnabled(False)
            controls.addWidget(btn)
        controls.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(self._video_frame, stretch=1)
        layout.addLayout(controls)
        layout.addWidget(self._status_label)

    def _ensure_player(self) -> bool:
        if self._player is not None:
            return True
        if self._libvlc_error is not None:
            return False
        _register_vlc_dll_path()
        # Capture fd 2 before libvlc loads: live555's buffer-overflow warnings come from
        # native C++ and bypass both libvlc's --quiet and Python's sys.stderr replacement.
        if self._vlc_log_path is not None and self._stderr_saved_fd is None:
            try:
                rotate_log_file(self._vlc_log_path)
                self._stderr_saved_fd = redirect_fd_to_file(2, self._vlc_log_path)
            except OSError:
                self._stderr_saved_fd = None
        try:
            import vlc
        except (ImportError, OSError, FileNotFoundError) as exc:
            self._libvlc_error = (
                f"libvlc not available ({exc}). Install 64-bit VLC from https://www.videolan.org/ "
                "(your Python is 64-bit; a 32-bit VLC will not load)."
            )
            self._status_label.setText(self._libvlc_error)
            return False
        try:
            # --rtsp-frame-buffer-size raises live555's OutPacketBuffer::maxSize above its
            # 250 KB default so high-bitrate keyframes don't trip the overflow warning.
            self._instance = vlc.Instance(
                "--network-caching=300",
                "--rtsp-tcp",
                "--rtsp-frame-buffer-size=2000000",
                "--quiet",
            )
        except Exception as exc:  # noqa: BLE001 — surface any libvlc init failure to the user
            self._libvlc_error = f"libvlc failed to initialise: {exc}"
            self._status_label.setText(self._libvlc_error)
            return False
        if self._instance is None:
            self._libvlc_error = "libvlc failed to create an instance."
            self._status_label.setText(self._libvlc_error)
            return False
        self._player = self._instance.media_player_new()
        win_id = int(self._video_frame.winId())
        if sys.platform.startswith("win"):
            self._player.set_hwnd(win_id)
        elif sys.platform == "darwin":
            self._player.set_nsobject(win_id)
        else:
            self._player.set_xwindow(win_id)
        return True

    def play(self, camera: Camera) -> None:
        if not camera.rtsp_url:
            self._status_label.setText(f"No RTSP URL for {camera.name}")
            return
        rtsp_url = build_rtsp_url_with_credentials(
            camera.rtsp_url, camera.username, camera.password
        )
        if not self._ensure_player():
            return
        if rtsp_url == self._current_url and self._player.is_playing():
            self._status_label.setText(f"Playing: {camera.name}")
            return
        media = self._instance.media_new(rtsp_url)
        media.add_option(":network-caching=300")
        media.add_option(":rtsp-tcp")
        self._player.set_media(media)
        self._player.play()
        self._current_url = rtsp_url
        self._current_camera = camera
        self._snapshot_btn.setEnabled(True)
        self._refresh_record_button()
        self._status_label.setText(f"Playing: {camera.name} — {camera.rtsp_url}")

    def stop(self) -> None:
        if self._player is not None:
            self._player.stop()
        self._current_url = None
        self._current_camera = None
        self._snapshot_btn.setEnabled(False)
        self._record_btn.setEnabled(False)
        self._record_btn.setText("Record")
        if self._libvlc_error is None:
            self._status_label.setText("No camera selected")

    def release(self) -> None:
        if self._player is not None:
            self._player.stop()
            self._player.release()
            self._player = None
        if self._instance is not None:
            self._instance.release()
            self._instance = None
        if self._stderr_saved_fd is not None:
            try:
                restore_fd(2, self._stderr_saved_fd)
            except OSError:
                pass
            self._stderr_saved_fd = None

    def _refresh_record_button(self) -> None:
        camera = self._current_camera
        is_stored = isinstance(camera, StoredCamera) and camera.id > 0
        self._record_btn.setEnabled(is_stored)
        if is_stored and camera.record_mode != RecordMode.OFF:
            self._record_btn.setText("Stop recording")
        else:
            self._record_btn.setText("Record")

    def set_recording_state(self, camera_id: int, is_recording: bool) -> None:
        """Called by MainWindow after the manager toggles a camera, so the button
        label reflects the actual recorder state instead of the stale DB value."""
        camera = self._current_camera
        if not isinstance(camera, StoredCamera) or camera.id != camera_id:
            return
        self._record_btn.setText("Stop recording" if is_recording else "Record")

    def _on_record_toggle(self) -> None:
        camera = self._current_camera
        if not isinstance(camera, StoredCamera) or camera.id <= 0:
            return
        self.record_toggled.emit(camera)

    def _on_snapshot(self) -> None:
        if self._player is None or self._current_camera is None:
            self._status_label.setText("Nothing to snapshot — select a camera first.")
            return
        if self._snapshot_root is None:
            self._status_label.setText("Snapshot root is not configured.")
            return
        path = snapshot_output_path(self._snapshot_root, self._current_camera, datetime.now())
        path.parent.mkdir(parents=True, exist_ok=True)
        result = self._player.video_take_snapshot(0, str(path), 0, 0)
        if result == 0:
            self._status_label.setText(f"Saved snapshot: {path}")
        else:
            self._status_label.setText(
                f"Snapshot failed (libvlc returned {result}). Is the stream actually playing?"
            )
