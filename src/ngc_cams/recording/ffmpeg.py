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
        "-reconnect",
        "1",
        "-reconnect_streamed",
        "1",
        "-reconnect_delay_max",
        "5",
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
