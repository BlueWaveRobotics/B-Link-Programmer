"""
Industrial Option Bytes (OB) Inspection and Configuration Widget modeled
after STM32CubeProgrammer. Supports RDP Levels, Hardware/Software Watchdog,
Stop/Standby Reset Behavior, and Live Hardware Synchronization.
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
    QComboBox,
    QCheckBox,
    QPushButton,
    QLineEdit,
    QMessageBox,
    QFormLayout,
)

from src.common import get_logger
from src.features.option_bytes.worker import (
    OptionBytesReadWorker,
    OptionBytesProgramWorker,
)

logger = get_logger("OptionBytesWidget")


class OptionBytesWidget(QWidget):
    """
    Feature widget for reading, displaying, and programming STM32 Option Bytes.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._read_worker: Optional[OptionBytesReadWorker] = None
        self._program_worker: Optional[OptionBytesProgramWorker] = None
        self._init_ui()

    def _init_ui(self) -> None:
        """Constructs the structured Option Bytes configuration form."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(14)

        # -------------------------------------------------------------
        # 1. Read-Out Protection (RDP) Section
        # -------------------------------------------------------------
        rdp_group = QGroupBox("Read-Out Protection (RDP)")
        rdp_layout = QFormLayout(rdp_group)
        rdp_layout.setSpacing(10)

        self.combo_rdp = QComboBox()
        self.combo_rdp.addItems([
            "Level 0 (AA - Unprotected)",
            "Level 1 (BB - Read Protected)",
            "Level 2 (CC - Chip Protection / Permanent - CAUTION)"
        ])
        rdp_layout.addRow(QLabel("RDP Level:"), self.combo_rdp)
        main_layout.addWidget(rdp_group)

        # -------------------------------------------------------------
        # 2. User Configuration Option Bytes (USER OB)
        # -------------------------------------------------------------
        user_group = QGroupBox("User Configuration (USER OB)")
        user_layout = QVBoxLayout(user_group)
        user_layout.setSpacing(10)

        self.chk_iwdg_sw = QCheckBox(
            "IWDG_SW: Independent Watchdog in Software Mode")
        self.chk_iwdg_sw.setChecked(True)
        self.chk_iwdg_sw.setToolTip(
            "If unchecked, Independent Watchdog starts automatically by hardware.")
        user_layout.addWidget(self.chk_iwdg_sw)

        self.chk_nrst_stop = QCheckBox(
            "nRST_STOP: No Reset Generated when entering STOP mode")
        self.chk_nrst_stop.setChecked(True)
        user_layout.addWidget(self.chk_nrst_stop)

        self.chk_nrst_stdby = QCheckBox(
            "nRST_STDBY: No Reset Generated when entering STANDBY mode")
        self.chk_nrst_stdby.setChecked(True)
        user_layout.addWidget(self.chk_nrst_stdby)

        main_layout.addWidget(user_group)

        # -------------------------------------------------------------
        # 3. Raw Hexadecimal Display Section
        # -------------------------------------------------------------
        raw_group = QGroupBox("Raw Option Bytes Dump")
        raw_layout = QHBoxLayout(raw_group)
        raw_layout.addWidget(QLabel("Raw OB Block (8 Bytes):"))
        self.txt_raw_hex = QLineEdit()
        self.txt_raw_hex.setReadOnly(True)
        self.txt_raw_hex.setFont(QFont("Consolas", 10))
        self.txt_raw_hex.setPlaceholderText(
            "Click 'Reload OB' to inspect hardware values...")
        raw_layout.addWidget(self.txt_raw_hex)
        main_layout.addWidget(raw_group)

        main_layout.addStretch()

        # -------------------------------------------------------------
        # 4. Action Buttons (Reload / Apply)
        # -------------------------------------------------------------
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.btn_reload = QPushButton("🔄 Reload OB")
        self.btn_reload.setStyleSheet(
            """
            QPushButton {
                background-color: #34495E; color: white; font-weight: bold;
                padding: 8px 18px; border-radius: 4px;
            }
            QPushButton:hover { background-color: #415B76; }
            """
        )
        self.btn_reload.clicked.connect(self._on_reload_clicked)

        self.btn_apply = QPushButton("⚡ Apply Option Bytes")
        self.btn_apply.setStyleSheet(
            """
            QPushButton {
                background-color: #E67E22; color: white; font-weight: bold;
                padding: 8px 18px; border-radius: 4px;
            }
            QPushButton:hover { background-color: #D35400; }
            """
        )
        self.btn_apply.clicked.connect(self._on_apply_clicked)

        btn_layout.addWidget(self.btn_reload)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_apply)

        main_layout.addLayout(btn_layout)

    @Slot()
    def _on_reload_clicked(self) -> None:
        """Triggers background read of current target Option Bytes."""
        self.btn_reload.setEnabled(False)
        self.btn_reload.setText("⏳ Reading...")

        self._read_worker = OptionBytesReadWorker()
        self._read_worker.ob_read_finished.connect(self._on_read_finished)
        self._read_worker.start()

    @Slot(bool, dict, str)
    def _on_read_finished(
        self, success: bool, ob_data: Dict[str, Any], error_msg: str
    ) -> None:
        """Populates UI controls with read hardware Option Bytes."""
        self.btn_reload.setEnabled(True)
        self.btn_reload.setText("🔄 Reload OB")

        if not success:
            QMessageBox.critical(self, "Option Bytes Error", error_msg)
            return

        # Synchronize UI with read parameters
        rdp_level = ob_data.get("rdp_level", "")
        for idx in range(self.combo_rdp.count()):
            if rdp_level.startswith(self.combo_rdp.itemText(idx)[:7]):
                self.combo_rdp.setCurrentIndex(idx)
                break

        self.chk_iwdg_sw.setChecked(ob_data.get("iwdg_sw", True))
        self.chk_nrst_stop.setChecked(ob_data.get("nrst_stop", True))
        self.chk_nrst_stdby.setChecked(ob_data.get("nrst_stdby", True))
        self.txt_raw_hex.setText(ob_data.get("raw_hex", ""))

    @Slot()
    def _on_apply_clicked(self) -> None:
        """Validates configuration and triggers Option Bytes programming."""
        rdp_idx = self.combo_rdp.currentIndex()
        if rdp_idx == 2:
            confirm = QMessageBox.warning(
                self,
                "Critical Warning: Permanent Chip Protection",
                "You selected RDP Level 2. Once applied, the microcontroller "
                "JTAG/SWD debug port is permanently disabled and cannot be reverted.\n\n"
                "Are you strictly sure you want to proceed?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirm == QMessageBox.StandardButton.No:
                return
            rdp_val = 0xCC
        elif rdp_idx == 1:
            rdp_val = 0xBB
        else:
            rdp_val = 0xAA

        # Construct USER Option Byte (Bits 0, 1, 2)
        user_val = 0x00
        if self.chk_iwdg_sw.isChecked():
            user_val |= (1 << 0)
        if self.chk_nrst_stop.isChecked():
            user_val |= (1 << 1)
        if self.chk_nrst_stdby.isChecked():
            user_val |= (1 << 2)
        user_val |= 0xF8  # Reserved bits high in standard STM32

        self.btn_apply.setEnabled(False)
        self.btn_apply.setText("⏳ Programming OB...")

        self._program_worker = OptionBytesProgramWorker(
            rdp_value=rdp_val, user_config_byte=user_val
        )
        self._program_worker.ob_program_finished.connect(
            self._on_program_finished)
        self._program_worker.start()

    @Slot(bool, str)
    def _on_program_finished(self, success: bool, message: str) -> None:
        """Handles completion of Option Bytes programming."""
        self.btn_apply.setEnabled(True)
        self.btn_apply.setText("⚡ Apply Option Bytes")

        if success:
            QMessageBox.information(self, "Success", message)
            self._on_reload_clicked()
        else:
            QMessageBox.critical(self, "Programming Error", message)

    def shutdown_threads(self) -> None:
        """Safely terminates active worker threads during application shutdown."""
        for worker in (self._read_worker, self._program_worker):
            if worker and worker.isRunning():
                logger.info("Stopping Option Bytes worker thread...")
                worker.quit()
                worker.wait()
                logger.info("✔ Option Bytes worker thread stopped.")
