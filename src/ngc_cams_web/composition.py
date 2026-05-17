from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from ngc_cams.cameras import CameraRepository
from ngc_cams.onvif.discovery import DiscoveryService
from ngc_cams_web.routes import cameras as cameras_routes
from ngc_cams_web.routes import discovery as discovery_routes
from ngc_cams_web.routes import live as live_routes

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _build_lifespan(recording_manager, interval_seconds: float):
    @contextlib.asynccontextmanager
    async def lifespan(app):
        stop = asyncio.Event()

        async def poller():
            while not stop.is_set():
                try:
                    recording_manager.poll()
                except Exception:  # noqa: BLE001 — poller must survive transient errors
                    pass
                try:
                    await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
                except asyncio.TimeoutError:
                    pass

        task = asyncio.create_task(poller())
        try:
            yield
        finally:
            stop.set()
            await task
            try:
                recording_manager.stop_all()
            except Exception:  # noqa: BLE001
                pass

    return lifespan


def build_app(
    *,
    cameras: CameraRepository,
    discovery: DiscoveryService | None,
    recording_manager,
    live_stream_manager,
    lifespan_poll_seconds: float | None = None,
) -> FastAPI:
    lifespan = (
        _build_lifespan(recording_manager, lifespan_poll_seconds)
        if recording_manager is not None and lifespan_poll_seconds is not None
        else None
    )
    app = FastAPI(title="ngc-cams", lifespan=lifespan)
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
    app.include_router(live_routes.router)
    return app
