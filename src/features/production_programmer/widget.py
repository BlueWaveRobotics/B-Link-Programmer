"""
UI component for Production Programmer.
Provides interactive controls for firmware selection, custom memory start address,
SWD clock speed, connect modes, verify toggles, and real-time execution monitoring.
"""

import os
from typing import Optional
from PySide6.QtCore import Qt, QThread, Slot
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
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
from src.features.production_programmer.worker import ProductionProgrammerWorker

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
    full chip erase operations, and target SWD hardware configuration.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._flash_thread: Optional[QThread] = None
        self._flash_worker: Optional[ProductionProgrammerWorker] = None

        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

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

        # Row 1: File selection
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

        # Row 2: Start Address Selector
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
        # Log Console Display
        # -------------------------------------------------------------
        log_group = QGroupBox("SWD Operation & Debug Logs")
        log_layout = QVBoxLayout()

        self.log_viewer = QTextEdit()
        self.log_viewer.setReadOnly(True)
        self.log_viewer.setStyleSheet(
            "background-color: #1E1E1E; color: #00FF66; font-family: Consolas, monospace; font-size: 11px;"
        )
        log_layout.addWidget(self.log_viewer)

        self.btn_clear_log = QPushButton("Clear Console")
        self.btn_clear_log.clicked.connect(self.log_viewer.clear)
        log_layout.addWidget(self.btn_clear_log,
                             alignment=Qt.AlignmentFlag.AlignRight)

        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)

        self._append_log("[SYSTEM] Production Programmer Module Ready.")

    # -----------------------------------------------------------------
    # Configuration & File Selection Helpers
    # -----------------------------------------------------------------
    def _get_selected_clock_freq(self) -> int:
        """Parse numeric clock frequency from combobox text selection."""
        text = self.combo_clock.currentText()
        if "10 MHz" in text:
            return 10000000
        if "4 MHz" in text:
            return 4000000
        if "1 MHz" in text:
            return 1000000
        return 100000  # Default: 100 kHz

    def _select_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Firmware File",
            "",
            "Firmware Files (*.hex *.bin);;All Files (*)",
        )
        if file_path:
            self.txt_filepath.setText(file_path)
            self._append_log(f"[INFO] Firmware binary selected: {file_path}")

    def _parse_input_address(self, text: str) -> int:
        """Safely convert hexadecimal (0x...) or decimal string to integer address."""
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

    # -----------------------------------------------------------------
    # Execution Slots (Flash & Erase)
    # -----------------------------------------------------------------
    def _start_production_flash(self) -> None:
        file_path = self.txt_filepath.text().strip()
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(
                self,
                "Invalid File",
                "Please select a valid .hex or .bin firmware file first.",
            )
            return

        try:
            start_address = self._parse_input_address(
                self.combo_address.currentText())
            if start_address < 0 or start_address > 0xFFFFFFFF:
                raise ValueError("Address out of 32-bit ARM Cortex-M range.")
        except ValueError as err:
            QMessageBox.warning(
                self, "Invalid Address", f"Please enter a valid memory address: {str(err)}"
            )
            return

        clock_freq = self._get_selected_clock_freq()
        connect_mode = self.combo_mode.currentText()
        verify_enabled = self.chk_verify.isChecked()

        self._set_buttons_enabled(False)
        self.progress_bar.setValue(0)
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
        )
        self._flash_worker.moveToThread(self._flash_thread)

        self._flash_thread.started.connect(
            self._flash_worker.run_production_flash)
        self._flash_worker.log_signal.connect(self._append_log)
        self._flash_worker.progress_signal.connect(self.progress_bar.setValue)
        self._flash_worker.finished_signal.connect(self._on_operation_finished)

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

    @Slot(bool, str)
    def _on_operation_finished(self, success: bool, message: str) -> None:
        self._set_buttons_enabled(True)
        if success:
            self._append_log(f"[SUCCESS] {message}")
        else:
            self._append_log(f"[FAILED] {message}")

    def _set_buttons_enabled(self, enabled: bool) -> None:
        self.btn_production_flash.setEnabled(enabled)
        self.btn_start_flash.setEnabled(enabled)
        self.btn_chip_erase.setEnabled(enabled)
        self.btn_browse.setEnabled(enabled)

    def shutdown_threads(self) -> None:
        """Safely terminate background programmer threads before exiting application."""
        if self._flash_thread and self._flash_thread.isRunning():
            self._flash_thread.quit()
            self._flash_thread.wait()
