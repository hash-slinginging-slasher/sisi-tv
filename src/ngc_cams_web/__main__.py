from __future__ import annotations

import socket
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


def _lan_hostname() -> str:
    """Best-guess LAN IP for log/browser convenience when bound to 0.0.0.0."""
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "127.0.0.1"


def main() -> int:
    config = AppConfig.from_settings()
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
        disk_guard_free_gb=config.disk_guard_free_gb,
    )

    app = build_app(
        cameras=cameras,
        discovery=discovery,
        recording_manager=recording,
        segments=segments,
        lifespan_poll_seconds=1.0,
        retention_interval_seconds=300.0,
        config=config,
    )

    host = config.bind_host
    port = config.bind_port
    # webbrowser.open should hit a routable address. 0.0.0.0 is a bind sentinel,
    # not a real destination — use the LAN IP (or 127.0.0.1 as fallback).
    open_host = host if host not in ("0.0.0.0", "::") else _lan_hostname()
    open_url = f"http://{open_host}:{port}/"

    print(f"SISI-TV binding {host}:{port}")
    if host in ("0.0.0.0", "::"):
        print(f"  LAN: http://{_lan_hostname()}:{port}/")
        print(f"  Or:  http://{socket.gethostname()}:{port}/")
        print("  (anyone on this network can reach the app -- no auth)")
    print(f"  Local: http://127.0.0.1:{port}/")

    def _open_when_ready():
        time.sleep(0.6)
        try:
            webbrowser.open(open_url)
        except Exception:
            pass

    threading.Thread(target=_open_when_ready, daemon=True).start()
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        timeout_graceful_shutdown=5,
    )
    connection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
