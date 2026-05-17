from __future__ import annotations

import os
import shutil
from pathlib import Path


def find_ffmpeg_executable() -> str | None:
    """Locate a real ``ffmpeg.exe`` on Windows.

    ``shutil.which`` finds ffmpeg if it's on PATH as a normal file, but winget
    installs it as a 0-byte App Execution Alias reparse point that the Windows
    shell resolves transparently — ``subprocess.Popen`` doesn't follow it and
    fails with ``[WinError 2]``. So we scan the winget Packages directory and
    a few other well-known install locations for a real binary.

    Returns an absolute path, or ``None`` if nothing usable is found.
    """
    candidate = shutil.which("ffmpeg")
    if candidate and _is_real_executable(Path(candidate)):
        return candidate

    for path in _candidate_paths():
        if _is_real_executable(path):
            return str(path)

    for pattern_root, pattern in _glob_candidates():
        if not pattern_root.exists():
            continue
        for match in pattern_root.glob(pattern):
            if _is_real_executable(match):
                return str(match)

    return None


def _is_real_executable(path: Path) -> bool:
    """True iff ``path`` is a real (non-empty) ffmpeg binary, not an app alias."""
    try:
        if not path.is_file():
            return False
        return path.stat().st_size > 1024
    except OSError:
        return False


def _candidate_paths() -> list[Path]:
    paths: list[Path] = []
    local_app = os.environ.get("LOCALAPPDATA")
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    program_data = os.environ.get("ProgramData", r"C:\ProgramData")
    user_profile = os.environ.get("USERPROFILE", "")

    paths.append(Path(program_files) / "ffmpeg" / "bin" / "ffmpeg.exe")
    paths.append(Path(program_files_x86) / "ffmpeg" / "bin" / "ffmpeg.exe")
    paths.append(Path(program_data) / "chocolatey" / "bin" / "ffmpeg.exe")
    paths.append(Path(r"C:\ffmpeg\bin\ffmpeg.exe"))
    if user_profile:
        paths.append(Path(user_profile) / "scoop" / "apps" / "ffmpeg" / "current" / "bin" / "ffmpeg.exe")
    if local_app:
        paths.append(Path(local_app) / "Programs" / "ffmpeg" / "bin" / "ffmpeg.exe")
    return paths


def _glob_candidates() -> list[tuple[Path, str]]:
    """(root, glob) pairs for installs that nest under a versioned directory."""
    pairs: list[tuple[Path, str]] = []
    local_app = os.environ.get("LOCALAPPDATA")
    if local_app:
        # winget's Gyan.FFmpeg layout: <Packages>/Gyan.FFmpeg_*/ffmpeg-<version>-full_build/bin/ffmpeg.exe
        pairs.append(
            (
                Path(local_app) / "Microsoft" / "WinGet" / "Packages",
                "Gyan.FFmpeg_*/ffmpeg-*/bin/ffmpeg.exe",
            )
        )
    return pairs
