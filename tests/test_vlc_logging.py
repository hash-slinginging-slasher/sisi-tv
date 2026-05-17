from __future__ import annotations

import os

from ngc_cams.vlc_logging import (
    redirect_fd_to_file,
    restore_fd,
    rotate_log_file,
)


def test_rotate_log_file_skips_nonexistent(tmp_path):
    log_path = tmp_path / "missing.log"
    assert rotate_log_file(log_path, max_bytes=10) is False
    assert not log_path.exists()


def test_rotate_log_file_skips_small_file(tmp_path):
    log_path = tmp_path / "small.log"
    log_path.write_bytes(b"hi")
    assert rotate_log_file(log_path, max_bytes=100) is False
    assert log_path.exists()
    assert not (tmp_path / "small.log.old").exists()


def test_rotate_log_file_renames_large_file(tmp_path):
    log_path = tmp_path / "big.log"
    log_path.write_bytes(b"x" * 200)
    assert rotate_log_file(log_path, max_bytes=100) is True
    assert not log_path.exists()
    assert (tmp_path / "big.log.old").read_bytes() == b"x" * 200


def test_rotate_log_file_replaces_existing_backup(tmp_path):
    log_path = tmp_path / "big.log"
    log_path.write_bytes(b"new" * 100)
    backup = tmp_path / "big.log.old"
    backup.write_bytes(b"stale")
    assert rotate_log_file(log_path, max_bytes=10) is True
    assert backup.read_bytes() == b"new" * 100


def test_redirect_and_restore_round_trip(tmp_path):
    log_path = tmp_path / "logs" / "captured.log"
    # Duplicate stdout to a private fd we can safely redirect without affecting pytest's streams.
    test_fd = os.dup(1)
    try:
        saved = redirect_fd_to_file(test_fd, log_path)
        try:
            os.write(test_fd, b"hello live555\n")
        finally:
            restore_fd(test_fd, saved)
        assert log_path.read_bytes() == b"hello live555\n"
    finally:
        os.close(test_fd)


def test_redirect_creates_parent_directories(tmp_path):
    log_path = tmp_path / "nested" / "dirs" / "log.txt"
    test_fd = os.dup(1)
    try:
        saved = redirect_fd_to_file(test_fd, log_path)
        restore_fd(test_fd, saved)
    finally:
        os.close(test_fd)
    assert log_path.exists()
