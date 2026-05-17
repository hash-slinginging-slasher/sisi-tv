from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from ngc_cams.cameras import CameraRepository
from ngc_cams.onvif.discovery import DiscoveryService
from ngc_cams_web.routes import cameras as cameras_routes
from ngc_cams_web.routes import discovery as discovery_routes

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def build_app(
    *,
    cameras: CameraRepository,
    discovery: DiscoveryService | None,
    recording_manager,
    live_stream_manager,
) -> FastAPI:
    app = FastAPI(title="ngc-cams")
    app.state.cameras = cameras
    app.state.discovery = discovery
    app.state.recording_manager = recording_manager
    app.state.live_stream_manager = live_stream_manager
    app.state.templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    app.include_router(cameras_routes.router)
    app.include_router(discovery_routes.router)
    return app
