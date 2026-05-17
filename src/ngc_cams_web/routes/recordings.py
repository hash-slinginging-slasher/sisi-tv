"""Playback of saved recording segments.

`GET /recordings/{segment_id}` renders an HTML5 video player page.
`GET /recordings/{segment_id}/file` serves the .mp4 with FileResponse, which
supports HTTP byte-range requests so the browser can scrub.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

router = APIRouter()


@router.get("/recordings/{segment_id}", response_class=HTMLResponse)
def recording_detail(request: Request, segment_id: int):
    segments_repo = getattr(request.app.state, "segments", None)
    if segments_repo is None:
        raise HTTPException(status_code=503, detail="segments repository not configured")
    segment = segments_repo.get_by_id(segment_id)
    if segment is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    camera = request.app.state.cameras.get(segment.camera_id)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "recording_detail.html",
        {
            "active_nav": "events",
            "segment": segment,
            "camera": camera,
        },
    )


@router.get("/recordings/{segment_id}/file")
def recording_file(request: Request, segment_id: int):
    segments_repo = getattr(request.app.state, "segments", None)
    if segments_repo is None:
        raise HTTPException(status_code=503)
    segment = segments_repo.get_by_id(segment_id)
    if segment is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    if not segment.path.is_file():
        # Row exists but the .mp4 was deleted out from under us (manual
        # cleanup, drive disconnect). Surface a clean 404 instead of 500.
        raise HTTPException(status_code=404, detail="Recording file missing")
    return FileResponse(
        segment.path,
        media_type="video/mp4",
        filename=segment.path.name,
    )
