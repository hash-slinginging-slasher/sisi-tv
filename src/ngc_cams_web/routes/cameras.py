from __future__ import annotations

import shutil
from dataclasses import replace
from datetime import datetime

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ngc_cams.models import Camera, RecordMode
from ngc_cams.recording.paths import safe_camera_dir_name

router = APIRouter()

DASHBOARD_FEED_LIMIT = 3
SNAPSHOT_GALLERY_LIMIT = 12


def _free_storage_str(path) -> str:
    try:
        path.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(path)
    except OSError:
        return "—"
    gb = usage.free / (1024 ** 3)
    if gb >= 1024:
        return f"{gb / 1024:.1f} TB"
    return f"{gb:.0f} GB"


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    cameras_repo = request.app.state.cameras
    cameras = cameras_repo.list()
    segments_repo = getattr(request.app.state, "segments", None)
    config = request.app.state.config
    recent_segments: list = []
    if segments_repo is not None:
        for cam in cameras:
            recent_segments.extend(segments_repo.list_by_camera(cam.id))
        recent_segments.sort(key=lambda s: s.started_at, reverse=True)
        recent_segments = recent_segments[:6]
    cam_lookup = {c.id: c for c in cameras}
    active_alerts = sum(1 for c in cameras if c.record_mode != RecordMode.OFF)
    stats = {
        "total_cameras": len(cameras),
        "active_alerts": active_alerts,
        "uptime": "99.8%",
        "free_storage": _free_storage_str(config.recording_root),
    }
    templates = request.app.state.templates
    feed_cameras = cameras[:DASHBOARD_FEED_LIMIT]
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "active_nav": "dashboard",
            "cameras": cameras,
            "feed_cameras": feed_cameras,
            "feed_seeds": {cam.id: feed_seed(cam.id) for cam in feed_cameras},
            "stats": stats,
            "recent_segments": recent_segments,
            "cam_lookup": cam_lookup,
            "now": datetime.now(),
        },
    )


def _ordered_cameras(cameras_list, saved_order):
    """Order `cameras_list` by `saved_order` (list of camera ids), appending any
    cameras not in the saved order at the end. Unknown ids in saved_order are
    skipped (camera was deleted)."""
    by_id = {c.id: c for c in cameras_list}
    seen: set[int] = set()
    ordered = []
    for cid in saved_order:
        cam = by_id.get(cid)
        if cam is not None and cid not in seen:
            ordered.append(cam)
            seen.add(cid)
    for cam in cameras_list:
        if cam.id not in seen:
            ordered.append(cam)
    return ordered


FEED_FILTERS = ("normal", "fnaf", "static", "vhs", "mgs")


def _coerce_feed_filter(value) -> str:
    if isinstance(value, str) and value in FEED_FILTERS:
        return value
    return "normal"


def feed_seed(camera_id: int) -> int:
    """Per-camera Fibonacci seed used to desync filter animations.

    Returns fib(camera_id + 2) so cams 1 and 2 don't both get 1 (which would
    leave them in lockstep). The golden-ratio growth between adjacent fib
    numbers means no two cameras land in resonance with the same animation
    period, which is the whole point of the seed.
    """
    if camera_id < 1:
        return 1
    a, b = 1, 1
    for _ in range(camera_id + 1):
        a, b = b, a + b
    return a


@router.get("/grid", response_class=HTMLResponse)
def grid(request: Request):
    from ngc_cams import settings_store

    cameras = request.app.state.cameras.list()
    stored = settings_store.load()
    raw_order = stored.get("grid_order") or []
    order = [int(x) for x in raw_order if isinstance(x, int) or str(x).isdigit()]
    # Default 2 columns -- matches what most users actually want for a
    # multi-camera wall. The user can pick Auto or 1/3/4/5/6 in the dropdown.
    columns_raw = stored.get("grid_columns", 2)
    if isinstance(columns_raw, int) and 1 <= columns_raw <= 8:
        columns = columns_raw
    elif isinstance(columns_raw, str) and columns_raw.isdigit() and 1 <= int(columns_raw) <= 8:
        columns = int(columns_raw)
    elif columns_raw == "auto":
        columns = "auto"
    else:
        columns = 2
    feed_filter = _coerce_feed_filter(stored.get("feed_filter"))
    visible = _ordered_cameras(cameras, order)
    feed_seeds = {cam.id: feed_seed(cam.id) for cam in visible}
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "grid.html",
        {
            "active_nav": "matrix",
            "visible": visible,
            "columns": columns,
            "feed_filter": feed_filter,
            "feed_filters": FEED_FILTERS,
            "feed_seeds": feed_seeds,
        },
    )


@router.post("/grid/layout")
async def save_grid_layout(request: Request):
    from ngc_cams import settings_store

    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="expected JSON object")
    update: dict = {}
    raw_order = body.get("order")
    if isinstance(raw_order, list):
        update["grid_order"] = [int(x) for x in raw_order if isinstance(x, int) or str(x).isdigit()]
    raw_cols = body.get("columns")
    if raw_cols == "auto":
        update["grid_columns"] = "auto"
    elif isinstance(raw_cols, int) and 1 <= raw_cols <= 8:
        update["grid_columns"] = raw_cols
    elif isinstance(raw_cols, str) and raw_cols.isdigit() and 1 <= int(raw_cols) <= 8:
        update["grid_columns"] = int(raw_cols)
    raw_filter = body.get("feed_filter")
    if isinstance(raw_filter, str) and raw_filter in FEED_FILTERS:
        update["feed_filter"] = raw_filter
    if not update:
        raise HTTPException(status_code=400, detail="nothing to save")
    existing = settings_store.load()
    existing.update(update)
    settings_store.save(existing)
    return {"status": "ok", **update}


@router.post("/cameras/add")
def add_camera(
    request: Request,
    name: str = Form(...),
    rtsp_url: str = Form(...),
    ptz_enabled: str | None = Form(default=None),
    record_enabled: str | None = Form(default=None),
):
    record_mode = RecordMode.VIDEO_ONLY if record_enabled else RecordMode.OFF
    request.app.state.cameras.add(
        Camera(
            name=name,
            rtsp_url=rtsp_url,
            ptz_enabled=bool(ptz_enabled),
            record_mode=record_mode,
        )
    )
    manager = request.app.state.recording_manager
    if manager is not None and record_enabled:
        manager.apply_modes()
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


@router.get("/cameras/{camera_id}/edit", response_class=HTMLResponse)
def edit_camera_form(request: Request, camera_id: int):
    stored = request.app.state.cameras.get(camera_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "camera_edit.html",
        {
            "active_nav": "settings",
            "camera": stored,
            "modes": list(RecordMode),
        },
    )


@router.post("/cameras/{camera_id}/edit")
def edit_camera(
    request: Request,
    camera_id: int,
    name: str = Form(...),
    rtsp_url: str = Form(...),
    record_mode: str = Form(default=""),
    ptz_enabled: str | None = Form(default=None),
    display_rotation: str = Form(default="0"),
):
    repo = request.app.state.cameras
    stored = repo.get(camera_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    try:
        next_mode = RecordMode(record_mode) if record_mode else stored.record_mode
    except ValueError:
        next_mode = stored.record_mode
    try:
        rotation = int(display_rotation)
        if rotation not in (0, 90, 180, 270):
            rotation = stored.display_rotation
    except ValueError:
        rotation = stored.display_rotation
    rtsp_changed = stored.rtsp_url != rtsp_url.strip()
    updated = replace(
        stored,
        name=name.strip(),
        rtsp_url=rtsp_url.strip(),
        ptz_enabled=bool(ptz_enabled),
        record_mode=next_mode,
        display_rotation=rotation,
    )
    repo.update(camera_id, updated)
    manager = request.app.state.recording_manager
    if manager is not None:
        # If the camera was recording and the RTSP URL changed, ffmpeg
        # is still tied to the old URL. Stop it explicitly so apply_modes
        # can spawn a fresh ffmpeg against the new URL.
        if rtsp_changed and manager.is_recording(camera_id):
            manager.stop(camera_id)
        manager.apply_modes()
    return RedirectResponse("/settings", status_code=303)


@router.get("/cameras/{camera_id}", response_class=HTMLResponse)
def camera_detail(request: Request, camera_id: int):
    from ngc_cams import settings_store

    stored = request.app.state.cameras.get(camera_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    config = request.app.state.config
    cam_dir = config.snapshot_root / safe_camera_dir_name(stored.name)
    snapshots: list[str] = []
    if cam_dir.is_dir():
        try:
            files = sorted(
                cam_dir.glob("*.jpg"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            files = []
        snapshots = [f.name for f in files[:SNAPSHOT_GALLERY_LIMIT]]
    feed_filter = _coerce_feed_filter(settings_store.load().get("feed_filter"))
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "camera_detail.html",
        {
            "camera": stored,
            "snapshots": snapshots,
            "feed_filter": feed_filter,
            "feed_seed": feed_seed(stored.id),
        },
    )
