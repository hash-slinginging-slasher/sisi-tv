from __future__ import annotations

import sys


def main() -> int:
    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        print("PyQt6 is not installed. Run: pip install -r requirements-dev.txt", file=sys.stderr)
        return 1

    from ngc_cams.cameras import CameraRepository
    from ngc_cams.config import AppConfig
    from ngc_cams.db import connect, initialize
    from ngc_cams.onvif.discovery import DiscoveryService
    from ngc_cams.recording.manager import RecordingManager
    from ngc_cams.segments import SegmentRepository
    from ngc_cams.ui.main_window import MainWindow

    config = AppConfig()
    connection = connect(config.db_path)
    initialize(connection)
    repository = CameraRepository(connection)
    segments = SegmentRepository(connection)
    discovery = DiscoveryService()
    recording_manager = RecordingManager(
        repository,
        segments,
        recording_root=config.recording_root,
        segment_seconds=config.segment_seconds,
    )

    app = QApplication(sys.argv)
    window = MainWindow(
        repository,
        discovery,
        snapshot_root=config.snapshot_root,
        vlc_log_path=config.vlc_log_path,
        recording_manager=recording_manager,
    )
    window.show()
    exit_code = app.exec()
    connection.close()
    return exit_code
