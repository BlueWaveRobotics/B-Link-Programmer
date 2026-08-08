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
            # استفاده از حالت attach یا under-reset برای جلوگیری از اجرای ناخواسته کد
            options = {
                "connect_mode": "attach",
                "halt_on_connect": True,
            }
            session = ConnectHelper.session_with_chosen_probe(
                blocking=False,
                options=options
            )
            if not session:
                raise ConnectionError(
                    "No DAPLink/CMSIS-DAP debug probe connected.")

            session.open()
            target: Target = session.target

            # تلاش برای خواندن حافظه از سخت‌افزار
            try:
                raw_data: List[int] = target.read_memory_block8(
                    self.address, self.size_bytes
                )
            except Exception as read_exc:
                # تشخیص خطای محافظت خواندن (RDP Level 1)
                exc_str = str(read_exc).lower()
                if "transferfault" in exc_str or "fault" in exc_str or "ack" in exc_str:
                    rdp_msg = (
                        "[READ PROTECTED / RDP LEVEL 1 ACTIVE] "
                        "Cannot read Flash memory while Read Protection is enabled. "
                        "Please downgrade RDP to Level 0 in Option Bytes tab."
                    )
                    logger.warning(
                        f"Memory read blocked by RDP protection: {read_exc}")
                    self.memory_read_finished.emit(
                        False, self.address, [], rdp_msg)
                    return
                else:
                    raise read_exc

            logger.info("✔ Memory block read successfully from target.")
            self.memory_read_finished.emit(True, self.address, raw_data, "")

        except Exception as exc:
            err_msg = f"Memory Read Failed: {str(exc)}"
            logger.error(err_msg)
            self.memory_read_finished.emit(False, self.address, [], err_msg)

        finally:
            if session and session.is_open:
                try:
                    session.close()
                except Exception:
                    pass
