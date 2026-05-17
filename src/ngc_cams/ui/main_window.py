from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ngc_cams.cameras import CameraRepository
from ngc_cams.models import Camera, RecordMode, StoredCamera
from ngc_cams.onvif.discovery import DiscoveredCamera, DiscoveryService
from ngc_cams.onvif.streams import StreamUris, get_stream_uris
from ngc_cams.recording.manager import RecordingManager
from ngc_cams.ui.cameras_tab import CamerasTab
from ngc_cams.ui.discovered_tab import DiscoveredTab
from ngc_cams.ui.viewer_panel import ViewerPanel


class MainWindow(QMainWindow):
    def __init__(
        self,
        repository: CameraRepository,
        discovery: DiscoveryService,
        snapshot_root: Path | None = None,
        vlc_log_path: Path | None = None,
        recording_manager: RecordingManager | None = None,
        poll_interval_ms: int = 2_000,
    ) -> None:
        super().__init__()
        self.setWindowTitle("ONVIF Camera Manager")
        self.resize(1100, 720)
        self._repository = repository
        self._recording_manager = recording_manager
        self._cameras_tab = CamerasTab(repository)
        self._discovered_tab = DiscoveredTab(
            discovery,
            open_add_dialog=self._open_add_camera_from_discovery,
            play_discovered=self._play_discovered,
            resolve_streams=_resolve_streams_anonymous,
        )
        self._viewer_panel = ViewerPanel(
            snapshot_root=snapshot_root,
            vlc_log_path=vlc_log_path,
        )
        self._cameras_tab.camera_selected.connect(self._on_camera_selected)
        self._viewer_panel.record_toggled.connect(self._on_record_toggled)
        self.setCentralWidget(self._build_central_widget())
        QTimer.singleShot(200, self._discovered_tab.start_discovery)
        if self._recording_manager is not None:
            self._recording_manager.apply_modes()
            self._poll_timer = QTimer(self)
            self._poll_timer.setInterval(poll_interval_ms)
            self._poll_timer.timeout.connect(self._recording_manager.poll)
            self._poll_timer.start()
            if self._recording_manager.ffmpeg_missing:
                QTimer.singleShot(0, self._warn_ffmpeg_missing)

    def _on_camera_selected(self, camera: StoredCamera | None) -> None:
        if camera is None:
            self._viewer_panel.stop()
        else:
            self._viewer_panel.play(camera)

    def _play_discovered(self, cam: DiscoveredCamera) -> None:
        synthetic = Camera(
            name=cam.manufacturer or cam.address,
            rtsp_url=cam.main_rtsp_url or "",
            sub_stream_url=cam.sub_rtsp_url,
        )
        self._viewer_panel.play(synthetic)

    def _open_add_camera_from_discovery(self, prefill_ip: str | None) -> None:
        self._cameras_tab.open_add_dialog(prefill_ip=prefill_ip)
        self._tabs.setCurrentWidget(self._cameras_tab)

    def _on_record_toggled(self, camera: StoredCamera) -> None:
        if self._recording_manager is None:
            return
        # Toggle the DB record_mode (off ↔ video_only). Audio mode is set via the
        # camera edit dialog; the Record button is a binary on/off.
        new_mode = RecordMode.OFF if camera.record_mode != RecordMode.OFF else RecordMode.VIDEO_ONLY
        # Don't toggle the DB into a recording state we can't fulfill — that's how
        # we got into the "crashes on every launch" situation.
        if new_mode != RecordMode.OFF and not self._recording_manager.ffmpeg_available():
            self._warn_ffmpeg_missing()
            return
        try:
            updated = self._repository.update(
                camera.id,
                Camera(
                    name=camera.name,
                    rtsp_url=camera.rtsp_url,
                    username=camera.username,
                    password=camera.password,
                    sub_stream_url=camera.sub_stream_url,
                    ptz_enabled=camera.ptz_enabled,
                    record_mode=new_mode,
                    retention_days=camera.retention_days,
                ),
            )
        except KeyError:
            return
        self._recording_manager.apply_modes()
        self._cameras_tab.refresh()
        self._viewer_panel.set_recording_state(
            updated.id, self._recording_manager.is_recording(updated.id)
        )

    def _warn_ffmpeg_missing(self) -> None:
        QMessageBox.warning(
            self,
            "ffmpeg not found",
            "Recording requires ffmpeg, but it isn't on PATH.\n\n"
            "Install ffmpeg (https://www.gyan.dev/ffmpeg/builds/ for a Windows build), "
            "make sure ffmpeg.exe is reachable via PATH, then restart the app.",
        )

    def _build_central_widget(self) -> QWidget:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._viewer_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        return splitter

    def _build_left_panel(self) -> QWidget:
        tabs = QTabWidget()
        tabs.addTab(self._cameras_tab, "Cameras")
        tabs.addTab(self._discovered_tab, "Discovered")
        tabs.addTab(self._build_settings_tab(), "Settings")
        tabs.setMinimumWidth(360)
        self._tabs = tabs
        return tabs

    def _build_settings_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel(r"Recordings: D:\ngc-cams-recordings"))
        layout.addWidget(QLabel(r"Snapshots: D:\ngc-cams-snapshots"))
        layout.addWidget(QLabel("Segment length: 10 minutes"))
        layout.addStretch()
        return widget

    def closeEvent(self, event: QCloseEvent) -> None:
        # Stop any in-flight WS-Discovery worker so the app exits cleanly without
        # "QThread: Destroyed while thread is still running" warnings on stderr.
        # closeEvent on child widgets won't fire — Qt only delivers it to top-level
        # windows — so the wire-up has to live here.
        self._discovered_tab.stop_worker()
        if self._recording_manager is not None:
            self._recording_manager.stop_all()
        self._viewer_panel.release()
        super().closeEvent(event)


def _resolve_streams_anonymous(cam: DiscoveredCamera) -> StreamUris:
    """Try anonymous ONVIF GetStreamUri; if the camera requires auth, the runner catches and skips."""
    port = urlparse(cam.xaddr).port or 80
    return get_stream_uris(cam.address, username="", password="", port=port)
