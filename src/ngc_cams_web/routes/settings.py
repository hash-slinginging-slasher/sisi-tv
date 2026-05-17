from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ngc_cams import settings_store
from ngc_cams.config import EDITABLE_FIELD_NAMES

router = APIRouter()

_FIELD_LABELS: dict[str, str] = {
    "recording_root": "Recording root (folder for .mp4 segments)",
    "snapshot_root": "Snapshot root (folder for .jpg snapshots)",
    "segment_seconds": "Segment length (seconds)",
    "default_retention_days": "Recording retention (days) — older segments are pruned",
    "storage_limit_gb": "Storage cap (GB) — oldest segments deleted past this size",
    "disk_guard_free_gb": "Pause recording when free disk drops below (GB)",
    "bind_host": "Bind host (127.0.0.1 = local only, 0.0.0.0 = LAN-wide)",
    "bind_port": "Bind port",
}


def _live_values(request: Request) -> dict[str, str]:
    """What the running process is using right now (only changes on restart)."""
    config = request.app.state.config
    return {name: str(getattr(config, name)) for name in EDITABLE_FIELD_NAMES}


def _form_values(request: Request) -> dict[str, str]:
    """What goes into the form inputs: persisted overrides first, falling back
    to the live config for fields the user hasn't customized yet. After a Save
    the user sees their edit immediately even though it won't take effect until
    the app restarts."""
    stored = settings_store.load()
    live = _live_values(request)
    return {name: str(stored.get(name, live[name])) for name in EDITABLE_FIELD_NAMES}


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, saved: int = 0):
    templates = request.app.state.templates
    cameras = request.app.state.cameras.list()
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "active_nav": "settings",
            "values": _form_values(request),
            "live_values": _live_values(request),
            "labels": _FIELD_LABELS,
            "fields": EDITABLE_FIELD_NAMES,
            "saved": bool(saved),
            "stored": settings_store.load(),
            "stored_path": settings_store.default_settings_path(),
            "cameras": cameras,
        },
    )


@router.post("/settings")
async def save_settings(request: Request):
    form = await request.form()
    data: dict[str, Any] = {}
    int_fields = {
        "segment_seconds",
        "default_retention_days",
        "storage_limit_gb",
        "disk_guard_free_gb",
        "bind_port",
    }
    for name in EDITABLE_FIELD_NAMES:
        raw = form.get(name)
        if raw is None:
            continue
        raw = str(raw).strip()
        if raw == "":
            continue
        if name in int_fields:
            try:
                data[name] = int(raw)
            except ValueError:
                # Skip invalid integers — current value stays.
                continue
        else:
            data[name] = raw
    existing = settings_store.load()
    existing.update(data)
    settings_store.save(existing)
    return RedirectResponse("/settings?saved=1", status_code=303)
