import os
import logging
from typing import Optional

# PySide6 Core & GUI Widgets
from PySide6.QtCore import Qt, QThread, Signal, Slot, QTimer
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog, QProgressBar,
    QTextEdit, QGroupBox, QMessageBox, QTabWidget, QComboBox,
    QCheckBox
)

# PySerial (for listing available COM ports)
import serial
import serial.tools.list_ports

# --- Internal Project Modular Imports ---
from src.worker import FlashWorker, SerialWorker

# from src.core import DAPLinkController
logger = logging.getLogger("DAPLinkSuite")


class MainWindow(QMainWindow):
    """
    Main GUI application window for DAPLink Programmer Management & CDC Serial Diagnostics.
    """
    # Signal to communicate with SerialWorker across threads
    send_serial_signal = Signal(bytes)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(
            "B-Link DAPLink Production & Diagnostic Suite - v1.0")
        self.resize(800, 600)

        # Thread & Worker References
        self.flash_thread: Optional[QThread] = None
        self.flash_worker: Optional[FlashWorker] = None
        self.serial_thread: Optional[QThread] = None
        self.serial_worker: Optional[SerialWorker] = None

        self.is_serial_connected = False
        self._init_ui()

    def _init_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Tab Widget Container
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # Initialize Tabs
        self.tab_programmer = QWidget()
        self.tab_serial = QWidget()

        self.tabs.addTab(self.tab_programmer, "⚡ Production Programmer & SWD")
        self.tabs.addTab(self.tab_serial, "🔌 CDC Serial Monitor")

        self._build_programmer_tab()
        self._build_serial_tab()

    # -----------------------------------------------------------------
    # Tab 1: SWD Production Programmer Build
    # -----------------------------------------------------------------
    def _build_programmer_tab(self) -> None:
        layout = QVBoxLayout(self.tab_programmer)

        # Target Detection Section (CubeProgrammer Style)
        target_group = QGroupBox("Target SWD Connection")
        target_layout = QHBoxLayout()

        self.lbl_target_id = QLabel("Target ID: Disconnected / Unknown")
        self.lbl_target_id.setStyleSheet("color: #E74C3C; font-weight: bold;")

        self.btn_refresh_target = QPushButton("🔄 Refresh Target")
        self.btn_refresh_target.setToolTip(
            "Detect ARM Core and read ID (No Chip Reset)")
        self.btn_refresh_target.clicked.connect(self.on_refresh_target_clicked)

        target_layout.addWidget(self.lbl_target_id)
        target_layout.addStretch()
        target_layout.addWidget(self.btn_refresh_target)
        target_group.setLayout(target_layout)
        layout.addWidget(target_group)

        # Target Config
        config_group = QGroupBox("Hardware Configuration")
        config_layout = QHBoxLayout()

        config_layout.addWidget(QLabel("SWD Clock: 100 kHz"))
        config_layout.addWidget(QLabel(" |   Connect Mode: Under-Reset"))
        config_layout.addWidget(
            QLabel(" |   Target: Auto-Detect (ARM Cortex-M)"))
        config_layout.addStretch()

        config_group.setLayout(config_layout)
        layout.addWidget(config_group)

        # File Selector
        file_group = QGroupBox("Firmware Binary (.hex / .bin)")
        file_layout = QHBoxLayout()
        self.txt_filepath = QLineEdit()
        self.txt_filepath.setPlaceholderText(
            "Select firmware binary file (.hex or .bin)...")
        self.txt_filepath.setReadOnly(True)
        self.btn_browse = QPushButton("Browse File...")
        self.btn_browse.clicked.connect(self._select_file)
        file_layout.addWidget(self.txt_filepath)
        file_layout.addWidget(self.btn_browse)
        file_group.setLayout(file_layout)
        layout.addWidget(file_group)

        # Main One-Click Action Button
        self.btn_production_flash = QPushButton("ONE-CLICK PRODUCTION FLASH")
        self.btn_production_flash.setMinimumHeight(45)
        self.btn_production_flash.setStyleSheet(
            "background-color: #2E8B57; color: white; font-weight: bold; font-size: 13px;"
        )
        self.btn_production_flash.clicked.connect(self._start_production_flash)
        layout.addWidget(self.btn_production_flash)

        action_layout = QHBoxLayout()

        # Start Production Flash Button
        self.btn_start_flash = QPushButton("Start Production Flash")
        self.btn_start_flash.clicked.connect(self._start_production_flash)
        action_layout.addWidget(self.btn_start_flash)

        # Full Chip Erase Button
        self.btn_chip_erase = QPushButton("Full Chip Erase")
        self.btn_chip_erase.setStyleSheet(
            "QPushButton { color: #d9534f; font-weight: bold; }")
        self.btn_chip_erase.clicked.connect(self._start_chip_erase)
        action_layout.addWidget(self.btn_chip_erase)

        layout.addLayout(action_layout)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # Programmer Logs
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
        layout.addWidget(log_group)

        self._append_flash_log(
            "[SYSTEM] DAPLink Production GUI Initialized. Ready for firmware deployment."
        )

    # -----------------------------------------------------------------
    # Tab 2: CDC Serial Monitor Build
    # -----------------------------------------------------------------
    def _build_serial_tab(self) -> None:
        layout = QVBoxLayout(self.tab_serial)

        # Port Configuration Top Panel
        serial_config_group = QGroupBox("COM Port Connection")
        serial_config_layout = QHBoxLayout()

        serial_config_layout.addWidget(QLabel("Port:"))
        self.combo_ports = QComboBox()
        self.combo_ports.setMinimumWidth(220)
        serial_config_layout.addWidget(self.combo_ports)

        self.btn_refresh_ports = QPushButton("Refresh")
        self.btn_refresh_ports.clicked.connect(self._refresh_serial_ports)
        serial_config_layout.addWidget(self.btn_refresh_ports)

        serial_config_layout.addWidget(QLabel("Baud Rate:"))
        self.combo_baud = QComboBox()
        self.combo_baud.addItems(
            ["9600", "19200", "38400", "57600",
                "115200", "230400", "460800", "921600"]
        )
        self.combo_baud.setCurrentText("115200")
        serial_config_layout.addWidget(self.combo_baud)

        self.btn_connect_serial = QPushButton("Connect")
        self.btn_connect_serial.setStyleSheet(
            "background-color: #2980B9; color: white; font-weight: bold;"
        )
        self.btn_connect_serial.clicked.connect(self._toggle_serial_connection)
        serial_config_layout.addWidget(self.btn_connect_serial)

        serial_config_group.setLayout(serial_config_layout)
        layout.addWidget(serial_config_group)

        # Display Options
        opt_layout = QHBoxLayout()
        self.chk_hex_view = QCheckBox("HEX Display Mode")
        self.chk_autoscroll = QCheckBox("Auto-Scroll")
        self.chk_autoscroll.setChecked(True)
        opt_layout.addWidget(self.chk_hex_view)
        opt_layout.addWidget(self.chk_autoscroll)
        opt_layout.addStretch()
        layout.addLayout(opt_layout)

        # Serial Terminal Console
        terminal_group = QGroupBox("RX/TX Terminal Console")
        terminal_layout = QVBoxLayout()
        self.txt_serial_console = QTextEdit()
        self.txt_serial_console.setReadOnly(True)
        self.txt_serial_console.setStyleSheet(
            "background-color: #0D1117; color: #E6EDF3; font-family: Consolas, monospace; font-size: 12px;"
        )
        terminal_layout.addWidget(self.txt_serial_console)

        # Send Input Field
        send_layout = QHBoxLayout()
        self.txt_send_data = QLineEdit()
        self.txt_send_data.setPlaceholderText(
            "Type string or HEX to send to target MCU...")
        self.txt_send_data.returnPressed.connect(self._send_serial_message)
        send_layout.addWidget(self.txt_send_data)

        self.btn_send = QPushButton("Send")
        self.btn_send.clicked.connect(self._send_serial_message)
        send_layout.addWidget(self.btn_send)

        self.btn_clear_serial = QPushButton("Clear")
        self.btn_clear_serial.clicked.connect(self.txt_serial_console.clear)
        send_layout.addWidget(self.btn_clear_serial)

        terminal_layout.addLayout(send_layout)
        terminal_group.setLayout(terminal_layout)
        layout.addWidget(terminal_group)

        # Initial Port Populate
        self._refresh_serial_ports()

    # -----------------------------------------------------------------
    # Flash Programmer Slots & Helpers
    # -----------------------------------------------------------------
    def _select_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Firmware File", "", "Firmware Files (*.hex *.bin);;All Files (*)"
        )
        if file_path:
            self.txt_filepath.setText(file_path)
            self._append_flash_log(
                f"[INFO] Selected firmware binary: {file_path}")

    def _append_flash_log(self, message: str) -> None:
        self.log_viewer.append(message)
        self.log_viewer.verticalScrollBar().setValue(
            self.log_viewer.verticalScrollBar().maximum()
        )

    def _start_production_flash(self) -> None:
        file_path = self.txt_filepath.text().strip()
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(
                self, "Invalid File", "Please select a valid .hex or .bin firmware file first."
            )
            return

        self.btn_production_flash.setEnabled(False)
        self.progress_bar.setValue(0)
        self._append_flash_log("-" * 65)
        self._append_flash_log(
            "[SYSTEM] Launching SWD/pyOCD background worker thread...")

        self.flash_thread = QThread()
        self.flash_worker = FlashWorker(
            file_path=file_path,
            clock_freq=100000,
            connect_mode="under-reset"
        )
        self.flash_worker.moveToThread(self.flash_thread)
        self.flash_worker.target_info_signal.connect(
            self.on_target_info_received)
        self.flash_thread.started.connect(
            self.flash_worker.run_production_flash)
        self.flash_worker.log_signal.connect(self._append_flash_log)
        self.flash_worker.progress_signal.connect(self.progress_bar.setValue)
        self.flash_worker.finished_signal.connect(self._on_flash_finished)

        self.flash_worker.finished_signal.connect(self.flash_thread.quit)
        self.flash_worker.finished_signal.connect(
            self.flash_worker.deleteLater)
        self.flash_thread.finished.connect(self.flash_thread.deleteLater)

        self.flash_thread.start()

    def _start_chip_erase(self) -> None:
        reply = QMessageBox.question(
            self,
            "Confirm Chip Erase",
            "Are you sure you want to perform a FULL CHIP ERASE?\n\nThis will completely wipe the target microcontroller flash memory.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        self.btn_production_flash.setEnabled(False)
        self.btn_chip_erase.setEnabled(False)
        self.progress_bar.setValue(0)
        self._append_flash_log("-" * 65)
        self._append_flash_log(
            "[SYSTEM] Launching SWD/pyOCD background worker for Chip Erase...")

        self.flash_thread = QThread()
        self.flash_worker = FlashWorker(
            file_path="",
            clock_freq=100000,
            connect_mode="under-reset"
        )
        self.flash_worker.moveToThread(self.flash_thread)

        self.flash_thread.started.connect(self.flash_worker.run_chip_erase)
        self.flash_worker.log_signal.connect(self._append_flash_log)
        self.flash_worker.progress_signal.connect(self.progress_bar.setValue)
        self.flash_worker.finished_signal.connect(self._on_flash_finished)

        self.flash_worker.finished_signal.connect(self.flash_thread.quit)
        self.flash_worker.finished_signal.connect(
            self.flash_worker.deleteLater)
        self.flash_thread.finished.connect(self.flash_thread.deleteLater)

        self.flash_thread.start()

    @Slot(bool, str)
    def _on_flash_finished(self, success: bool, message: str) -> None:
        self.btn_production_flash.setEnabled(True)
        self.btn_chip_erase.setEnabled(True)

        if success:
            self._append_flash_log(f"[SUCCESS] {message}")
        else:
            self._append_flash_log(f"[FAILED] {message}")

    # -----------------------------------------------------------------
    # Serial Monitor Slots & Helpers
    # -----------------------------------------------------------------
    def _refresh_serial_ports(self) -> None:
        self.combo_ports.clear()
        ports = serial.tools.list_ports.comports()
        if not ports:
            self.combo_ports.addItem("No COM ports found")
            return

        for p in sorted(ports):
            description = f"{p.device} ({p.description})"
            self.combo_ports.addItem(description, p.device)

    def _toggle_serial_connection(self) -> None:
        if not self.is_serial_connected:
            port_name = self.combo_ports.currentData()
            if not port_name:
                QMessageBox.warning(
                    self, "Warning", "Please select a valid COM port.")
                return

            baudrate = int(self.combo_baud.currentText())

            # Create Thread and Worker for continuous asynchronous listening
            self.serial_thread = QThread()
            self.serial_worker = SerialWorker(
                port=port_name, baudrate=baudrate)
            self.serial_worker.moveToThread(self.serial_thread)

            self.serial_thread.started.connect(
                self.serial_worker.start_listening)
            self.serial_worker.data_received.connect(
                self._on_serial_data_received)
            self.serial_worker.status_changed.connect(
                self._on_serial_status_changed)
            self.serial_worker.error_occurred.connect(self._on_serial_error)

            # Bind send data signal from GUI thread to Serial worker thread
            self.send_serial_signal.connect(self.serial_worker.send_data)

            self.serial_thread.start()
        else:
            if self.serial_worker:
                self.serial_worker.stop_listening()
            if self.serial_thread:
                self.serial_thread.quit()
                self.serial_thread.wait()

    @Slot(bytes)
    def _on_serial_data_received(self, data: bytes) -> None:
        if self.chk_hex_view.isChecked():
            formatted_text = " ".join(f"{b:02X}" for b in data) + " "
        else:
            formatted_text = data.decode("utf-8", errors="replace")

        # Move cursor to end and insert text
        cursor = self.txt_serial_console.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(formatted_text)

        if self.chk_autoscroll.isChecked():
            self.txt_serial_console.verticalScrollBar().setValue(
                self.txt_serial_console.verticalScrollBar().maximum()
            )

    @Slot(bool, str)
    def _on_serial_status_changed(self, connected: bool, message: str) -> None:
        self.is_serial_connected = connected
        self._append_serial_system_msg(f"[STATUS] {message}")

        if connected:
            self.btn_connect_serial.setText("Disconnect")
            self.btn_connect_serial.setStyleSheet(
                "background-color: #C0392B; color: white; font-weight: bold;"
            )
            self.combo_ports.setEnabled(False)
            self.combo_baud.setEnabled(False)
            self.btn_refresh_ports.setEnabled(False)
        else:
            self.btn_connect_serial.setText("Connect")
            self.btn_connect_serial.setStyleSheet(
                "background-color: #2980B9; color: white; font-weight: bold;"
            )
            self.combo_ports.setEnabled(True)
            self.combo_baud.setEnabled(True)
            self.btn_refresh_ports.setEnabled(True)

    @Slot(str)
    def _on_serial_error(self, err_msg: str) -> None:
        self._append_serial_system_msg(f"[ERROR] {err_msg}")

    def _append_serial_system_msg(self, msg: str) -> None:
        self.txt_serial_console.append(f"\n--- {msg} ---")
        self.txt_serial_console.verticalScrollBar().setValue(
            self.txt_serial_console.verticalScrollBar().maximum()
        )

    def _send_serial_message(self) -> None:
        if not self.is_serial_connected:
            QMessageBox.warning(
                self, "Warning", "Please connect to a COM port first.")
            return

        text = self.txt_send_data.text()
        if not text:
            return

        try:
            if self.chk_hex_view.isChecked():
                clean_hex = text.replace(" ", "").replace("0x", "")
                data_bytes = bytes.fromhex(clean_hex)
            else:
                data_bytes = (text + "\r\n").encode("utf-8")

            self.send_serial_signal.emit(data_bytes)
            self._append_serial_system_msg(f"[TX] {text}")
            self.txt_send_data.clear()

        except ValueError:
            QMessageBox.critical(
                self, "Error", "Invalid HEX string format. Use hexadecimal characters only."
            )

    @Slot()
    def on_refresh_target_clicked(self) -> None:
        """Triggers non-blocking target SWD probe safely using a dynamic worker."""
        self.btn_refresh_target.setEnabled(False)
        self.lbl_target_id.setText("Target ID: Probing...")
        self.lbl_target_id.setStyleSheet(
            "color: #F39C12; font-weight: bold;")

        self._refresh_thread = QThread()
        self._refresh_worker = FlashWorker()
        self._refresh_worker.moveToThread(self._refresh_thread)

        self._refresh_worker.log_signal.connect(self._append_flash_log)
        self._refresh_worker.target_info_signal.connect(
            self.on_target_info_received)

        self._refresh_thread.started.connect(
            self._refresh_worker.check_target_connection)
        self._refresh_worker.target_info_signal.connect(
            self._refresh_thread.quit)
        self._refresh_worker.target_info_signal.connect(
            self._refresh_worker.deleteLater)
        self._refresh_thread.finished.connect(self._refresh_thread.deleteLater)

        self._refresh_thread.start()

    @Slot(dict)
    def on_target_info_received(self, info: dict) -> None:
        """
        Updates the UI label with chip part number and IDCODE/DPIDR.
        """
        self.btn_refresh_target.setEnabled(True)
        if info.get("success"):
            part_num = info.get("part_number", "ARM_MCU")
            dpidr = info.get("dpidr", "0x2BA01477")
            self.lbl_target_id.setText(f"Target: {part_num} | ID: {dpidr}")
            self.lbl_target_id.setStyleSheet(
                "color: #2ECC71; font-weight: bold;")
        else:
            self.lbl_target_id.setText("Target ID: No Target / SWD Error")
            self.lbl_target_id.setStyleSheet(
                "color: #E74C3C; font-weight: bold;")

    def closeEvent(self, event) -> None:
        """Safely clean up background threads before exiting application."""
        if self.is_serial_connected and self.serial_worker:
            self.serial_worker.stop_listening()
        if self.serial_thread and self.serial_thread.isRunning():
            self.serial_thread.quit()
            self.serial_thread.wait()
        if self.flash_thread and self.flash_thread.isRunning():
            self.flash_thread.quit()
            self.flash_thread.wait()
        super().closeEvent(event)
