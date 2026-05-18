from __future__ import annotations

import os
import socket
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from ngc_cams import settings_store


# Fields that the Settings web page is allowed to override. Each entry is
# (field_name, coercer). Anything outside this list is ignored even if the
# JSON has it — keeps the surface explicit.
_EDITABLE_FIELDS: tuple[tuple[str, Any], ...] = (
    ("recording_root", lambda v: Path(v)),
    ("snapshot_root", lambda v: Path(v)),
    ("segment_seconds", lambda v: int(v)),
    ("default_retention_days", lambda v: int(v)),
    ("storage_limit_gb", lambda v: int(v)),
    ("disk_guard_free_gb", lambda v: int(v)),
    ("bind_host", lambda v: str(v).strip()),
    ("bind_port", lambda v: int(v)),
)

EDITABLE_FIELD_NAMES: tuple[str, ...] = tuple(name for name, _ in _EDITABLE_FIELDS)


def _hostname() -> str:
    """Per-PC subdirectory key for shared-NAS storage.

    Multiple SISI-TV machines pointing at the same Z:\\SISI-TV-storage share
    must not write to the same directory. We namespace by Windows
    COMPUTERNAME (falling back to socket.gethostname()) so each machine
    gets its own subtree without any per-PC configuration.
    """
    name = os.environ.get("COMPUTERNAME") or socket.gethostname() or "default"
    # Defensive: refuse path separators that would break the directory layout.
    return name.strip().replace("/", "_").replace("\\", "_") or "default"


def _default_storage_root() -> Path:
    return Path(r"Z:\SISI-TV-storage") / _hostname()


@dataclass(frozen=True)
class AppConfig:
    recording_root: Path = field(default_factory=_default_storage_root)
    snapshot_root: Path = field(default_factory=lambda: _default_storage_root() / "snapshots")
    segment_seconds: int = 600
    retention_days: int = 7
    default_retention_days: int = 7
    storage_limit_gb: int = 20
    disk_guard_free_gb: int = 10
    db_path: Path = field(default_factory=lambda: _default_storage_root() / "ngc-cams.sqlite3")
    bind_host: str = "127.0.0.1"
    bind_port: int = 8000

    @classmethod
    def from_settings(cls, settings: dict[str, Any] | None = None) -> "AppConfig":
        """Build an `AppConfig` whose `EDITABLE_FIELD_NAMES` come from the
        settings dict (or `settings_store.load()` if not passed). Missing keys
        keep their default; coercion errors fall back to the default."""
        if settings is None:
            settings = settings_store.load()
        config = cls()
        overrides: dict[str, Any] = {}
        for name, coerce in _EDITABLE_FIELDS:
            if name not in settings:
                continue
            try:
                overrides[name] = coerce(settings[name])
            except (TypeError, ValueError):
                continue
        return replace(config, **overrides) if overrides else config
