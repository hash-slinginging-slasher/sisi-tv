from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ngc_cams.models import Camera, RecordMode

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    cameras = request.app.state.cameras.list()
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "index.html", {"cameras": cameras})


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
