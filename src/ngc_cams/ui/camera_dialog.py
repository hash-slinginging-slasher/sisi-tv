from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ngc_cams.models import Camera, RecordMode, StoredCamera
from ngc_cams.ui.camera_form import CameraFormError, build_camera_from_fields


class CameraDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        camera: StoredCamera | None = None,
        prefill_ip: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit camera" if camera else "Add camera")
        self._result_camera: Camera | None = None

        self._name = QLineEdit()
        self._rtsp_url = QLineEdit()
        self._sub_stream_url = QLineEdit()
        self._username = QLineEdit()
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._ptz = QCheckBox("PTZ enabled")
        self._record_mode = QComboBox()
        for mode in RecordMode:
            self._record_mode.addItem(mode.value, mode)
        self._retention = QSpinBox()
        self._retention.setRange(0, 365)
        self._retention.setValue(7)
        self._error_label = QLabel()
        self._error_label.setStyleSheet("color: #c33;")
        self._error_label.hide()

        if camera is not None:
            self._name.setText(camera.name)
            self._rtsp_url.setText(camera.rtsp_url)
            self._sub_stream_url.setText(camera.sub_stream_url or "")
            self._username.setText(camera.username or "")
            self._password.setText(camera.password or "")
            self._ptz.setChecked(camera.ptz_enabled)
            self._record_mode.setCurrentText(camera.record_mode.value)
            self._retention.setValue(camera.retention_days)
        elif prefill_ip:
            self._rtsp_url.setText(f"rtsp://{prefill_ip}/")

        form = QFormLayout()
        form.addRow("Name", self._name)
        form.addRow("RTSP URL", self._rtsp_url)
        form.addRow("Sub-stream URL", self._sub_stream_url)
        form.addRow("Username", self._username)
        form.addRow("Password", self._password)
        form.addRow(self._ptz)
        form.addRow("Record", self._record_mode)
        form.addRow("Retention (days)", self._retention)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._error_label)
        layout.addWidget(buttons)

    def camera(self) -> Camera | None:
        return self._result_camera

    def _on_accept(self) -> None:
        fields = {
            "name": self._name.text(),
            "rtsp_url": self._rtsp_url.text(),
            "sub_stream_url": self._sub_stream_url.text(),
            "username": self._username.text(),
            "password": self._password.text(),
            "ptz_enabled": self._ptz.isChecked(),
            "record_mode": self._record_mode.currentData(),
            "retention_days": self._retention.value(),
        }
        try:
            self._result_camera = build_camera_from_fields(fields)
        except CameraFormError as exc:
            self._error_label.setText(str(exc))
            self._error_label.show()
            return
        self.accept()
