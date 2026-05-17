from __future__ import annotations

import pytest

from ngc_cams.recording import locator


@pytest.fixture()
def empty_env(monkeypatch, tmp_path):
    # Point env vars at empty tmp_path subdirs so no real install is found.
    base = tmp_path / "empty"
    base.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(base / "Local"))
    monkeypatch.setenv("ProgramFiles", str(base / "Program Files"))
    monkeypatch.setenv("ProgramFiles(x86)", str(base / "Program Files x86"))
    monkeypatch.setenv("ProgramData", str(base / "ProgramData"))
    monkeypatch.setenv("USERPROFILE", str(base / "user"))
    # And neutralise PATH so shutil.which doesn't find anything.
    monkeypatch.setenv("PATH", str(base))
    return base


def test_returns_none_when_nothing_installed(empty_env):
    assert locator.find_ffmpeg_executable() is None


def test_finds_real_path_when_shutil_which_resolves(empty_env, monkeypatch, tmp_path):
    real = tmp_path / "real" / "ffmpeg.exe"
    real.parent.mkdir(parents=True)
    real.write_bytes(b"X" * 4096)
    monkeypatch.setattr(locator.shutil, "which", lambda name: str(real))
    assert locator.find_ffmpeg_executable() == str(real)


def test_skips_zero_byte_app_alias_from_shutil_which(empty_env, monkeypatch, tmp_path):
    alias = tmp_path / "alias" / "ffmpeg.exe"
    alias.parent.mkdir(parents=True)
    alias.write_bytes(b"")  # 0-byte alias-like file
    monkeypatch.setattr(locator.shutil, "which", lambda name: str(alias))
    # No fallback installed either → None
    assert locator.find_ffmpeg_executable() is None


def test_finds_winget_gyan_install_via_glob(empty_env, monkeypatch):
    base = empty_env / "Local" / "Microsoft" / "WinGet" / "Packages"
    bin_dir = base / "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe" / "ffmpeg-8.1.1-full_build" / "bin"
    bin_dir.mkdir(parents=True)
    real = bin_dir / "ffmpeg.exe"
    real.write_bytes(b"X" * 4096)
    monkeypatch.setattr(locator.shutil, "which", lambda name: None)
    found = locator.find_ffmpeg_executable()
    assert found == str(real)


def test_finds_chocolatey_install(empty_env, monkeypatch):
    choco_bin = empty_env / "ProgramData" / "chocolatey" / "bin"
    choco_bin.mkdir(parents=True)
    real = choco_bin / "ffmpeg.exe"
    real.write_bytes(b"X" * 4096)
    monkeypatch.setattr(locator.shutil, "which", lambda name: None)
    assert locator.find_ffmpeg_executable() == str(real)


def test_finds_traditional_program_files_install(empty_env, monkeypatch):
    bin_dir = empty_env / "Program Files" / "ffmpeg" / "bin"
    bin_dir.mkdir(parents=True)
    real = bin_dir / "ffmpeg.exe"
    real.write_bytes(b"X" * 4096)
    monkeypatch.setattr(locator.shutil, "which", lambda name: None)
    assert locator.find_ffmpeg_executable() == str(real)


def test_is_real_executable_rejects_empty_file(tmp_path):
    f = tmp_path / "f.exe"
    f.write_bytes(b"")
    assert locator._is_real_executable(f) is False


def test_is_real_executable_rejects_missing(tmp_path):
    assert locator._is_real_executable(tmp_path / "missing.exe") is False
