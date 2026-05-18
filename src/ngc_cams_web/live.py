from __future__ import annotations

from typing import IO, Iterator

_SOI = b"\xff\xd8"
_EOI = b"\xff\xd9"


def build_mjpeg_command(rtsp_url: str, ffmpeg: str = "ffmpeg") -> list[str]:
    """Argv for ffmpeg -> stdout MJPEG transcode.

    `-q:v 5` is a reasonable browser-friendly quality; `-r 5` caps FPS to keep
    one process per viewer affordable. The route handler pipes stdout into
    :func:`iter_mjpeg_multipart`.
    """
    return [
        ffmpeg,
        "-loglevel",
        "error",
        "-rtsp_transport",
        "tcp",
        # Timeouts match the recording command (see comment in
        # ngc_cams.recording.ffmpeg.build_segment_command). When the
        # source RTSP stalls, ffmpeg exits cleanly rather than blocking
        # the browser <img> tag forever waiting on the next JPEG frame.
        "-stimeout",
        "5000000",
        "-rw_timeout",
        "10000000",
        "-i",
        rtsp_url,
        "-f",
        "mjpeg",
        "-q:v",
        "5",
        "-r",
        "5",
        "-an",
        "pipe:1",
    ]


def iter_mjpeg_multipart(
    stream: IO[bytes],
    boundary: bytes = b"frame",
    read_size: int = 4096,
) -> Iterator[bytes]:
    """Read concatenated JPEGs from ``stream``, yield multipart frame chunks.

    Each yielded chunk is a complete frame ready to write into a
    ``multipart/x-mixed-replace`` response: boundary line, JPEG content-type,
    blank line, the JPEG bytes, trailing CRLF.

    Stops when the stream returns ``b""`` (EOF) or when no more complete frames
    can be parsed.
    """
    buf = b""
    while True:
        chunk = stream.read(read_size)
        if not chunk:
            return
        buf += chunk
        while True:
            soi = buf.find(_SOI)
            if soi == -1:
                # Keep last byte in case it's the first half of an SOI marker.
                buf = buf[-1:] if buf else b""
                break
            eoi = buf.find(_EOI, soi + 2)
            if eoi == -1:
                buf = buf[soi:]
                break
            jpeg = buf[soi : eoi + 2]
            buf = buf[eoi + 2 :]
            yield (
                b"--" + boundary + b"\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(jpeg)).encode("ascii") + b"\r\n\r\n"
                + jpeg + b"\r\n"
            )
