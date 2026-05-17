from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()

_EVENT_LIMIT = 50


@router.get("/events", response_class=HTMLResponse)
def events(request: Request):
    cameras = request.app.state.cameras.list()
    cam_lookup = {c.id: c for c in cameras}
    segments_repo = getattr(request.app.state, "segments", None)
    all_segments: list = []
    if segments_repo is not None:
        for cam in cameras:
            all_segments.extend(segments_repo.list_by_camera(cam.id))
        all_segments.sort(key=lambda s: s.started_at, reverse=True)
        all_segments = all_segments[:_EVENT_LIMIT]
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "events.html",
        {
            "active_nav": "events",
            "segments": all_segments,
            "cam_lookup": cam_lookup,
        },
    )
