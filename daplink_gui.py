import sys
import os
import logging
from typing import Optional, List
from PySide6.QtCore import Qt, QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog, QProgressBar,
    QTextEdit, QGroupBox, QMessageBox, QTabWidget, QComboBox,
    QCheckBox
)

import serial
import serial.tools.list_ports
from pyocd.core.helpers import ConnectHelper
from pyocd.flash.file_programmer import FileProgrammer

# Configure Python logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DAPLinkSuite")


# =====================================================================
# Worker 1: SWD / pyOCD Flash Programmer Worker
# =====================================================================
class FlashWorker(QObject):
    """
    Background worker for executing pyOCD flash programming and diagnostics
    in a dedicated QThread to prevent GUI freezing.
    """
    log_signal = Signal(str)
    progress_signal = Signal(int)
    finished_signal = Signal(bool, str)

    def __init__(
        self,
        file_path: str,
        target_type: str = "stm32f103c8",
        clock_freq: int = 100000,
        connect_mode: str = "under-reset"
    ):
        super().__init__()
        self.file_path = file_path
        self.target_type = target_type
        self.clock_freq = clock_freq
        self.connect_mode = connect_mode
        self._is_running = True

    def _progress_callback(self, progress: float) -> None:
        if self._is_running:
            percent = int(progress * 100)
            self.progress_signal.emit(percent)

    @Slot()
    def run_production_flash(self) -> None:
        session = None
        try:
            self.log_signal.emit(
                f"[INFO] Starting Production Mode for file: {os.path.basename(self.file_path)}")
            self.log_signal.emit(
                f"[INFO] Connecting to target '{self.target_type}' @ {self.clock_freq//1000} kHz...")

            options = {
                'connect_mode': self.connect_mode,
                'frequency': self.clock_freq,
                'target_override': self.target_type,
                'reset_type': 'hw' if self.connect_mode == 'under-reset' else 'sw',
                'resume_on_disconnect': False
            }

            try:
                session = ConnectHelper.session_with_chosen_probe(
                    options=options)
                session.open()
            except Exception as e:
                if "not recognized" in str(e).lower() and self.target_type != "cortex_m":
                    self.log_signal.emit(
                        "[WARNING] Target pack not found. Falling back to 'cortex_m'...")
                    options['target_override'] = "cortex_m"
                    session = ConnectHelper.session_with_chosen_probe(
                        options=options)
                    session.open()
                else:
                    raise e

            self.log_signal.emit(
                "[INFO] SWD Connection established successfully.")
            dpidr = session.probe.read_dp(0x0)
            self.log_signal.emit(f"[INFO] Read DP IDCODE: 0x{dpidr:08X}")

            self.log_signal.emit(
                "[INFO] Initializing Flash Erase, Program, and Verify sequence...")
            self.progress_signal.emit(0)

            programmer = FileProgrammer(
                session,
                progress=self._progress_callback,
                chip_erase="sector"
            )
            programmer.program(self.file_path)

            self.progress_signal.emit(100)
            self.log_signal.emit(
                "[INFO] ✔ Flash Program & Verify completed successfully!")

            self.log_signal.emit(
                "[INFO] Resetting target core to run application...")
            session.target.reset_and_halt()
            session.target.resume()
            self.log_signal.emit("[INFO] Target MCU is now running.")

            self.finished_signal.emit(
                True, "Production flash sequence completed successfully.")

        except Exception as e:
            error_msg = f"Flash operation failed: {str(e)}"
            self.log_signal.emit(f"[ERROR] {error_msg}")
            self.finished_signal.emit(False, error_msg)

        finally:
            if session:
                try:
                    session.close()
                    self.log_signal.emit("[INFO] SWD session closed.")
                except Exception:
                    pass


# =====================================================================
# Worker 2: CDC Virtual COM Port (Serial) Worker
# =====================================================================
class SerialWorker(QObject):
    """
    Background worker for continuous asynchronous serial port monitoring
    without blocking the main GUI thread.
    """
    data_received = Signal(bytes)
    status_changed = Signal(bool, str)
    error_occurred = Signal(str)

    def __init__(self, port: str, baudrate: int):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.serial_inst: Optional[serial.Serial] = None
        self._is_running = False

    @Slot()
    def start_listening(self) -> None:
        try:
            self.serial_inst = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=0.1
            )
            self._is_running = True
            self.status_changed.emit(
                True, f"Connected to {self.port} @ {self.baudrate} bps")

            while self._is_running and self.serial_inst and self.serial_inst.is_open:
                if self.serial_inst.in_waiting > 0:
                    data = self.serial_inst.read(self.serial_inst.in_waiting)
                    if data:
                        self.data_received.emit(data)

        except Exception as e:
            self.error_occurred.emit(str(e))
            self.status_changed.emit(False, f"Connection error: {str(e)}")
            self.stop_listening()

    @Slot()
    def send_data(self, data: bytes) -> None:
        if self.serial_inst and self.serial_inst.is_open:
            try:
                self.serial_inst.write(data)
            except Exception as e:
                self.error_occurred.emit(f"Write failed: {str(e)}")

    @Slot()
    def stop_listening(self) -> None:
        self._is_running = False
        if self.serial_inst and self.serial_inst.is_open:
            try:
                self.serial_inst.close()
            except Exception:
                pass
        self.status_changed.emit(False, "Disconnected")


# =====================================================================
# Main GUI Application Window (Multi-Tabbed Suite)
# =====================================================================
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

        # Target Config
        config_group = QGroupBox("Hardware & Target Configuration")
        config_layout = QHBoxLayout()
        config_layout.addWidget(QLabel("Target: STM32F103C8"))
        config_layout.addWidget(QLabel("SWD Clock: 100 kHz"))
        config_layout.addWidget(QLabel("Mode: Under-Reset"))
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

        # Action Button
        self.btn_production_flash = QPushButton("ONE-CLICK PRODUCTION FLASH")
        self.btn_production_flash.setMinimumHeight(45)
        self.btn_production_flash.setStyleSheet(
            "background-color: #2E8B57; color: white; font-weight: bold; font-size: 13px;"
        )
        self.btn_production_flash.clicked.connect(self._start_production_flash)
        layout.addWidget(self.btn_production_flash)

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
            "[SYSTEM] DAPLink Production GUI Initialized. Ready for firmware deployment.")

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
            ["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"])
        self.combo_baud.setCurrentText("115200")
        serial_config_layout.addWidget(self.combo_baud)

        self.btn_connect_serial = QPushButton("Connect")
        self.btn_connect_serial.setStyleSheet(
            "background-color: #2980B9; color: white; font-weight: bold;")
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
            self.log_viewer.verticalScrollBar().maximum())

    def _start_production_flash(self) -> None:
        file_path = self.txt_filepath.text().strip()
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(
                self, "Invalid File", "Please select a valid .hex or .bin firmware file first.")
            return

        self.btn_production_flash.setEnabled(False)
        self.progress_bar.setValue(0)
        self._append_flash_log("-" * 65)
        self._append_flash_log(
            "[SYSTEM] Launching SWD/pyOCD background worker thread...")

        self.flash_thread = QThread()
        self.flash_worker = FlashWorker(
            file_path=file_path,
            target_type="stm32f103c8",
            clock_freq=100000,
            connect_mode="under-reset"
        )
        self.flash_worker.moveToThread(self.flash_thread)

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

    @Slot(bool, str)
    def _on_flash_finished(self, success: bool, message: str) -> None:
        self.btn_production_flash.setEnabled(True)
        self._append_flash_log("-" * 65)
        if success:
            QMessageBox.information(
                self, "Success", "Firmware successfully flashed and target is running!")
        else:
            QMessageBox.critical(self, "Flash Failure",
                                 f"Operation failed:\n{message}")

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
                "background-color: #C0392B; color: white; font-weight: bold;")
            self.combo_ports.setEnabled(False)
            self.combo_baud.setEnabled(False)
            self.btn_refresh_ports.setEnabled(False)
        else:
            self.btn_connect_serial.setText("Connect")
            self.btn_connect_serial.setStyleSheet(
                "background-color: #2980B9; color: white; font-weight: bold;")
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
                # Clean space-separated hex strings like '48 65 6C 6C 6F'
                clean_hex = text.replace(" ", "").replace("0x", "")
                data_bytes = bytes.fromhex(clean_hex)
            else:
                data_bytes = (text + "\r\n").encode("utf-8")

            self.send_serial_signal.emit(data_bytes)
            self._append_serial_system_msg(f"[TX] {text}")
            self.txt_send_data.clear()

        except ValueError:
            QMessageBox.critical(
                self, "Error", "Invalid HEX string format. Use hexadecimal characters only.")

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


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
