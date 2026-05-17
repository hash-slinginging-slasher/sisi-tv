from __future__ import annotations

import sys
import threading
import time
import webbrowser

import uvicorn

from ngc_cams.cameras import CameraRepository
from ngc_cams.config import AppConfig
from ngc_cams.db import connect, initialize
from ngc_cams.onvif.discovery import DiscoveryService
from ngc_cams.recording.manager import RecordingManager
from ngc_cams.segments import SegmentRepository
from ngc_cams_web.composition import build_app


def main() -> int:
    config = AppConfig()
    connection = connect(config.db_path)
    initialize(connection)
    cameras = CameraRepository(connection)
    segments = SegmentRepository(connection)
    discovery = DiscoveryService()
    recording = RecordingManager(
        cameras,
        segments,
        recording_root=config.recording_root,
        segment_seconds=config.segment_seconds,
    )

    app = build_app(
        cameras=cameras,
        discovery=discovery,
        recording_manager=recording,
        live_stream_manager=None,
        lifespan_poll_seconds=1.0,
    )

    host, port = "127.0.0.1", 8000
    url = f"http://{host}:{port}/"

    def _open_when_ready():
        time.sleep(0.6)  # give uvicorn a moment to bind the socket
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=_open_when_ready, daemon=True).start()
    uvicorn.run(app, host=host, port=port, log_level="info")
    connection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
