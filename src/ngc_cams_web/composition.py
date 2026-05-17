from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ngc_cams.cameras import CameraRepository
from ngc_cams.config import AppConfig
from ngc_cams.onvif.discovery import DiscoveryService
from ngc_cams.onvif.ptz import PTZService
from ngc_cams.onvif.streams import get_stream_uris
from ngc_cams.recording.retention import enforce_storage_cap, prune_all
from ngc_cams.segments import SegmentRepository
from ngc_cams_web.routes import cameras as cameras_routes
from ngc_cams_web.routes import discovery as discovery_routes
from ngc_cams_web.routes import events as events_routes
from ngc_cams_web.routes import live as live_routes
from ngc_cams_web.routes import ptz as ptz_routes
from ngc_cams_web.routes import settings as settings_routes

logger = logging.getLogger(__name__)
_TEMPLATE_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"


def _default_resolve_streams(cam):
    """Anonymous ONVIF probe for stream URIs after WS-Discovery finds a host.
    Wrapped in a try by `run_discovery` so a failed probe (camera demands
    auth, port closed) just leaves `main_rtsp_url=None` on the result."""
    return get_stream_uris(cam.address)


def _build_lifespan(
    recording_manager,
    poll_interval_seconds: float,
    cameras: CameraRepository | None,
    segments: SegmentRepository | None,
    retention_interval_seconds: float | None,
    config: AppConfig | None = None,
):
    retention_enabled = (
        cameras is not None
        and segments is not None
        and retention_interval_seconds is not None
    )

    @contextlib.asynccontextmanager
    async def lifespan(app):
        stop = asyncio.Event()

        async def poller():
            while not stop.is_set():
                try:
                    recording_manager.poll()
                except Exception:  # noqa: BLE001 — poller must survive transient errors
                    logger.exception("recording poll tick failed")
                try:
                    await asyncio.wait_for(stop.wait(), timeout=poll_interval_seconds)
                except asyncio.TimeoutError:
                    pass

        async def retention():
            while not stop.is_set():
                try:
                    override = config.default_retention_days if config else None
                    limit_bytes = (
                        config.storage_limit_gb * 1_000_000_000
                        if config and config.storage_limit_gb > 0
                        else 0
                    )
                    deleted_by_age = prune_all(
                        cameras,
                        segments,
                        now=datetime.now(),
                        retention_days_override=override,
                    )
                    deleted_by_cap = enforce_storage_cap(
                        segments, storage_limit_bytes=limit_bytes
                    )
                    total = sum(len(v) for v in deleted_by_age.values()) + len(
                        deleted_by_cap
                    )
                    if total:
                        logger.info(
                            "retention pruned %s segment(s) (age=%s, cap=%s)",
                            total,
                            sum(len(v) for v in deleted_by_age.values()),
                            len(deleted_by_cap),
                        )
                except Exception:  # noqa: BLE001
                    logger.exception("retention pass failed")
                try:
                    await asyncio.wait_for(
                        stop.wait(), timeout=retention_interval_seconds
                    )
                except asyncio.TimeoutError:
                    pass

        tasks = [asyncio.create_task(poller())]
        if retention_enabled:
            tasks.append(asyncio.create_task(retention()))
        try:
            yield
        finally:
            stop.set()
            for task in tasks:
                await task
            try:
                recording_manager.stop_all()
            except Exception:  # noqa: BLE001
                logger.exception("recording stop_all failed")

    return lifespan


def build_app(
    *,
    cameras: CameraRepository,
    discovery: DiscoveryService | None,
    recording_manager,
    segments: SegmentRepository | None = None,
    lifespan_poll_seconds: float | None = None,
    retention_interval_seconds: float | None = None,
    config: AppConfig | None = None,
) -> FastAPI:
    lifespan = (
        _build_lifespan(
            recording_manager,
            lifespan_poll_seconds,
            cameras if segments is not None else None,
            segments,
            retention_interval_seconds,
            config,
        )
        if recording_manager is not None and lifespan_poll_seconds is not None
        else None
    )
    app = FastAPI(title="SISI-TV", lifespan=lifespan)
    app.state.cameras = cameras
    app.state.discovery = discovery
    app.state.recording_manager = recording_manager
    app.state.segments = segments
    app.state.ptz_service = PTZService()
    app.state.resolve_streams = _default_resolve_streams
    app.state.config = config if config is not None else AppConfig()
    app.state.templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    app.include_router(cameras_routes.router)
    app.include_router(discovery_routes.router)
    app.include_router(events_routes.router)
    app.include_router(live_routes.router)
    app.include_router(ptz_routes.router)
    app.include_router(settings_routes.router)
    return app
