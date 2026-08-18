"""
Diagnostic UI Widget for Option Bytes.
Updated for STM32F1 (0xA5 as Unlock Key).
Theme: BlueWave Sport, Dark, Industrial
"""

from src.common.resources import ICON_ARROWS_ROTATE, ICON_BOLT, ICON_BOLT, ICON_HOURGLASS
from typing import Optional, Dict, Any
from PySide6.QtCore import Qt, Slot, QSize
from PySide6.QtGui import QFont, QIcon
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
        """اعمال تم صنعتی و یکدست BlueWave با قوانین چک‌باکس و فیلد پویا"""
        self.setStyleSheet(
            """
            QWidget {
                background-color: #070B19;
                color: #F8FAFC;
                font-family: "Segoe UI", "Arial", sans-serif;
            }
            
            QGroupBox {
                background-color: #0C1327;
                border: 1px solid #1A2642;
                border-radius: 6px;
                margin-top: 20px;
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 0px;
                padding: 0px 8px;
                background-color: transparent;
                color: #00E5FF;
                font-size: 13px;
                font-weight: 800;
            }
            
            QLabel {
                color: #F8FAFC;
                font-size: 13px;
                font-weight: 600;
                background-color: transparent;
            }
            
            /* --- QCheckBox Styles --- */
            QCheckBox {
                background-color: transparent;
                color: #F8FAFC;
                font-size: 12px;
                font-weight: 600;
                spacing: 6px;
                padding: 3px 0px;
            }

            QCheckBox:hover {
                color: #00E5FF;
            }

            QCheckBox:checked {
                color: #00E5FF;
            }

            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #1A2642;
                border-radius: 3px;
                background-color: #03060E;
            }

            QCheckBox::indicator:hover {
                border-color: #00E5FF;
            }

            QCheckBox::indicator:checked {
                background-color: #00E5FF;
                border-color: #00E5FF;
                image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%23070B19' stroke-width='4' stroke-linecap='round' stroke-linejoin='round'><polyline points='20 6 9 17 4 12'></polyline></svg>");
            }

            /* --- QLineEdit & Dynamic Property Styles --- */
            QLineEdit {
                background-color: #03060E;
                color: #F8FAFC;
                border: 1px solid #1A2642;
                border-radius: 4px;
                padding: 8px 12px;
                font-family: "Consolas", monospace;
                font-size: 13px;
                font-weight: bold;
                selection-background-color: #00B4D8;
            }

            QLineEdit:read-only {
                background-color: #070B19;
                color: #94A3B8;
                border: 1px solid #1A2642;
            }

            /* وقتی داده معتبر خوانده شده و dynamic property فعال شد: */
            QLineEdit:read-only[hasFile="true"] {
                border: 1px solid #00E5FF;
                color: #00E5FF;
            }

            /* --- QPushButton Styles --- */
            QPushButton {
                background-color: #121D38;
                color: #F8FAFC;
                border: 1px solid #1A2642;
                border-radius: 6px;
                padding: 8px 16px;
                min-height: 40px;
                font-size: 13px;
                font-weight: bold;
            }
            
            QPushButton:hover { 
                background-color: #00B4D8;
                color: #FFFFFF;
                border-color: #00E5FF;
            }
            
            QPushButton:pressed { 
                background-color: #0093B4; 
            }
            
            QPushButton:disabled { 
                background-color: #0B1220; 
                color: #94A3B8; 
                border-color: #1A2642; 
            }
            
            QPushButton#applyBtn {
                border: 1px solid #00B4D8;
            }
            """
        )

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # --- 1. RDP Group ---
        rdp_group = QGroupBox("Read-Out Protection (RDP)")
        rdp_layout = QVBoxLayout(rdp_group)
        rdp_layout.setContentsMargins(16, 24, 16, 16)
        rdp_layout.setSpacing(12)

        self.chk_rdp = QCheckBox(
            "Enable Read-Out Protection (Lock Chip - Level 1)")
        self.chk_rdp.setChecked(True)
        self.chk_rdp.setToolTip(
            "Check to Lock (0xBB). Uncheck to Unlock & Mass Erase (0xA5).")
        rdp_layout.addWidget(self.chk_rdp)

        self.lbl_rdp_status = QLabel("Current Status: Pending Read...")
        self.lbl_rdp_status.setStyleSheet(
            "color: #94A3B8; font-size: 12px; font-weight: bold;")
        rdp_layout.addWidget(self.lbl_rdp_status)

        main_layout.addWidget(rdp_group)

        # --- 2. User OB Group ---
        user_group = QGroupBox("User Configuration (USER OB)")
        user_layout = QVBoxLayout(user_group)
        user_layout.setContentsMargins(16, 24, 16, 16)
        user_layout.setSpacing(10)

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
        raw_layout.setContentsMargins(16, 24, 16, 16)

        lbl_raw = QLabel("Raw Hex Values:")
        lbl_raw.setFixedWidth(120)
        raw_layout.addWidget(lbl_raw)

        self.txt_raw_hex = QLineEdit()
        self.txt_raw_hex.setReadOnly(True)
        self.txt_raw_hex.setPlaceholderText(
            "Click 'Reload Option Bytes' to read from target...")
        raw_layout.addWidget(self.txt_raw_hex)

        main_layout.addWidget(raw_group)
        main_layout.addStretch()

        # --- 4. Bottom Controls ---
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(16)

        self.btn_reload = QPushButton(" Reload Option Bytes")
        self.btn_reload.setIcon(
            QIcon(ICON_ARROWS_ROTATE))
        self.btn_reload.setIconSize(QSize(16, 16))
        self.btn_reload.setMinimumHeight(45)
        self.btn_reload.clicked.connect(self._on_reload_clicked)

        self.btn_apply = QPushButton(" Apply Changes to Target")
        self.btn_apply.setObjectName("applyBtn")
        self.btn_apply.setIcon(QIcon(ICON_BOLT))
        self.btn_apply.setIconSize(QSize(16, 16))
        self.btn_apply.setMinimumHeight(45)
        self.btn_apply.clicked.connect(self._on_apply_clicked)

        btn_layout.addWidget(self.btn_reload, 1)
        btn_layout.addWidget(self.btn_apply, 2)

        main_layout.addLayout(btn_layout)

    @Slot()
    def _on_reload_clicked(self) -> None:
        self.btn_reload.setEnabled(False)
        self.btn_apply.setEnabled(False)
        self.btn_reload.setText(" Reading Target...")
        self.btn_reload.setIcon(
            QIcon(ICON_HOURGLASS))
        self.lbl_rdp_status.setStyleSheet(
            "color: #00E5FF; font-size: 12px; font-weight: bold;")

        self._read_worker = OptionBytesReadWorker()
        self._read_worker.ob_read_finished.connect(self._on_read_finished)
        self._read_worker.start()

    @Slot(bool, dict, str)
    def _on_read_finished(self, success: bool, ob_data: Dict[str, Any], error_msg: str) -> None:
        self.btn_reload.setEnabled(True)
        self.btn_apply.setEnabled(True)
        self.btn_reload.setText(" Reload Option Bytes")
        self.btn_reload.setIcon(
            QIcon(ICON_ARROWS_ROTATE))

        if not success:
            QMessageBox.critical(self, "Option Bytes Error", error_msg)
            self.lbl_rdp_status.setText("Read Failed")
            self.lbl_rdp_status.setStyleSheet(
                "color: #EF4444; font-size: 12px; font-weight: bold;")

            # ریست کردن ویژگی dynamic property فیلد متنی
            self.txt_raw_hex.setProperty("hasFile", False)
            self.txt_raw_hex.style().unpolish(self.txt_raw_hex)
            self.txt_raw_hex.style().polish(self.txt_raw_hex)
            return

        rdp_raw = ob_data.get("rdp_raw", 0xBB)

        if rdp_raw == 0xA5:
            self.chk_rdp.setChecked(False)
            self.lbl_rdp_status.setText(
                "Current Status: UNLOCKED (Level 0 - 0xA5)")
            self.lbl_rdp_status.setStyleSheet(
                "color: #10B981; font-size: 12px; font-weight: bold;")
        else:
            self.chk_rdp.setChecked(True)
            self.lbl_rdp_status.setText(
                f"Current Status: LOCKED (Level 1 - 0x{rdp_raw:02X})")
            self.lbl_rdp_status.setStyleSheet(
                "color: #EF4444; font-size: 12px; font-weight: bold;")

        self.chk_iwdg_sw.setChecked(ob_data.get("iwdg_sw", True))
        self.chk_nrst_stop.setChecked(ob_data.get("nrst_stop", True))
        self.chk_nrst_stdby.setChecked(ob_data.get("nrst_stdby", True))

        # مقداردهی داده‌های خوانده‌شده و روشن کردن dynamic property
        raw_hex_value = ob_data.get("raw_hex", "")
        self.txt_raw_hex.setText(raw_hex_value)

        has_valid_data = bool(raw_hex_value.strip())
        self.txt_raw_hex.setProperty("hasFile", has_valid_data)

        # رندر مجدد استایل جهت اعمال تغییرات کادر
        self.txt_raw_hex.style().unpolish(self.txt_raw_hex)
        self.txt_raw_hex.style().polish(self.txt_raw_hex)

    @Slot()
    def _on_apply_clicked(self) -> None:
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
        self.btn_apply.setText(" Programming...")
        self.btn_apply.setIcon(
            QIcon(ICON_HOURGLASS))

        self._program_worker = OptionBytesProgramWorker(
            rdp_value=rdp_val, user_config_byte=user_val)
        self._program_worker.ob_program_finished.connect(
            self._on_program_finished)
        self._program_worker.start()

    @Slot(bool, str)
    def _on_program_finished(self, success: bool, message: str) -> None:
        self.btn_apply.setEnabled(True)
        self.btn_reload.setEnabled(True)
        self.btn_apply.setText(" Apply Changes to Target")
        self.btn_apply.setIcon(QIcon(ICON_BOLT))

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
