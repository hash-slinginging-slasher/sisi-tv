"""One-shot snapshot capture via ffmpeg.

POST `/cameras/{id}/snapshot` spawns a short-lived ffmpeg that grabs a single
JPEG from the camera's RTSP feed and writes it to
`<snapshot_root>/<safe_camera_dir>/<YYYY-MM-DD_HH-MM-SS>.jpg`. Returns a 303 to
the detail page where the new shot shows up in the gallery.

GET `/cameras/{id}/snapshots/{filename}` serves the stored JPEG. Filename is
validated against a strict timestamp pattern so the route can't be tricked into
serving anything outside the camera's snapshot dir.
"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse

from ngc_cams.recording.locator import find_ffmpeg_executable
from ngc_cams.recording.paths import safe_camera_dir_name, snapshot_output_path

router = APIRouter()

_SAFE_SNAPSHOT_FILENAME = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.jpg$")
_SNAPSHOT_TIMEOUT_SECONDS = 10


def _build_snapshot_command(ffmpeg: str, rtsp_url: str, output: Path) -> list[str]:
    return [
        ffmpeg,
        "-rtsp_transport",
        "tcp",
        "-y",
        "-loglevel",
        "error",
        "-i",
        rtsp_url,
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(output),
    ]


@router.post("/cameras/{camera_id}/snapshot")
def take_snapshot(request: Request, camera_id: int):
    stored = request.app.state.cameras.get(camera_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Camera not found")

    resolver = getattr(
        request.app.state, "snapshot_ffmpeg_resolver", find_ffmpeg_executable
    )
    ffmpeg_path = resolver()
    if ffmpeg_path is None:
        raise HTTPException(status_code=503, detail="ffmpeg not installed")

    config = request.app.state.config
    when = datetime.now()
    output = snapshot_output_path(config.snapshot_root, stored, when)
    output.parent.mkdir(parents=True, exist_ok=True)

    command = _build_snapshot_command(ffmpeg_path, stored.rtsp_url, output)
    popen = getattr(request.app.state, "snapshot_popen_factory", subprocess.Popen)
    process = popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        returncode = process.wait(timeout=_SNAPSHOT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except OSError:
            pass
        raise HTTPException(status_code=504, detail="snapshot timed out") from None

    if returncode != 0:
        raise HTTPException(
            status_code=502, detail=f"ffmpeg exited {returncode}"
        )

    return RedirectResponse(f"/cameras/{camera_id}", status_code=303)


@router.get("/cameras/{camera_id}/snapshots/{filename}")
def get_snapshot(request: Request, camera_id: int, filename: str):
    if not _SAFE_SNAPSHOT_FILENAME.match(filename):
        raise HTTPException(status_code=400, detail="bad filename")

    stored = request.app.state.cameras.get(camera_id)
    if stored is None:
        raise HTTPException(status_code=404)

    config = request.app.state.config
    cam_dir = config.snapshot_root / safe_camera_dir_name(stored.name)
    path = cam_dir / filename
    if not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="image/jpeg")
