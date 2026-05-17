from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


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
    vlc_log_path: Path = field(
        default_factory=lambda: Path(r"D:\ngc-cams-recordings\logs\vlc-stderr.log")
    )
