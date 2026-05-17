from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from ngc_cams.ui.discovery_runner import DiscoveryResult, ResolveStreams, run_discovery


class DiscoveryWorker(QThread):
    finished_with_result = pyqtSignal(object)  # DiscoveryResult — opaque to Qt's meta-type system

    def __init__(
        self,
        discovery,
        timeout: int = 5,
        resolve_streams: ResolveStreams | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._discovery = discovery
        self._timeout = timeout
        self._resolve_streams = resolve_streams

    def run(self) -> None:
        result: DiscoveryResult = run_discovery(
            self._discovery,
            self._timeout,
            resolve_streams=self._resolve_streams,
        )
        self.finished_with_result.emit(result)
