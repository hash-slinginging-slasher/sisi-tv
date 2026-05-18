from __future__ import annotations

from pathlib import Path

import pytest

from ngc_cams.models import RecordMode
from ngc_cams.recording.ffmpeg import build_segment_command


def test_video_only_command_drops_audio():
    command = build_segment_command(
        "rtsp://192.168.1.18/main",
        Path(r"D:\recordings\front\%Y-%m-%d_%H-%M-%S.mp4"),
        RecordMode.VIDEO_ONLY,
    )

    assert "-an" in command
    assert "0:v" in command
    assert "-rtsp_transport" in command
    # No `-reconnect` flags: ffmpeg 8+ moved them to HTTP-only and the
    # recording manager handles process restart instead.
    assert "-reconnect" not in command


def test_video_audio_command_uses_optional_audio_map():
    command = build_segment_command(
        "rtsp://192.168.1.18/main",
        Path(r"D:\recordings\front\%Y-%m-%d_%H-%M-%S.mp4"),
        RecordMode.VIDEO_AUDIO,
    )

    assert "0:a?" in command
    assert "-an" not in command


def test_off_mode_does_not_build_command():
    with pytest.raises(ValueError):
        build_segment_command("rtsp://camera/main", Path("out.mp4"), RecordMode.OFF)


def test_segment_command_emits_segment_list_when_provided():
    command = build_segment_command(
        "rtsp://camera/main",
        Path(r"D:\rec\front\%Y-%m-%d_%H-%M-%S.mp4"),
        RecordMode.VIDEO_ONLY,
        segment_list=Path(r"D:\rec\front\segments.csv"),
    )
    assert "-segment_list" in command
    assert r"D:\rec\front\segments.csv" in command
    assert "-segment_list_type" in command
    assert "csv" in command


def test_segment_command_omits_segment_list_when_none():
    command = build_segment_command(
        "rtsp://camera/main",
        Path("out.mp4"),
        RecordMode.VIDEO_ONLY,
    )
    assert "-segment_list" not in command
    assert "-segment_list_type" not in command


def test_segment_command_emits_faststart_movflag():
    # Each segment is an MP4 with moov at the front so it is playable in browsers
    # and on phones without re-muxing. Free with -c copy.
    command = build_segment_command(
        "rtsp://camera/main",
        Path("out.mp4"),
        RecordMode.VIDEO_ONLY,
    )
    assert "-segment_format_options" in command
    idx = command.index("-segment_format_options")
    assert command[idx + 1] == "movflags=+faststart"


def test_segment_command_uses_custom_ffmpeg_path():
    command = build_segment_command(
        "rtsp://camera/main",
        Path("out.mp4"),
        RecordMode.VIDEO_ONLY,
        ffmpeg=r"C:\tools\ffmpeg\bin\ffmpeg.exe",
    )
    assert command[0] == r"C:\tools\ffmpeg\bin\ffmpeg.exe"


def test_segment_command_sets_rtsp_and_read_timeouts():
    # Without -stimeout and -rw_timeout, ffmpeg hangs indefinitely when the
    # camera/NAS stalls and the segment file stops growing -- which is what
    # the user reported as "recordings are stuck".
    command = build_segment_command(
        "rtsp://camera/main",
        Path("out.mp4"),
        RecordMode.VIDEO_ONLY,
    )
    assert "-stimeout" in command
    assert command[command.index("-stimeout") + 1] == "5000000"
    assert "-rw_timeout" in command
    assert command[command.index("-rw_timeout") + 1] == "10000000"
    # Both must come BEFORE the input URL so ffmpeg applies them to the input.
    i = command.index("-i")
    assert command.index("-stimeout") < i
    assert command.index("-rw_timeout") < i
