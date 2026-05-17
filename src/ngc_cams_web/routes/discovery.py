from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ngc_cams.discovery_runner import run_discovery

router = APIRouter()


@router.post("/discover", response_class=HTMLResponse)
def discover(request: Request):
    service = request.app.state.discovery
    result = run_discovery(service, timeout=5)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "_discovered.html",
        {"cameras": result.cameras, "error": result.error},
    )
