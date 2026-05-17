from __future__ import annotations

import sqlite3

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ngc_cams.cameras import CameraRepository
from ngc_cams.models import StoredCamera
from ngc_cams.ui.camera_dialog import CameraDialog
from ngc_cams.ui.camera_form import camera_id_for_row


class CamerasTab(QWidget):
    camera_selected = pyqtSignal(object)  # StoredCamera or None

    def __init__(self, repository: CameraRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._repository = repository
        self._rows: list[StoredCamera] = []

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Name", "Record", "PTZ"])
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.itemSelectionChanged.connect(self._emit_selection)

        add_btn = QPushButton("Add")
        edit_btn = QPushButton("Edit")
        delete_btn = QPushButton("Delete")
        add_btn.clicked.connect(self._on_add)
        edit_btn.clicked.connect(self._on_edit)
        delete_btn.clicked.connect(self._on_delete)

        actions = QHBoxLayout()
        actions.addWidget(add_btn)
        actions.addWidget(edit_btn)
        actions.addWidget(delete_btn)
        actions.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(self._table)
        layout.addLayout(actions)

        self.refresh()

    def open_add_dialog(self, prefill_ip: str | None = None) -> None:
        dialog = CameraDialog(self, prefill_ip=prefill_ip)
        if dialog.exec() == CameraDialog.DialogCode.Accepted:
            camera = dialog.camera()
            if camera is None:
                return
            try:
                self._repository.add(camera)
            except sqlite3.Error as exc:
                QMessageBox.critical(self, "Database error", str(exc))
                return
            self.refresh()

    def refresh(self) -> None:
        self._rows = self._repository.list()
        self._table.setRowCount(len(self._rows))
        for row_index, camera in enumerate(self._rows):
            self._table.setItem(row_index, 0, QTableWidgetItem(camera.name))
            self._table.setItem(row_index, 1, QTableWidgetItem(camera.record_mode.value))
            self._table.setItem(row_index, 2, QTableWidgetItem("yes" if camera.ptz_enabled else ""))

    def _selected_camera_id(self) -> int | None:
        return camera_id_for_row(self._rows, self._table.currentRow())

    def _emit_selection(self) -> None:
        index = self._table.currentRow()
        if 0 <= index < len(self._rows):
            self.camera_selected.emit(self._rows[index])
        else:
            self.camera_selected.emit(None)

    def _on_add(self) -> None:
        self.open_add_dialog()

    def _on_edit(self) -> None:
        camera_id = self._selected_camera_id()
        if camera_id is None:
            QMessageBox.information(self, "No selection", "Select a camera to edit.")
            return
        stored = self._repository.get(camera_id)
        if stored is None:
            self.refresh()
            return
        dialog = CameraDialog(self, camera=stored)
        if dialog.exec() == CameraDialog.DialogCode.Accepted:
            camera = dialog.camera()
            if camera is None:
                return
            try:
                self._repository.update(camera_id, camera)
            except KeyError:
                QMessageBox.information(
                    self,
                    "Camera no longer exists",
                    "The camera was removed by another process. Refreshing the list.",
                )
                self.refresh()
                return
            except sqlite3.Error as exc:
                QMessageBox.critical(self, "Database error", str(exc))
                return
            self.refresh()

    def _on_delete(self) -> None:
        camera_id = self._selected_camera_id()
        if camera_id is None:
            QMessageBox.information(self, "No selection", "Select a camera to delete.")
            return
        confirm = QMessageBox.question(
            self,
            "Delete camera",
            "Delete the selected camera? Recording segments referencing it will also be removed.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            self._repository.delete(camera_id)
        except sqlite3.Error as exc:
            QMessageBox.critical(self, "Database error", str(exc))
            return
        self.refresh()
