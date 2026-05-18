from __future__ import annotations

from pathlib import Path

from ngc_cams.models import RecordMode


def build_segment_command(
    rtsp_url: str,
    output_pattern: Path,
    mode: RecordMode,
    segment_seconds: int = 600,
    segment_list: Path | None = None,
    ffmpeg: str = "ffmpeg",
) -> list[str]:
    if mode == RecordMode.OFF:
        raise ValueError("Cannot build a recording command when recording is off.")

    audio_args = ["-an"] if mode == RecordMode.VIDEO_ONLY else ["-map", "0:a?"]
    segment_args = [
        "-f",
        "segment",
        "-segment_time",
        str(segment_seconds),
        "-reset_timestamps",
        "1",
        # ffmpeg 8+ requires -strftime 1 to interpret %Y / %m / %d / %H etc
        # in the output filename template. Older versions auto-detected.
        "-strftime",
        "1",
        # Per-segment MP4 muxer options: write moov atom at the front so each
        # segment is browser/mobile-playable without re-muxing.
        "-segment_format_options",
        "movflags=+faststart",
    ]
    if segment_list is not None:
        segment_args.extend(
            ["-segment_list", str(segment_list), "-segment_list_type", "csv"]
        )

    return [
        ffmpeg,
        "-rtsp_transport",
        "tcp",
        # Without these timeouts, ffmpeg blocks indefinitely when the RTSP
        # stream stalls (camera firmware hiccup, router blip, NAS SMB hang
        # back-pressuring the muxer). The poll() restart loop only sees
        # crashed processes, so a hung-but-alive ffmpeg writes 0 bytes for
        # hours and the segment file just sits there. With these, ffmpeg
        # exits on the timeout, RecordingManager's existing crash-restart
        # logic respawns it. The stall-watchdog (RecordingManager._check_stall)
        # is the second line of defense for cases where ffmpeg is still
        # producing data but the output is stuck.
        # ffmpeg 8 renamed -stimeout -> -timeout for RTSP; -rw_timeout is only
        # valid on HTTP-style protocols and ffmpeg 8 rejects it outright on an
        # RTSP input. One -timeout covers both connect and read for RTSP.
        "-timeout",
        "10000000",  # 10s socket timeout (microseconds)
        "-i",
        rtsp_url,
        "-c",
        "copy",
        "-map",
        "0:v",
        *audio_args,
        *segment_args,
        str(output_pattern),
    ]
