"""User-editable settings persisted as JSON.

`AppConfig` defaults are baked into the code; this module is the override
layer the web Settings page writes to. The file lives at
``~/.ngc-cams/settings.json`` so changing ``recording_root`` itself never
moves the settings file out from under us.

Schema is intentionally just a dict[str, JSON]. Unknown keys are preserved
on round-trip so older versions don't strip newer settings.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def default_settings_path() -> Path:
    return Path.home() / ".ngc-cams" / "settings.json"


def load(path: Path | None = None) -> dict[str, Any]:
    target = path or default_settings_path()
    try:
        with target.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def save(data: dict[str, Any], path: Path | None = None) -> None:
    target = path or default_settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(target)
