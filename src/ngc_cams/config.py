from __future__ import annotations

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
    ("disk_guard_free_gb", lambda v: int(v)),
)

EDITABLE_FIELD_NAMES: tuple[str, ...] = tuple(name for name, _ in _EDITABLE_FIELDS)


@dataclass(frozen=True)
class AppConfig:
    recording_root: Path = Path(r"D:\ngc-cams-recordings")
    snapshot_root: Path = Path(r"D:\ngc-cams-snapshots")
    segment_seconds: int = 600
    retention_days: int = 7
    disk_guard_free_gb: int = 10
    db_path: Path = field(
        default_factory=lambda: Path(r"D:\ngc-cams-recordings\ngc-cams.sqlite3")
    )

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
