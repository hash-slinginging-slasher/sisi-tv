from __future__ import annotations

import os
from pathlib import Path

DEFAULT_MAX_BYTES = 5 * 1024 * 1024


def rotate_log_file(log_path: Path, max_bytes: int = DEFAULT_MAX_BYTES) -> bool:
    """Rotate ``log_path`` to ``<log>.old`` if it exceeds ``max_bytes``.

    Returns True when rotation happened. A single rotation step is enough for
    a desktop session — call this once at app start so the stderr capture file
    does not grow unbounded across runs.
    """
    try:
        if not log_path.exists() or log_path.stat().st_size <= max_bytes:
            return False
    except OSError:
        return False
    backup = log_path.with_suffix(log_path.suffix + ".old")
    if backup.exists():
        backup.unlink()
    log_path.rename(backup)
    return True


def redirect_fd_to_file(source_fd: int, log_path: Path) -> int:
    """Dup ``log_path`` (opened append+create) onto ``source_fd``.

    Returns the original fd backing ``source_fd`` so the caller can pass it to
    :func:`restore_fd`. Used to capture libvlc/live555 writes to fd 2, which
    bypass libvlc ``--quiet`` and Python's :data:`sys.stderr` replacement.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    saved = os.dup(source_fd)
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    # Windows: native libvlc writes raw bytes; avoid CRLF translation by opening binary.
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    log_fd = os.open(log_path, flags)
    try:
        os.dup2(log_fd, source_fd)
    finally:
        os.close(log_fd)
    return saved


def restore_fd(source_fd: int, saved_fd: int) -> None:
    """Restore ``source_fd`` from ``saved_fd`` and close ``saved_fd``."""
    os.dup2(saved_fd, source_fd)
    os.close(saved_fd)
