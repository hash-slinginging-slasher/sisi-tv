from __future__ import annotations

from fastapi import FastAPI

from ngc_cams.cameras import CameraRepository
from ngc_cams.onvif.discovery import DiscoveryService


def build_app(
    *,
    cameras: CameraRepository,
    discovery: DiscoveryService,
    recording_manager,
    live_stream_manager,
) -> FastAPI:
    app = FastAPI(title="ngc-cams")
    app.state.cameras = cameras
    app.state.discovery = discovery
    app.state.recording_manager = recording_manager
    app.state.live_stream_manager = live_stream_manager

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    return app
