from __future__ import annotations

import subprocess
from typing import Iterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

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
