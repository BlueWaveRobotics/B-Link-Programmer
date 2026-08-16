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
    QFrame,
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
        self._apply_styles()

    def _apply_styles(self) -> None:
        """اعمال تم صنعتی و مدرن هماهنگ با سایر بخش‌های برنامه"""
        self.setStyleSheet(
            """
            QWidget {
                background-color: #0B1220;
                color: #E5E7EB;
                font-family: "Segoe UI", "Arial";
            }
            QGroupBox {
                background-color: #111C2E;
                border: 1px solid #2A3D59;
                border-radius: 12px;
                margin-top: 25px;
                font-size: 15px;
                font-weight: 800;
                color: #38BDF8;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 18px;
                padding: 5px 11px;
                background-color: #0B1220;
                color: #38BDF8;
            }
            QLabel {
                color: #E5EDF7;
                font-size: 14px;
                font-weight: 650;
            }
            QLineEdit {
                background-color: #0A1323;
                color: #F8FAFC;
                border: 1px solid #40516B;
                border-radius: 8px;
                padding: 10px 13px;
                min-height: 24px;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 15px;
                font-weight: 700;
                selection-background-color: #155E75;
            }
            QLineEdit:read-only {
                background-color: #162338;
                color: #CBD5E1;
                border: 1px dashed #3A4E6A;
            }
            QCheckBox {
                color: #E5EDF7;
                font-size: 14px;
                font-weight: 700;
                spacing: 12px;
                padding: 4px 0px;
            }
            QCheckBox:hover { color: #38BDF8; }
            QCheckBox::indicator {
                width: 24px;
                height: 24px;
                border: 2px solid #64748B;
                border-radius: 6px;
                background-color: #0A1323;
            }
            QCheckBox::indicator:hover { border-color: #38BDF8; }
            QCheckBox::indicator:checked {
                background-color: #059669;
                border-color: #10B981;
                image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='4' stroke-linecap='round' stroke-linejoin='round'><polyline points='20 6 9 17 4 12'></polyline></svg>");
            }
            QPushButton {
                background-color: #2A3D59;
                color: #F8FAFC;
                border: 1px solid #405675;
                border-radius: 9px;
                padding: 10px 20px;
                min-height: 35px;
                font-size: 14px;
                font-weight: 800;
            }
            QPushButton:hover { background-color: #344C6B; border-color: #5B7393; }
            QPushButton:pressed { background-color: #1C2B42; }
            QPushButton:disabled { background-color: #172236; color: #52627A; border-color: #26354B; }
            
            QPushButton#applyBtn {
                background-color: #D97706; /* رنگ نارنجی صنعتی */
                border: 1px solid #F59E0B;
                color: white;
                font-size: 15px;
                font-weight: 900;
                letter-spacing: 1px;
            }
            QPushButton#applyBtn:hover { background-color: #F59E0B; }
            QPushButton#applyBtn:pressed { background-color: #B45309; }
            """
        )

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(22, 22, 22, 22)
        main_layout.setSpacing(20)

        # --- 1. RDP Group ---
        rdp_group = QGroupBox("Read-Out Protection (RDP)")
        rdp_layout = QVBoxLayout(rdp_group)
        rdp_layout.setContentsMargins(16, 20, 16, 16)
        rdp_layout.setSpacing(12)

        self.chk_rdp = QCheckBox(
            "Enable Read-Out Protection (Lock Chip - Level 1)")
        self.chk_rdp.setChecked(True)
        self.chk_rdp.setToolTip(
            "Check to Lock (0xBB). Uncheck to Unlock & Mass Erase (0xA5).")
        rdp_layout.addWidget(self.chk_rdp)

        self.lbl_rdp_status = QLabel("Current Status: Pending Read...")
        self.lbl_rdp_status.setStyleSheet(
            "color: #94A3B8; font-size: 13px; font-weight: bold; margin-top: 5px;")
        rdp_layout.addWidget(self.lbl_rdp_status)

        main_layout.addWidget(rdp_group)

        # --- 2. User OB Group ---
        user_group = QGroupBox("User Configuration (USER OB)")
        user_layout = QVBoxLayout(user_group)
        user_layout.setContentsMargins(16, 20, 16, 16)
        user_layout.setSpacing(12)

        self.chk_iwdg_sw = QCheckBox(
            "IWDG_SW: Independent Watchdog Software Mode")
        self.chk_iwdg_sw.setChecked(True)
        user_layout.addWidget(self.chk_iwdg_sw)

        self.chk_nrst_stop = QCheckBox(
            "nRST_STOP: No Reset generated when entering STOP mode")
        self.chk_nrst_stop.setChecked(True)
        user_layout.addWidget(self.chk_nrst_stop)

        self.chk_nrst_stdby = QCheckBox(
            "nRST_STDBY: No Reset generated when entering STANDBY mode")
        self.chk_nrst_stdby.setChecked(True)
        user_layout.addWidget(self.chk_nrst_stdby)

        main_layout.addWidget(user_group)

        # --- 3. Raw Dump Group ---
        raw_group = QGroupBox("Raw Option Bytes Dump")
        raw_layout = QHBoxLayout(raw_group)
        raw_layout.setContentsMargins(16, 20, 16, 16)

        lbl_raw = QLabel("Raw Hex Values:")
        lbl_raw.setFixedWidth(130)
        raw_layout.addWidget(lbl_raw)

        self.txt_raw_hex = QLineEdit()
        self.txt_raw_hex.setReadOnly(True)
        self.txt_raw_hex.setPlaceholderText(
            "Click 'Reload OB' to read from target...")
        raw_layout.addWidget(self.txt_raw_hex)

        main_layout.addWidget(raw_group)

        main_layout.addStretch()

        # --- 4. Bottom Controls ---
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(16)

        self.btn_reload = QPushButton("🔄 RELOAD OPTION BYTES")
        self.btn_reload.setMinimumHeight(55)
        self.btn_reload.clicked.connect(self._on_reload_clicked)

        self.btn_apply = QPushButton("⚡ APPLY CHANGES TO TARGET")
        self.btn_apply.setObjectName("applyBtn")
        self.btn_apply.setMinimumHeight(55)
        self.btn_apply.clicked.connect(self._on_apply_clicked)

        btn_layout.addWidget(self.btn_reload, 1)
        btn_layout.addWidget(self.btn_apply, 2)

        main_layout.addLayout(btn_layout)

    @Slot()
    def _on_reload_clicked(self) -> None:
        self.btn_reload.setEnabled(False)
        self.btn_apply.setEnabled(False)
        self.btn_reload.setText("⏳ READING TARGET...")

        self._read_worker = OptionBytesReadWorker()
        self._read_worker.ob_read_finished.connect(self._on_read_finished)
        self._read_worker.start()

    @Slot(bool, dict, str)
    def _on_read_finished(self, success: bool, ob_data: Dict[str, Any], error_msg: str) -> None:
        self.btn_reload.setEnabled(True)
        self.btn_apply.setEnabled(True)
        self.btn_reload.setText("🔄 RELOAD OPTION BYTES")

        if not success:
            QMessageBox.critical(self, "Option Bytes Error", error_msg)
            return

        rdp_raw = ob_data.get("rdp_raw", 0xBB)

        # 0xA5 is the magic unlock byte for STM32F1
        if rdp_raw == 0xA5:
            self.chk_rdp.setChecked(False)
            self.lbl_rdp_status.setText(
                "Current Status: UNLOCKED (Level 0 - 0xA5)")
            self.lbl_rdp_status.setStyleSheet(
                "color: #4ADE80; font-size: 14px; font-weight: bold; margin-top: 5px;")
        else:
            self.chk_rdp.setChecked(True)
            self.lbl_rdp_status.setText(
                f"Current Status: LOCKED (Level 1 - 0x{rdp_raw:02X})")
            self.lbl_rdp_status.setStyleSheet(
                "color: #F87171; font-size: 14px; font-weight: bold; margin-top: 5px;")

        self.chk_iwdg_sw.setChecked(ob_data.get("iwdg_sw", True))
        self.chk_nrst_stop.setChecked(ob_data.get("nrst_stop", True))
        self.chk_nrst_stdby.setChecked(ob_data.get("nrst_stdby", True))
        self.txt_raw_hex.setText(ob_data.get("raw_hex", ""))

    @Slot()
    def _on_apply_clicked(self) -> None:
        # هشدار امنیتی قبل از اعمال تغییرات
        is_checked = self.chk_rdp.isChecked()
        if not is_checked:
            reply = QMessageBox.warning(
                self, "Warning: Mass Erase",
                "Unlocking the target (RDP Level 0) will trigger a Hardware Mass Erase.\nAll flash memory contents will be permanently deleted.\n\nContinue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return

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
        self.btn_apply.setText("⏳ PROGRAMMING OPTION BYTES...")

        self._program_worker = OptionBytesProgramWorker(
            rdp_value=rdp_val, user_config_byte=user_val)
        self._program_worker.ob_program_finished.connect(
            self._on_program_finished)
        self._program_worker.start()

    @Slot(bool, str)
    def _on_program_finished(self, success: bool, message: str) -> None:
        self.btn_apply.setEnabled(True)
        self.btn_reload.setEnabled(True)
        self.btn_apply.setText("⚡ APPLY CHANGES TO TARGET")

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
