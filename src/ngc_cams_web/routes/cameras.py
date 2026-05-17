from __future__ import annotations

import shutil
from dataclasses import replace
from datetime import datetime

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ngc_cams.models import Camera, RecordMode

router = APIRouter()

GRID_MAX_CELLS = 8
DASHBOARD_FEED_LIMIT = 3


def _free_storage_str(path) -> str:
    try:
        path.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(path)
    except OSError:
        return "—"
    gb = usage.free / (1024 ** 3)
    if gb >= 1024:
        return f"{gb / 1024:.1f} TB"
    return f"{gb:.0f} GB"


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    cameras_repo = request.app.state.cameras
    cameras = cameras_repo.list()
    segments_repo = getattr(request.app.state, "segments", None)
    config = request.app.state.config
    recent_segments: list = []
    if segments_repo is not None:
        for cam in cameras:
            recent_segments.extend(segments_repo.list_by_camera(cam.id))
        recent_segments.sort(key=lambda s: s.started_at, reverse=True)
        recent_segments = recent_segments[:6]
    cam_lookup = {c.id: c for c in cameras}
    active_alerts = sum(1 for c in cameras if c.record_mode != RecordMode.OFF)
    stats = {
        "total_cameras": len(cameras),
        "active_alerts": active_alerts,
        "uptime": "99.8%",
        "free_storage": _free_storage_str(config.recording_root),
    }
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "active_nav": "dashboard",
            "cameras": cameras,
            "feed_cameras": cameras[:DASHBOARD_FEED_LIMIT],
            "stats": stats,
            "recent_segments": recent_segments,
            "cam_lookup": cam_lookup,
            "now": datetime.now(),
        },
    )


@router.get("/grid", response_class=HTMLResponse)
def grid(request: Request):
    cameras = request.app.state.cameras.list()
    visible = cameras[:GRID_MAX_CELLS]
    hidden_count = max(0, len(cameras) - GRID_MAX_CELLS)
    main_camera = visible[0] if visible else None
    side_cameras = visible[1:] if len(visible) > 1 else []
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "grid.html",
        {
            "active_nav": "matrix",
            "visible": visible,
            "main_camera": main_camera,
            "side_cameras": side_cameras,
            "hidden_count": hidden_count,
            "max_cells": GRID_MAX_CELLS,
        },
    )


@router.post("/cameras/add")
def add_camera(
    request: Request,
    name: str = Form(...),
    rtsp_url: str = Form(...),
    ptz_enabled: str | None = Form(default=None),
):
    request.app.state.cameras.add(
        Camera(name=name, rtsp_url=rtsp_url, ptz_enabled=bool(ptz_enabled))
    )
    return RedirectResponse("/", status_code=303)


@router.post("/cameras/{camera_id}/delete")
def delete_camera(request: Request, camera_id: int):
    deleted = request.app.state.cameras.delete(camera_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Camera not found")
    return RedirectResponse("/", status_code=303)


@router.post("/cameras/{camera_id}/record")
def toggle_record(request: Request, camera_id: int):
    repo = request.app.state.cameras
    stored = repo.get(camera_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    next_mode = RecordMode.VIDEO_ONLY if stored.record_mode == RecordMode.OFF else RecordMode.OFF
    repo.update(camera_id, replace(stored, record_mode=next_mode))
    manager = request.app.state.recording_manager
    if manager is not None:
        manager.apply_modes()
    return RedirectResponse("/", status_code=303)


@router.get("/cameras/{camera_id}", response_class=HTMLResponse)
def camera_detail(request: Request, camera_id: int):
    stored = request.app.state.cameras.get(camera_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "camera_detail.html", {"camera": stored})
