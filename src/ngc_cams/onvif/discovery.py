from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import unquote, urlparse


@dataclass(frozen=True)
class DiscoveredCamera:
    address: str
    xaddr: str
    manufacturer: str | None = None
    main_rtsp_url: str | None = None
    sub_rtsp_url: str | None = None


class DiscoveryService:
    def __init__(self, wsdiscovery_class=None) -> None:
        if wsdiscovery_class is None:
            from wsdiscovery.discovery import ThreadedWSDiscovery

            wsdiscovery_class = ThreadedWSDiscovery
        self._wsdiscovery_class = wsdiscovery_class

    def discover(self, timeout: int = 5) -> list[DiscoveredCamera]:
        discovery = self._wsdiscovery_class()
        discovery.start()
        try:
            services = discovery.searchServices(timeout=timeout)
        finally:
            discovery.stop()

        cameras: list[DiscoveredCamera] = []
        seen: set[str] = set()
        for service in services:
            for xaddr in service.getXAddrs():
                if not _looks_like_onvif_service(xaddr, service.getScopes()):
                    continue
                address = _address_from_xaddr(xaddr)
                if address in seen:
                    continue
                seen.add(address)
                cameras.append(
                    DiscoveredCamera(
                        address=address,
                        xaddr=xaddr,
                        manufacturer=_label_from_scopes(service.getScopes()),
                    )
                )
        return cameras


def discover(timeout: int = 5) -> list[DiscoveredCamera]:
    return DiscoveryService().discover(timeout=timeout)


def _looks_like_onvif_service(xaddr: str, scopes: list[str]) -> bool:
    haystack = " ".join([xaddr, *map(str, scopes)]).lower()
    return "onvif" in haystack


def _address_from_xaddr(xaddr: str) -> str:
    parsed = urlparse(xaddr)
    return parsed.hostname or xaddr


def _label_from_scopes(scopes: list[str]) -> str | None:
    for scope in scopes:
        parsed = urlparse(str(scope))
        if parsed.scheme != "onvif":
            continue
        parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
        if len(parts) >= 2 and parts[0] in {"name", "hardware"}:
            return parts[1].replace("_", " ")
    return None
