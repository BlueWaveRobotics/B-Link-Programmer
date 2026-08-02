"""
UI component for CDC Serial Monitor.
Provides interactive controls for COM port enumeration, baud rate selection,
HEX/ASCII formatting, auto-scroll console display, and data transmission.
"""

from typing import Optional
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QPushButton,
    QLabel,
    QLineEdit,
    QTextEdit,
    QComboBox,
    QCheckBox,
    QMessageBox,
)
import serial.tools.list_ports

from src.common import get_logger
from src.features.serial_monitor.serial_worker import SerialWorker

logger = get_logger("SerialMonitorWidget")


class SerialMonitorWidget(QWidget):
    """
    Industrial UI Widget for monitoring and communicating over virtual COM ports.
    """

    # Thread-safe signal to push TX byte payloads to the SerialWorker thread
    send_serial_signal = Signal(bytes)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.serial_thread: Optional[QThread] = None
        self.serial_worker: Optional[SerialWorker] = None
        self.is_serial_connected = False

        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # -------------------------------------------------------------
        # Port Configuration Top Panel
        # -------------------------------------------------------------
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
            [
                "9600",
                "19200",
                "38400",
                "57600",
                "115200",
                "230400",
                "460800",
                "921600",
            ]
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
        main_layout.addWidget(serial_config_group)

        # -------------------------------------------------------------
        # Display & Scroll Options
        # -------------------------------------------------------------
        opt_layout = QHBoxLayout()
        self.chk_hex_view = QCheckBox("HEX Display Mode")
        self.chk_autoscroll = QCheckBox("Auto-Scroll")
        self.chk_autoscroll.setChecked(True)
        opt_layout.addWidget(self.chk_hex_view)
        opt_layout.addWidget(self.chk_autoscroll)
        opt_layout.addStretch()
        main_layout.addLayout(opt_layout)

        # -------------------------------------------------------------
        # RX/TX Terminal Console
        # -------------------------------------------------------------
        terminal_group = QGroupBox("RX/TX Terminal Console")
        terminal_layout = QVBoxLayout()

        self.txt_serial_console = QTextEdit()
        self.txt_serial_console.setReadOnly(True)
        self.txt_serial_console.setStyleSheet(
            "background-color: #0D1117; color: #E6EDF3; font-family: Consolas, monospace; font-size: 12px;"
        )
        terminal_layout.addWidget(self.txt_serial_console)

        # Data Transmission Field
        send_layout = QHBoxLayout()
        self.txt_send_data = QLineEdit()
        self.txt_send_data.setPlaceholderText(
            "Type string or HEX payload to transmit to target MCU..."
        )
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
        main_layout.addWidget(terminal_group)

        # Populate COM ports on startup
        self._refresh_serial_ports()

    # -----------------------------------------------------------------
    # Port Enumeration & Connection Logic
    # -----------------------------------------------------------------
    def _refresh_serial_ports(self) -> None:
        """Scan system hardware for active COM / ttyACM / ttyUSB devices."""
        self.combo_ports.clear()
        ports = serial.tools.list_ports.comports()
        if not ports:
            self.combo_ports.addItem("No COM ports detected")
            return

        for p in sorted(ports, key=lambda item: item.device):
            description = f"{p.device} ({p.description})"
            self.combo_ports.addItem(description, p.device)

    def _toggle_serial_connection(self) -> None:
        if not self.is_serial_connected:
            port_name = self.combo_ports.currentData()
            if not port_name:
                QMessageBox.warning(
                    self,
                    "Port Warning",
                    "Please select a valid COM port from the list first.",
                )
                return

            baudrate = int(self.combo_baud.currentText())

            # Launch dedicated background worker and thread
            self.serial_thread = QThread()
            self.serial_worker = SerialWorker(
                port=port_name,
                baudrate=baudrate,
            )
            self.serial_worker.moveToThread(self.serial_thread)

            self.serial_thread.started.connect(
                self.serial_worker.start_listening
            )
            self.serial_worker.data_received.connect(
                self._on_serial_data_received
            )
            self.serial_worker.status_signal.connect(
                self._on_serial_status_changed
            )
            self.serial_worker.error_signal.connect(self._on_serial_error)

            # Bind UI TX signal to thread worker TX slot
            self.send_serial_signal.connect(self.serial_worker.send_data)

            self.serial_thread.start()
        else:
            self._disconnect_serial()

    def _disconnect_serial(self) -> None:
        if self.serial_worker:
            self.serial_worker.stop_listening()
        if self.serial_thread and self.serial_thread.isRunning():
            self.serial_thread.quit()
            self.serial_thread.wait()

    # -----------------------------------------------------------------
    # Signal / Slot Execution Slots
    # -----------------------------------------------------------------
    @Slot(bytes)
    def _on_serial_data_received(self, data: bytes) -> None:
        if self.chk_hex_view.isChecked():
            formatted_text = " ".join(f"{b:02X}" for b in data) + " "
        else:
            formatted_text = data.decode("utf-8", errors="replace")

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
                self,
                "Connection Warning",
                "Please connect to a valid COM port before transmitting.",
            )
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
                self,
                "Format Error",
                "Invalid HEX payload format. Use hexadecimal characters (0-9, A-F) only.",
            )

    def shutdown_threads(self) -> None:
        """Safely terminate COM port connections and background serial threads on application exit."""
        self._disconnect_serial()
