"""
Diagnostic UI Widget for Option Bytes.
Updated for STM32F1 (0xA5 as Unlock Key).
"""

from typing import Optional, Dict, Any
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QLabel,
    QCheckBox,
    QPushButton,
    QLineEdit,
    QMessageBox,
)

from src.common import get_logger
from src.features.option_bytes.worker import (
    OptionBytesReadWorker,
    OptionBytesProgramWorker,
)

logger = get_logger("OptionBytesWidget")


class OptionBytesWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._read_worker: Optional[OptionBytesReadWorker] = None
        self._program_worker: Optional[OptionBytesProgramWorker] = None
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(14)

        rdp_group = QGroupBox("Read-Out Protection (RDP)")
        rdp_layout = QVBoxLayout(rdp_group)

        self.chk_rdp = QCheckBox("Read Out Protection (RDP Level 1)")
        self.chk_rdp.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.chk_rdp.setChecked(True)
        self.chk_rdp.setToolTip(
            "Check to Lock (0xBB). Uncheck to Unlock & Mass Erase (0xA5).")
        rdp_layout.addWidget(self.chk_rdp)

        self.lbl_rdp_status = QLabel("Current Status: Unknown")
        self.lbl_rdp_status.setStyleSheet(
            "color: #BDC3C7; font-size: 10pt; font-weight: bold;")
        rdp_layout.addWidget(self.lbl_rdp_status)

        main_layout.addWidget(rdp_group)

        user_group = QGroupBox("User Configuration (USER OB)")
        user_layout = QVBoxLayout(user_group)

        self.chk_iwdg_sw = QCheckBox("IWDG_SW: Independent Watchdog Software")
        self.chk_iwdg_sw.setChecked(True)
        user_layout.addWidget(self.chk_iwdg_sw)

        self.chk_nrst_stop = QCheckBox("nRST_STOP: No Reset on STOP")
        self.chk_nrst_stop.setChecked(True)
        user_layout.addWidget(self.chk_nrst_stop)

        self.chk_nrst_stdby = QCheckBox("nRST_STDBY: No Reset on STANDBY")
        self.chk_nrst_stdby.setChecked(True)
        user_layout.addWidget(self.chk_nrst_stdby)

        main_layout.addWidget(user_group)

        raw_group = QGroupBox("Raw Option Bytes Dump")
        raw_layout = QHBoxLayout(raw_group)
        raw_layout.addWidget(QLabel("Raw Block:"))
        self.txt_raw_hex = QLineEdit()
        self.txt_raw_hex.setReadOnly(True)
        self.txt_raw_hex.setFont(QFont("Consolas", 10))
        raw_layout.addWidget(self.txt_raw_hex)
        main_layout.addWidget(raw_group)

        main_layout.addStretch()

        btn_layout = QHBoxLayout()
        self.btn_reload = QPushButton("🔄 Reload OB")
        self.btn_reload.clicked.connect(self._on_reload_clicked)

        self.btn_apply = QPushButton("⚡ Apply Option Bytes")
        self.btn_apply.setStyleSheet(
            "background-color: #E67E22; color: white; font-weight: bold; padding: 8px;")
        self.btn_apply.clicked.connect(self._on_apply_clicked)

        btn_layout.addWidget(self.btn_reload)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_apply)

        main_layout.addLayout(btn_layout)

    @Slot()
    def _on_reload_clicked(self) -> None:
        self.btn_reload.setEnabled(False)
        self.btn_apply.setEnabled(False)
        self.btn_reload.setText("⏳ Reading...")

        self._read_worker = OptionBytesReadWorker()
        self._read_worker.ob_read_finished.connect(self._on_read_finished)
        self._read_worker.start()

    @Slot(bool, dict, str)
    def _on_read_finished(self, success: bool, ob_data: Dict[str, Any], error_msg: str) -> None:
        self.btn_reload.setEnabled(True)
        self.btn_apply.setEnabled(True)
        self.btn_reload.setText("🔄 Reload OB")

        if not success:
            QMessageBox.critical(self, "Option Bytes Error", error_msg)
            return

        rdp_raw = ob_data.get("rdp_raw", 0xBB)

        # 0xA5 is the magic unlock byte for STM32F1
        if rdp_raw == 0xA5:
            self.chk_rdp.setChecked(False)
            self.lbl_rdp_status.setText("Status: Unlocked (Level 0 - 0xA5)")
            self.lbl_rdp_status.setStyleSheet(
                "color: #2ECC71; font-weight: bold;")
        else:
            self.chk_rdp.setChecked(True)
            self.lbl_rdp_status.setText(
                f"Status: Locked (Level 1 - 0x{rdp_raw:02X})")
            self.lbl_rdp_status.setStyleSheet(
                "color: #E74C3C; font-weight: bold;")

        self.chk_iwdg_sw.setChecked(ob_data.get("iwdg_sw", True))
        self.chk_nrst_stop.setChecked(ob_data.get("nrst_stop", True))
        self.chk_nrst_stdby.setChecked(ob_data.get("nrst_stdby", True))
        self.txt_raw_hex.setText(ob_data.get("raw_hex", ""))

    @Slot()
    def _on_apply_clicked(self) -> None:
        is_checked = self.chk_rdp.isChecked()
        # ارسال 0xA5 برای باز کردن قفل STM32F1
        rdp_val = 0xBB if is_checked else 0xA5

        user_val = 0x00
        if self.chk_iwdg_sw.isChecked():
            user_val |= 1 << 0
        if self.chk_nrst_stop.isChecked():
            user_val |= 1 << 1
        if self.chk_nrst_stdby.isChecked():
            user_val |= 1 << 2
        user_val |= 0xF8

        self.btn_apply.setEnabled(False)
        self.btn_reload.setEnabled(False)
        self.btn_apply.setText("⏳ Programming...")

        self._program_worker = OptionBytesProgramWorker(
            rdp_value=rdp_val, user_config_byte=user_val)
        self._program_worker.ob_program_finished.connect(
            self._on_program_finished)
        self._program_worker.start()

    @Slot(bool, str)
    def _on_program_finished(self, success: bool, message: str) -> None:
        self.btn_apply.setEnabled(True)
        self.btn_reload.setEnabled(True)
        self.btn_apply.setText("⚡ Apply Option Bytes")

        if success:
            QMessageBox.information(self, "Success", message)
            self._on_reload_clicked()
        else:
            QMessageBox.critical(self, "Error", message)

    def shutdown_threads(self) -> None:
        for worker in (self._read_worker, self._program_worker):
            if worker and worker.isRunning():
                worker.quit()
                worker.wait()
