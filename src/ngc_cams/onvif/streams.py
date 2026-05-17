from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StreamUris:
    main: str | None
    sub: str | None = None


def get_stream_uris(host: str, username: str = "", password: str = "", port: int = 80) -> StreamUris:
    from onvif import ONVIFCamera

    camera = ONVIFCamera(host, port, username, password)
    media = camera.create_media_service()
    profiles = media.GetProfiles()
    uris: list[str] = []

    for profile in profiles[:2]:
        response = media.GetStreamUri(
            {
                "StreamSetup": {
                    "Stream": "RTP-Unicast",
                    "Transport": {"Protocol": "RTSP"},
                },
                "ProfileToken": profile.token,
            }
        )
        uri = getattr(response, "Uri", None)
        if uri:
            uris.append(uri)

    main = uris[0] if uris else None
    sub = uris[1] if len(uris) > 1 else None
    return StreamUris(main=main, sub=sub)
