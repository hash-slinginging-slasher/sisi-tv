from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ngc_cams.models import Camera

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
):
    request.app.state.cameras.add(Camera(name=name, rtsp_url=rtsp_url))
    return RedirectResponse("/", status_code=303)
