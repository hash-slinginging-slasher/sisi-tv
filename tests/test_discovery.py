from __future__ import annotations

from ngc_cams.onvif.discovery import DiscoveryService


class FakeService:
    def __init__(self, xaddrs, scopes):
        self._xaddrs = xaddrs
        self._scopes = scopes

    def getXAddrs(self):
        return self._xaddrs

    def getScopes(self):
        return self._scopes


class FakeDiscovery:
    def __init__(self):
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def searchServices(self, timeout=3):
        assert timeout == 2
        return [
            FakeService(
                ["http://192.168.1.18/onvif/device_service"],
                ["onvif://www.onvif.org/name/Front_Gate"],
            ),
            FakeService(["http://192.168.1.50/other"], ["printer"]),
        ]


def test_discovery_parses_onvif_xaddr_and_scope_label():
    cameras = DiscoveryService(FakeDiscovery).discover(timeout=2)

    assert len(cameras) == 1
    assert cameras[0].address == "192.168.1.18"
    assert cameras[0].manufacturer == "Front Gate"
