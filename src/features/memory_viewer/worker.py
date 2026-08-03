"""
Background worker thread for reading raw memory blocks from ARM Cortex-M targets
via pyOCD without blocking the PySide6 UI thread.
"""

from typing import Optional, List
from PySide6.QtCore import QThread, Signal
from pyocd.core.helpers import ConnectHelper
from pyocd.core.target import Target

from src.common import get_logger

logger = get_logger("MemoryReadWorker")


class MemoryReadWorker(QThread):
    """
    Asynchronous worker that reads a block of memory from the target microcontroller
    and emits the raw byte array back to the UI.
    """

    # Signals: (success: bool, start_address: int, data: list[int], error_msg: str)
    memory_read_finished = Signal(bool, int, list, str)

    def __init__(
        self,
        address: int,
        size_bytes: int,
        parent: Optional[QThread] = None,
    ):
        super().__init__(parent)
        self.address = address
        self.size_bytes = size_bytes

    def run(self) -> None:
        """Executes the memory block read operation using pyOCD."""
        logger.info(
            f"Starting memory read: Addr=0x{self.address:08X}, Size={self.size_bytes} bytes"
        )
        session = None
        try:
            # Connect to the primary DAPLink probe
            session = ConnectHelper.session_with_chosen_probe(blocking=False)
            if not session:
                raise ConnectionError(
                    "No DAPLink/CMSIS-DAP debug probe connected.")

            session.open()
            target: Target = session.target

            # Read raw 8-bit memory block from hardware
            raw_data: List[int] = target.read_memory_block8(
                self.address, self.size_bytes
            )

            logger.info("✔ Memory block read successfully from target.")
            self.memory_read_finished.emit(True, self.address, raw_data, "")

        except Exception as exc:
            err_msg = f"Memory Read Failed: {str(exc)}"
            logger.error(err_msg)
            self.memory_read_finished.emit(False, self.address, [], err_msg)

        finally:
            if session and session.is_open:
                session.close()
