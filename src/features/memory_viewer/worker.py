# """
# Background worker thread for reading raw memory blocks from ARM Cortex-M targets
# via pyOCD (SWD) or Direct USB (DFU) without blocking the PySide6 UI thread.
# """

# from typing import Optional, List
# from PySide6.QtCore import QThread, Signal

# # 🌟 استفاده از SessionManager یکپارچه به جای pyOCD خام
# from src.common import get_logger, SessionManager

# logger = get_logger("MemoryReadWorker")


# class MemoryReadWorker(QThread):
#     """
#     Asynchronous worker that reads a block of memory from the target microcontroller
#     and emits the raw byte array back to the UI.
#     """

#     memory_read_finished = Signal(bool, int, list, str)

#     def __init__(
#         self,
#         address: int,
#         size_bytes: int,
#         interface_type: str = "DAPLink (SWD)",  # ⬅️ اضافه شدن نوع رابط
#         parent: Optional[QThread] = None,
#     ):
#         super().__init__(parent)
#         self.address = address
#         self.size_bytes = size_bytes
#         self.interface_type = interface_type

#     def run(self) -> None:
#         """Executes the memory block read operation using SessionManager."""
#         logger.info(
#             f"Starting memory read: Addr=0x{self.address:08X}, Size={self.size_bytes} bytes via {self.interface_type}"
#         )

#         # ساخت نشست بر اساس انتخاب کاربر (USB یا SWD)
#         sm = SessionManager(
#             interface_type=self.interface_type, connect_mode="attach")

#         try:
#             # 1. تلاش برای اتصال
#             if not sm.connect():
#                 if "USB" in self.interface_type:
#                     raise ConnectionError(
#                         "No STM32 DFU USB device detected. Is BOOT0=1?")
#                 else:
#                     raise ConnectionError(
#                         "No DAPLink/CMSIS-DAP debug probe connected.")

#             # 2. خواندن حافظه (به صورت هوشمند: اگر USB باشد dfu-util اجرا می‌شود، اگر SWD باشد pyOCD)
#             raw_data = sm.read_memory_block8(self.address, self.size_bytes)

#             if not raw_data:
#                 raise ValueError(
#                     "Memory read returned empty data. Check if device is read-protected (RDP Level 1).")

#             logger.info("✔ Memory block read successfully from target.")
#             self.memory_read_finished.emit(True, self.address, raw_data, "")

#         except Exception as exc:
#             exc_str = str(exc).lower()
#             # تشخیص خطای محافظت خواندن (RDP Level 1)
#             if "transferfault" in exc_str or "fault" in exc_str or "ack" in exc_str or "read-protected" in exc_str:
#                 rdp_msg = (
#                     "[READ PROTECTED / RDP LEVEL 1 ACTIVE] "
#                     "Cannot read Flash memory while Read Protection is enabled. "
#                     "Please downgrade RDP to Level 0."
#                 )
#                 logger.warning(f"Memory read blocked by RDP protection: {exc}")
#                 self.memory_read_finished.emit(
#                     False, self.address, [], rdp_msg)
#             else:
#                 err_msg = f"Memory Read Failed: {str(exc)}"
#                 logger.error(err_msg)
#                 self.memory_read_finished.emit(
#                     False, self.address, [], err_msg)

#         finally:
#             sm.close()
"""
Background worker thread for reading raw memory blocks from ARM Cortex-M targets
via pyOCD (SWD) or Direct USB (DFU) without blocking the PySide6 UI thread.
"""

from typing import Optional, List
from PySide6.QtCore import QThread, Signal

# 🌟 استفاده از SessionManager یکپارچه به جای pyOCD خام
from src.common import get_logger, SessionManager

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
        interface_type: str = "B-Link (SWD)",
        probe_id: Optional[str] = None,  # ⬅️ اضافه شدن شناسه یکتای پروب
        parent: Optional[QThread] = None,
    ):
        super().__init__(parent)
        self.address = address
        self.size_bytes = size_bytes
        self.interface_type = interface_type
        self.probe_id = probe_id  # ⬅️ ذخیره شناسه پروب

    def run(self) -> None:
        """Executes the memory block read operation using SessionManager."""
        probe_msg = f" (Probe: {self.probe_id[:8]}...)" if self.probe_id else ""
        logger.info(
            f"Starting memory read: Addr=0x{self.address:08X}, Size={self.size_bytes} bytes via {self.interface_type}{probe_msg}"
        )

        # ⬅️ پاس دادن unique_id به SessionManager برای اتصال به پروگرمر خاص
        sm = SessionManager(
            interface_type=self.interface_type,
            connect_mode="attach",
            unique_id=self.probe_id
        )

        try:
            # 1. تلاش برای اتصال
            if not sm.connect():
                if "USB" in self.interface_type:
                    raise ConnectionError(
                        "No STM32 DFU USB device detected. Is BOOT0=1?")
                else:
                    raise ConnectionError(
                        "No B-Link debug probe connected.")

            # 2. خواندن حافظه (به صورت هوشمند: اگر USB باشد dfu-util اجرا می‌شود، اگر SWD باشد pyOCD)
            raw_data = sm.read_memory_block8(self.address, self.size_bytes)

            if not raw_data:
                raise ValueError(
                    "Memory read returned empty data. Check if device is read-protected (RDP Level 1).")

            logger.info("✔ Memory block read successfully from target.")
            self.memory_read_finished.emit(True, self.address, raw_data, "")

        except Exception as exc:
            exc_str = str(exc).lower()
            # تشخیص خطای محافظت خواندن (RDP Level 1)
            if "transferfault" in exc_str or "fault" in exc_str or "ack" in exc_str or "read-protected" in exc_str:
                rdp_msg = (
                    "[READ PROTECTED / RDP LEVEL 1 ACTIVE] "
                    "Cannot read Flash memory while Read Protection is enabled. "
                    "Please downgrade RDP to Level 0."
                )
                logger.warning(f"Memory read blocked by RDP protection: {exc}")
                self.memory_read_finished.emit(
                    False, self.address, [], rdp_msg)
            else:
                err_msg = f"Memory Read Failed: {str(exc)}"
                logger.error(err_msg)
                self.memory_read_finished.emit(
                    False, self.address, [], err_msg)

        finally:
            sm.close()
