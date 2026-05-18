from __future__ import annotations

import io

from ngc_cams_web.live import build_mjpeg_command, iter_mjpeg_multipart


def test_build_mjpeg_command_uses_tcp_rtsp_and_mjpeg_output():
    cmd = build_mjpeg_command("rtsp://1.2.3.4/main", ffmpeg="/usr/bin/ffmpeg")
    assert cmd[0] == "/usr/bin/ffmpeg"
    assert "-rtsp_transport" in cmd
    i = cmd.index("-rtsp_transport")
    assert cmd[i + 1] == "tcp"
    assert "-i" in cmd
    assert cmd[cmd.index("-i") + 1] == "rtsp://1.2.3.4/main"
    assert "-f" in cmd
    assert cmd[cmd.index("-f") + 1] == "mjpeg"
    assert cmd[-1] == "pipe:1"


def test_build_mjpeg_command_defaults_to_bare_ffmpeg():
    cmd = build_mjpeg_command("rtsp://x/main")
    assert cmd[0] == "ffmpeg"


def test_build_mjpeg_command_sets_rtsp_and_read_timeouts():
    # Mirror the recording command's resilience: a stalled RTSP source
    # should cause ffmpeg to exit rather than leave the <img> frozen.
    cmd = build_mjpeg_command("rtsp://1.2.3.4/main")
    assert "-stimeout" in cmd
    assert cmd[cmd.index("-stimeout") + 1] == "5000000"
    assert "-rw_timeout" in cmd
    assert cmd[cmd.index("-rw_timeout") + 1] == "10000000"
    i = cmd.index("-i")
    assert cmd.index("-stimeout") < i
    assert cmd.index("-rw_timeout") < i


def test_iter_mjpeg_multipart_yields_one_frame_per_jpeg():
    SOI = b"\xff\xd8"
    EOI = b"\xff\xd9"
    jpeg_a = SOI + b"AAAA" + EOI
    jpeg_b = SOI + b"BBBB" + EOI
    stream = io.BytesIO(jpeg_a + jpeg_b)

    chunks = list(iter_mjpeg_multipart(stream, boundary=b"frame", read_size=3))

    joined = b"".join(chunks)
    assert joined.count(b"--frame\r\n") == 2
    assert b"Content-Type: image/jpeg" in joined
    assert jpeg_a in joined
    assert jpeg_b in joined


def test_iter_mjpeg_multipart_stops_when_stream_ends_mid_frame():
    SOI = b"\xff\xd8"
    truncated = SOI + b"AAAA"  # no EOI
    stream = io.BytesIO(truncated)
    chunks = list(iter_mjpeg_multipart(stream, boundary=b"frame", read_size=64))
    assert chunks == []
