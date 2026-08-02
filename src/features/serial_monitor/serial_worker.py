"""
Background worker handling continuous asynchronous CDC virtual COM port
communication without blocking or freezing the main application GUI thread.
"""

from typing import Optional, Any
from PySide6.QtCore import Signal, Slot
import serial

from src.common import BaseWorker, get_logger

logger = get_logger("SerialWorker")


class SerialWorker(BaseWorker):
    """
    Dedicated background serial worker responsible for opening hardware COM ports,
    polling RX buffers asynchronously, and writing TX byte payloads.
    """

    # Signal emitted whenever raw byte chunks are received from the MCU
    data_received = Signal(bytes)

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        parent: Optional[Any] = None,
    ):
        super().__init__(parent)
        self.port = port
        self.baudrate = baudrate
        self.serial_inst: Optional[serial.Serial] = None

    @Slot()
    def start_listening(self) -> None:
        """
        Opens the configured COM port and enters an asynchronous polling loop
        to stream incoming serial data to the UI until terminated.
        """
        try:
            logger.info(
                f"Opening CDC serial port {self.port} at {self.baudrate} bps..."
            )
            self.serial_inst = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=0.1,  # Non-blocking timeout allows loop checking
            )
            self._is_running = True
            self.status_signal.emit(
                True, f"Connected to {self.port} @ {self.baudrate} bps"
            )
            logger.info(f"✔ Serial connection established on {self.port}.")

            # Main asynchronous RX polling loop
            while (
                self._is_running
                and self.serial_inst
                and self.serial_inst.is_open
            ):
                if self.serial_inst.in_waiting > 0:
                    data = self.serial_inst.read(self.serial_inst.in_waiting)
                    if data:
                        self.data_received.emit(data)

        except Exception as exc:
            err_msg = str(exc)
            logger.error(f"Serial worker connection error: {err_msg}")
            self.report_error(f"COM Port Error: {err_msg}")
            self.status_signal.emit(
                False, f"Connection terminated: {err_msg}"
            )
        finally:
            self.stop_listening()

    @Slot(bytes)
    def send_data(self, data: bytes) -> None:
        """
        Transmits raw byte payloads to the active target microcontroller.

        :param data: Byte sequence to write over the serial port.
        """
        if self.serial_inst and self.serial_inst.is_open:
            try:
                self.serial_inst.write(data)
                logger.debug(f"Transmitted {len(data)} bytes -> {self.port}")
            except Exception as exc:
                err_msg = f"Serial write failure: {str(exc)}"
                logger.error(err_msg)
                self.report_error(err_msg)
        else:
            logger.warning("Attempted transmission while COM port is closed.")

    @Slot()
    def stop_listening(self) -> None:
        """
        Terminates the RX polling loop and safely releases the COM port resource.
        """
        self._is_running = False
        if self.serial_inst and self.serial_inst.is_open:
            try:
                self.serial_inst.close()
                logger.info(f"Serial port {self.port} closed cleanly.")
            except Exception as exc:
                logger.debug(
                    f"Minor error during serial port close: {str(exc)}")
            finally:
                self.serial_inst = None

        self.status_signal.emit(False, "Disconnected from COM port")
