from __future__ import annotations

import subprocess
from typing import Iterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from ngc_cams.recording.locator import find_ffmpeg_executable
from ngc_cams_web.live import build_mjpeg_command, iter_mjpeg_multipart

router = APIRouter()
_BOUNDARY = b"frame"


@router.get("/cameras/{camera_id}/live.mjpg")
def live_mjpeg(request: Request, camera_id: int):
    stored = request.app.state.cameras.get(camera_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Camera not found")

    resolver = getattr(request.app.state, "live_ffmpeg_resolver", find_ffmpeg_executable)
    ffmpeg_path = resolver()
    if ffmpeg_path is None:
        raise HTTPException(status_code=503, detail="ffmpeg not installed")

    popen = getattr(request.app.state, "live_popen_factory", subprocess.Popen)
    command = build_mjpeg_command(stored.rtsp_url, ffmpeg=ffmpeg_path)
    process = popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )

    def generate() -> Iterator[bytes]:
        try:
            yield from iter_mjpeg_multipart(process.stdout, boundary=_BOUNDARY)
        finally:
            if process.poll() is None:
                try:
                    process.kill()
                except OSError:
                    pass
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass

    return StreamingResponse(
        generate(),
        media_type=f"multipart/x-mixed-replace; boundary={_BOUNDARY.decode()}",
    )


# --- HLS live view -------------------------------------------------------
# Replaces the per-viewer MJPEG transcoder above (kept around for now as a
# fallback) with one ffmpeg per camera that all viewers share. See
# ngc_cams_web/hls.py for the manager. Playlist + segment URLs both live
# under /cameras/{id}/live/* so the .m3u8's relative segment filenames
# resolve to /cameras/{id}/live/seg_XXXXX.ts on the browser side.


@router.get("/cameras/{camera_id}/live/index.m3u8")
def live_playlist(request: Request, camera_id: int):
    stored = request.app.state.cameras.get(camera_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    manager = getattr(request.app.state, "live_stream_manager", None)
    if manager is None:
        # Not wired in this composition (e.g. some tests); fall back to 404
        # so the <video> tag tries MJPEG instead of looping on 5xx.
        raise HTTPException(status_code=404, detail="HLS not available")
    path = manager.request_playlist(stored)
    if path is None:
        # ffmpeg starting up but the playlist file isn't on disk yet, OR
        # ffmpeg unavailable. Send a 503 so hls.js retries with backoff
        # rather than treating it as a fatal stream error.
        return Response(status_code=503, content=b"")
    return FileResponse(
        path,
        media_type="application/vnd.apple.mpegurl",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@router.get("/cameras/{camera_id}/live/{segment_name}")
def live_segment(request: Request, camera_id: int, segment_name: str):
    if request.app.state.cameras.get(camera_id) is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    manager = getattr(request.app.state, "live_stream_manager", None)
    if manager is None:
        raise HTTPException(status_code=404, detail="HLS not available")
    path = manager.segment_path(camera_id, segment_name)
    if path is None:
        raise HTTPException(status_code=404, detail="Segment not found")
    return FileResponse(
        path,
        media_type="video/mp2t",
        headers={"Cache-Control": "public, max-age=4"},
    )
