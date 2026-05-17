from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ngc_cams.onvif.ptz import VALID_DIRECTIONS, PTZError, onvif_endpoint_from_rtsp

router = APIRouter()


@router.post("/cameras/{camera_id}/ptz/stop")
def ptz_stop(request: Request, camera_id: int):
    stored = request.app.state.cameras.get(camera_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    if not stored.ptz_enabled:
        raise HTTPException(status_code=409, detail="Camera is not PTZ-enabled")
    host, port = onvif_endpoint_from_rtsp(stored.rtsp_url)
    try:
        request.app.state.ptz_service.stop(
            host=host,
            port=port,
            username=stored.username,
            password=stored.password,
        )
    except PTZError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"status": "ok"}


@router.post("/cameras/{camera_id}/ptz/{direction}")
def ptz_move(request: Request, camera_id: int, direction: str):
    if direction not in VALID_DIRECTIONS:
        raise HTTPException(status_code=422, detail=f"Unknown PTZ direction: {direction}")
    stored = request.app.state.cameras.get(camera_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    if not stored.ptz_enabled:
        raise HTTPException(status_code=409, detail="Camera is not PTZ-enabled")
    host, port = onvif_endpoint_from_rtsp(stored.rtsp_url)
    try:
        request.app.state.ptz_service.move(
            host=host,
            port=port,
            username=stored.username,
            password=stored.password,
            direction=direction,
        )
    except PTZError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"status": "ok"}
