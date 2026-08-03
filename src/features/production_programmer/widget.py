"""
UI component for Production Programmer.
Provides interactive controls for firmware selection, custom memory start address,
SWD clock speed, connect modes, verify toggles, UID/Serial provisioning,
real-time execution monitoring, and SQLite traceability logging.
"""

import os
from typing import Optional, List
from PySide6.QtCore import Qt, QThread, Slot
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QGroupBox,
    QPushButton,
    QLabel,
    QLineEdit,
    QFileDialog,
    QProgressBar,
    QTextEdit,
    QComboBox,
    QCheckBox,
    QMessageBox,
)

from src.common import get_logger
from src.common.traceability import TraceabilityDatabase
from src.features.production_programmer.worker import ProductionProgrammerWorker
from src.features.production_programmer.provisioning import ProvisioningService

logger = get_logger("ProductionProgrammerWidget")

# Standard STM32 Memory Start Address Presets
ADDRESS_PRESETS = [
    ("0x08000000 - Main Flash Memory (Default Start)", "0x08000000"),
    ("0x08004000 - Application Offset (16 KB Bootloader)", "0x08004000"),
    ("0x08008000 - Application Offset (32 KB Bootloader)", "0x08008000"),
    ("0x08010000 - Application Offset (64 KB Bootloader)", "0x08010000"),
    ("0x20000000 - SRAM1 (RAM Execution / Testing)", "0x20000000"),
]


class ProductionProgrammerWidget(QWidget):
    """
    Industrial UI Widget for managing firmware deployments, custom start addressing,
    serial number provisioning, full chip erase operations, and traceability logging.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._flash_thread: Optional[QThread] = None
        self._flash_worker: Optional[ProductionProgrammerWorker] = None
        self._db_service = TraceabilityDatabase()
        self._provision_service = ProvisioningService()

        # Cache for current operation tracking
        self._current_uid: str = "UNKNOWN-UID"
        self._current_serial: Optional[str] = None

        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(10)

        # -------------------------------------------------------------
        # Operator Visual Status Banner (READY / PASS / FAIL)
        # -------------------------------------------------------------
        self.lbl_status_banner = QLabel("SYSTEM READY")
        self.lbl_status_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status_banner.setMinimumHeight(42)
        self._set_banner_style("#444444", "SYSTEM READY")
        main_layout.addWidget(self.lbl_status_banner)

        # -------------------------------------------------------------
        # Hardware & Connection Configuration Group
        # -------------------------------------------------------------
        config_group = QGroupBox("Hardware SWD Configuration")
        config_layout = QHBoxLayout()

        config_layout.addWidget(QLabel("Clock Speed:"))
        self.combo_clock = QComboBox()
        self.combo_clock.addItems([
            "100 kHz (100000)",
            "1 MHz (1000000)",
            "4 MHz (4000000)",
            "10 MHz (10000000)",
        ])
        self.combo_clock.setCurrentIndex(1)  # Default: 1 MHz
        config_layout.addWidget(self.combo_clock)

        config_layout.addWidget(QLabel("Mode:"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["under-reset", "attach"])
        self.combo_mode.setCurrentIndex(0)
        config_layout.addWidget(self.combo_mode)

        self.chk_verify = QCheckBox("Verify after flash")
        self.chk_verify.setChecked(True)
        config_layout.addWidget(self.chk_verify)

        config_layout.addStretch()
        config_group.setLayout(config_layout)
        main_layout.addWidget(config_group)

        # -------------------------------------------------------------
        # Firmware File & Memory Addressing Group
        # -------------------------------------------------------------
        file_group = QGroupBox(
            "Firmware Binary (.hex / .bin) & Memory Addressing")
        file_layout = QVBoxLayout()

        file_row_layout = QHBoxLayout()
        self.txt_filepath = QLineEdit()
        self.txt_filepath.setPlaceholderText(
            "Select firmware binary file (.hex or .bin)...")
        self.txt_filepath.setReadOnly(True)

        self.btn_browse = QPushButton("Browse File...")
        self.btn_browse.clicked.connect(self._select_file)

        file_row_layout.addWidget(self.txt_filepath)
        file_row_layout.addWidget(self.btn_browse)
        file_layout.addLayout(file_row_layout)

        addr_row_layout = QHBoxLayout()
        addr_row_layout.addWidget(QLabel("Start Address:"))
        self.combo_address = QComboBox()
        self.combo_address.setEditable(True)
        for label, addr in ADDRESS_PRESETS:
            self.combo_address.addItem(label, addr)
        self.combo_address.setToolTip(
            "Mandatory base address for raw .bin files. Acts as address override for .hex/.elf."
        )
        addr_row_layout.addWidget(self.combo_address, stretch=1)
        file_layout.addLayout(addr_row_layout)

        file_group.setLayout(file_layout)
        main_layout.addWidget(file_group)

        # -------------------------------------------------------------
        # Phase 2: Serial Provisioning & 96-bit Unique ID Group
        # -------------------------------------------------------------
        prov_group = QGroupBox("Device Provisioning & 96-bit Unique ID")
        prov_layout = QGridLayout(prov_group)
        prov_layout.setContentsMargins(10, 14, 10, 10)
        prov_layout.setHorizontalSpacing(12)

        self.chk_provision = QCheckBox("Inject Serial Number after Flash")
        self.chk_provision.setChecked(False)
        prov_layout.addWidget(self.chk_provision, 0, 0, 1, 2)

        prov_layout.addWidget(QLabel("Target UID:"), 0, 2)
        self.txt_uid = QLineEdit("UNKNOWN-UID")
        self.txt_uid.setReadOnly(True)
        self.txt_uid.setStyleSheet(
            "background-color: #2D2D30; color: #4EC9B0; font-weight: bold;")
        prov_layout.addWidget(self.txt_uid, 0, 3)

        prov_layout.addWidget(QLabel("Serial Prefix:"), 1, 0)
        self.txt_prefix = QLineEdit("BLINK-")
        self.txt_prefix.setFixedWidth(90)
        prov_layout.addWidget(self.txt_prefix, 1, 1)

        prov_layout.addWidget(QLabel("Next Counter:"), 1, 2)
        self.txt_counter = QLineEdit("1001")
        self.txt_counter.setFixedWidth(80)
        prov_layout.addWidget(self.txt_counter, 1, 3)

        prov_layout.addWidget(QLabel("Inject Address:"), 1, 4)
        self.txt_serial_addr = QLineEdit("0x0801FC00")
        self.txt_serial_addr.setFixedWidth(100)
        prov_layout.addWidget(self.txt_serial_addr, 1, 5)

        main_layout.addWidget(prov_group)

        # -------------------------------------------------------------
        # Primary & Secondary Execution Buttons
        # -------------------------------------------------------------
        self.btn_production_flash = QPushButton("ONE-CLICK PRODUCTION FLASH")
        self.btn_production_flash.setMinimumHeight(45)
        self.btn_production_flash.setStyleSheet(
            "background-color: #2E8B57; color: white; font-weight: bold; font-size: 13px;"
        )
        self.btn_production_flash.clicked.connect(self._start_production_flash)
        main_layout.addWidget(self.btn_production_flash)

        action_layout = QHBoxLayout()

        self.btn_start_flash = QPushButton("Start Production Flash")
        self.btn_start_flash.clicked.connect(self._start_production_flash)
        action_layout.addWidget(self.btn_start_flash)

        self.btn_chip_erase = QPushButton("Full Chip Erase")
        self.btn_chip_erase.setStyleSheet(
            "QPushButton { color: #d9534f; font-weight: bold; }")
        self.btn_chip_erase.clicked.connect(self._start_chip_erase)
        action_layout.addWidget(self.btn_chip_erase)

        main_layout.addLayout(action_layout)

        # -------------------------------------------------------------
        # Progress Bar
        # -------------------------------------------------------------
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)

        # -------------------------------------------------------------
        # Log Console & SQLite Excel Export Controls
        # -------------------------------------------------------------
        log_group = QGroupBox("SWD Operation & Traceability Logs")
        log_layout = QVBoxLayout()

        self.log_viewer = QTextEdit()
        self.log_viewer.setReadOnly(True)
        self.log_viewer.setStyleSheet(
            "background-color: #1E1E1E; color: #00FF66; font-family: Consolas, monospace; font-size: 11px;"
        )
        log_layout.addWidget(self.log_viewer)

        btn_layout = QHBoxLayout()
        self.btn_export_excel = QPushButton("📊 Export Logs to Excel (.csv)")
        self.btn_export_excel.setStyleSheet(
            "background-color: #205081; color: white; font-weight: bold; padding: 4px 12px;"
        )
        self.btn_export_excel.clicked.connect(self._export_traceability_logs)
        btn_layout.addWidget(self.btn_export_excel)

        btn_layout.addStretch()

        self.btn_clear_log = QPushButton("Clear Console")
        self.btn_clear_log.clicked.connect(self.log_viewer.clear)
        btn_layout.addWidget(self.btn_clear_log)

        log_layout.addLayout(btn_layout)
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)

        self._append_log(
            "[SYSTEM] Production Programmer & SQLite Traceability Module Ready.")

    def _set_banner_style(self, bg_color: str, text: str) -> None:
        """Updates the top status banner color and message for operators."""
        self.lbl_status_banner.setText(text)
        self.lbl_status_banner.setStyleSheet(
            f"background-color: {bg_color}; color: white; font-weight: bold; "
            f"font-size: 16px; border-radius: 4px; padding: 4px;"
        )

    def _get_selected_clock_freq(self) -> int:
        text = self.combo_clock.currentText()
        if "10 MHz" in text:
            return 10000000
        if "4 MHz" in text:
            return 4000000
        if "1 MHz" in text:
            return 1000000
        return 100000

    def _select_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Firmware File", "", "Firmware Files (*.hex *.bin);;All Files (*)"
        )
        if file_path:
            self.txt_filepath.setText(file_path)
            self._append_log(f"[INFO] Firmware binary selected: {file_path}")

    def _parse_input_address(self, text: str) -> int:
        clean_text = text.strip()
        if " - " in clean_text:
            clean_text = self.combo_address.currentData()
        if clean_text.lower().startswith("0x"):
            return int(clean_text, 16)
        return int(clean_text)

    def _append_log(self, message: str) -> None:
        self.log_viewer.append(message)
        self.log_viewer.verticalScrollBar().setValue(
            self.log_viewer.verticalScrollBar().maximum()
        )

    @Slot()
    def _export_traceability_logs(self) -> None:
        """Exports SQLite database rows to a user-specified CSV/Excel file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Production Logs", "Production_Traceability_Logs.csv", "CSV Files (*.csv)"
        )
        if not file_path:
            return

        success = self._db_service.export_to_csv(file_path)
        if success:
            QMessageBox.information(
                self, "Export Successful", f"Production logs exported to:\n{file_path}"
            )
            self._append_log(f"[TRACEABILITY] Logs exported to {file_path}")
        else:
            QMessageBox.critical(self, "Export Error",
                                 "Failed to export logs to file.")

    # -----------------------------------------------------------------
    # Execution Slots (Flash & Erase)
    # -----------------------------------------------------------------
    def _start_production_flash(self) -> None:
        file_path = self.txt_filepath.text().strip()
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(
                self, "Invalid File", "Please select a valid .hex or .bin firmware file first."
            )
            return

        try:
            start_address = self._parse_input_address(
                self.combo_address.currentText())
            serial_address = int(self.txt_serial_addr.text().strip(), 16)
            counter_val = int(self.txt_counter.text().strip())
        except ValueError as err:
            QMessageBox.warning(self, "Input Error",
                                f"Invalid numeric input: {str(err)}")
            return

        clock_freq = self._get_selected_clock_freq()
        connect_mode = self.combo_mode.currentText()
        verify_enabled = self.chk_verify.isChecked()

        # Provisioning setup
        enable_provisioning = self.chk_provision.isChecked()
        serial_payload: List[int] = []
        if enable_provisioning:
            self._provision_service.prefix = self.txt_prefix.text().strip()
            self._provision_service.current_counter = counter_val
            self._current_serial = self._provision_service.get_current_serial_string()
            serial_payload = self._provision_service.build_serial_payload()
        else:
            self._current_serial = None

        self._set_buttons_enabled(False)
        self.progress_bar.setValue(0)
        self._set_banner_style("#007ACC", "⏳ PROGRAMMING IN PROGRESS...")
        self.txt_uid.setText("Reading...")
        self._append_log("-" * 65)
        self._append_log(
            f"[SYSTEM] Launching SWD/pyOCD programmer thread @ 0x{start_address:08X}...")

        self._flash_thread = QThread()
        self._flash_worker = ProductionProgrammerWorker(
            file_path=file_path,
            base_address=start_address,
            clock_freq=clock_freq,
            connect_mode=connect_mode,
            verify_enabled=verify_enabled,
            enable_provisioning=enable_provisioning,
            serial_payload=serial_payload,
            serial_address=serial_address,
        )
        self._flash_worker.moveToThread(self._flash_thread)

        self._flash_thread.started.connect(
            self._flash_worker.run_production_flash)
        self._flash_worker.log_signal.connect(self._append_log)
        self._flash_worker.progress_signal.connect(self.progress_bar.setValue)
        self._flash_worker.finished_signal.connect(self._on_operation_finished)

        # Connect UID signal to display UID in UI immediately
        if hasattr(self._flash_worker, "uid_read_signal"):
            self._flash_worker.uid_read_signal.connect(self._on_uid_read)

        self._flash_worker.finished_signal.connect(self._flash_thread.quit)
        self._flash_worker.finished_signal.connect(
            self._flash_worker.deleteLater)
        self._flash_thread.finished.connect(self._flash_thread.deleteLater)

        self._flash_thread.start()

    def _start_chip_erase(self) -> None:
        reply = QMessageBox.question(
            self,
            "Confirm Chip Erase",
            "Are you sure you want to perform a FULL CHIP ERASE?\n\nThis will completely wipe the target microcontroller flash memory.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        clock_freq = self._get_selected_clock_freq()
        connect_mode = self.combo_mode.currentText()

        self._set_buttons_enabled(False)
        self.progress_bar.setValue(0)
        self._set_banner_style("#E67E22", "⏳ FULL CHIP ERASE IN PROGRESS...")
        self._append_log("-" * 65)
        self._append_log(
            "[SYSTEM] Launching SWD/pyOCD background erase worker...")

        self._flash_thread = QThread()
        self._flash_worker = ProductionProgrammerWorker(
            file_path="",
            base_address=0x08000000,
            clock_freq=clock_freq,
            connect_mode=connect_mode,
            verify_enabled=False,
        )
        self._flash_worker.moveToThread(self._flash_thread)

        self._flash_thread.started.connect(self._flash_worker.run_chip_erase)
        self._flash_worker.log_signal.connect(self._append_log)
        self._flash_worker.progress_signal.connect(self.progress_bar.setValue)
        self._flash_worker.finished_signal.connect(self._on_operation_finished)

        self._flash_worker.finished_signal.connect(self._flash_thread.quit)
        self._flash_worker.finished_signal.connect(
            self._flash_worker.deleteLater)
        self._flash_thread.finished.connect(self._flash_thread.deleteLater)

        self._flash_thread.start()

    @Slot(str)
    def _on_uid_read(self, uid_str: str) -> None:
        """Updates the UID field as soon as the probe reads it from hardware."""
        self._current_uid = uid_str
        self.txt_uid.setText(uid_str)

    @Slot(bool, str)
    def _on_operation_finished(self, success: bool, message: str) -> None:
        self._set_buttons_enabled(True)

        # 1. Update Operator Status Banner
        if success:
            self._set_banner_style("#2E8B57", "✔ PASS — OPERATION SUCCESSFUL")
            self._append_log(f"[SUCCESS] {message}")

            # Increment provision counter if it was enabled and successful
            if self.chk_provision.isChecked():
                self._provision_service.increment()
                self.txt_counter.setText(
                    str(self._provision_service.current_counter))
        else:
            self._set_banner_style("#D9534F", "✘ FAIL — OPERATION ERROR")
            self._append_log(f"[FAILED] {message}")

        # 2. Log record to local SQLite Database
        firmware_name = os.path.basename(
            self.txt_filepath.text()) or "CHIP_ERASE"
        status_text = "PASS" if success else "FAIL"
        self._db_service.log_operation(
            firmware_name=firmware_name,
            uid_96bit=self._current_uid,
            serial_number=self._current_serial,
            status=status_text,
            message=message,
        )

    def _set_buttons_enabled(self, enabled: bool) -> None:
        self.btn_production_flash.setEnabled(enabled)
        self.btn_start_flash.setEnabled(enabled)
        self.btn_chip_erase.setEnabled(enabled)
        self.btn_browse.setEnabled(enabled)
        self.btn_export_excel.setEnabled(enabled)

    def shutdown_threads(self) -> None:
        """Safely terminate background programmer threads before exiting application."""
        if self._flash_thread and self._flash_thread.isRunning():
            self._flash_thread.quit()
            self._flash_thread.wait()
