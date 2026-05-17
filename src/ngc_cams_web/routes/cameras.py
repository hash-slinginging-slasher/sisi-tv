from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    cameras = request.app.state.cameras.list()
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "index.html", {"cameras": cameras})
