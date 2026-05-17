from __future__ import annotations

from typing import Callable

from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ngc_cams.onvif.discovery import DiscoveredCamera, DiscoveryService
from ngc_cams.discovery_runner import DiscoveryResult, ResolveStreams
from ngc_cams.ui.discovery_worker import DiscoveryWorker


class DiscoveredTab(QWidget):
    def __init__(
        self,
        discovery: DiscoveryService,
        open_add_dialog: Callable[[str | None], None],
        play_discovered: Callable[[DiscoveredCamera], None],
        resolve_streams: ResolveStreams | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._discovery = discovery
        self._open_add_dialog = open_add_dialog
        self._play_discovered = play_discovered
        self._resolve_streams = resolve_streams
        self._rows: list[DiscoveredCamera] = []
        self._worker: DiscoveryWorker | None = None

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["IP", "Manufacturer", "Main RTSP", "ONVIF XAddr"])
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.doubleClicked.connect(self._on_double_click)

        self._discover_btn = QPushButton("Discover")
        self._play_btn = QPushButton("Play")
        self._add_btn = QPushButton("Add selected")
        self._discover_btn.clicked.connect(self._on_discover)
        self._play_btn.clicked.connect(self._on_play_selected)
        self._add_btn.clicked.connect(self._on_add_selected)

        actions = QHBoxLayout()
        actions.addWidget(self._discover_btn)
        actions.addWidget(self._play_btn)
        actions.addWidget(self._add_btn)
        actions.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(self._table)
        layout.addLayout(actions)

    def start_discovery(self) -> None:
        """Public entry point — same as clicking the Discover button. Idempotent while running."""
        self._on_discover()

    def _on_discover(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self._discover_btn.setEnabled(False)
        self._discover_btn.setText("Discovering...")
        worker = DiscoveryWorker(
            self._discovery,
            timeout=5,
            resolve_streams=self._resolve_streams,
            parent=self,
        )
        worker.finished_with_result.connect(self._on_discovery_finished)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(self._clear_worker_ref)
        self._worker = worker
        worker.start()

    def _clear_worker_ref(self) -> None:
        self._worker = None

    def _on_discovery_finished(self, result: DiscoveryResult) -> None:
        self._discover_btn.setEnabled(True)
        self._discover_btn.setText("Discover")
        if result.error is not None:
            QMessageBox.warning(self, "Discovery failed", result.error)
            return
        self._rows = result.cameras
        self._table.setRowCount(len(self._rows))
        for row_index, cam in enumerate(self._rows):
            self._table.setItem(row_index, 0, QTableWidgetItem(cam.address))
            self._table.setItem(row_index, 1, QTableWidgetItem(cam.manufacturer or ""))
            self._table.setItem(row_index, 2, QTableWidgetItem(cam.main_rtsp_url or ""))
            self._table.setItem(row_index, 3, QTableWidgetItem(cam.xaddr))

    def _selected_row(self) -> DiscoveredCamera | None:
        index = self._table.currentRow()
        if index < 0 or index >= len(self._rows):
            return None
        return self._rows[index]

    def _on_add_selected(self) -> None:
        cam = self._selected_row()
        if cam is None:
            QMessageBox.information(self, "No selection", "Select a discovered camera first.")
            return
        self._open_add_dialog(cam.address)

    def _on_play_selected(self) -> None:
        cam = self._selected_row()
        if cam is None:
            QMessageBox.information(self, "No selection", "Select a discovered camera first.")
            return
        if not cam.main_rtsp_url:
            QMessageBox.information(
                self,
                "RTSP URL not resolved",
                "Could not auto-resolve the RTSP URL for this device — it likely requires "
                "credentials. Use 'Add selected' to enter them and save the camera.",
            )
            return
        self._play_discovered(cam)

    def _on_double_click(self) -> None:
        self._on_play_selected()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.stop_worker()
        super().closeEvent(event)

    def stop_worker(self) -> None:
        """Stop a running discovery worker, waiting up to 2 s. Safe to call when no worker is active.

        Intended to be invoked from ``MainWindow.closeEvent`` so the app exits cleanly
        even if a discovery is in flight. ``QThread.quit()`` is a no-op here because the
        worker has no event loop; ``wait()`` blocks until ``run()`` returns on its own
        (WS-Discovery times out within its configured window).
        """
        worker = self._worker
        if worker is None:
            return
        if worker.isRunning():
            worker.quit()
            worker.wait(2000)
