import logging
from typing import Optional

# PySide6 Thread & Signal tools
from PySide6.QtCore import QObject, Signal, Slot

# PySerial library
import serial

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
