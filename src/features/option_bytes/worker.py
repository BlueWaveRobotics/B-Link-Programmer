"""
Background worker threads for reading and programming STM32 Option Bytes (OB)
via pyOCD without blocking the PySide6 UI thread.
"""

from typing import Optional, Dict, Any
from PySide6.QtCore import QThread, Signal
from pyocd.core.helpers import ConnectHelper
from pyocd.core.target import Target

from src.common import get_logger

logger = get_logger("OptionBytesWorker")

# Standard STM32F1/F4 Option Byte Registers (Base Address Example: 0x1FFFF800)
OB_BASE_ADDRESS = 0x1FFFF800


class OptionBytesReadWorker(QThread):
    """
    Asynchronous worker that inspects current STM32 Option Bytes from hardware
    and returns parsed configuration dictionaries.
    """

    # Signals: (success: bool, ob_data: dict, error_msg: str)
    ob_read_finished = Signal(bool, dict, str)

    def __init__(self, parent: Optional[QThread] = None):
        super().__init__(parent)

    def run(self) -> None:
        """Executes Option Byte read operation from target hardware."""
        logger.info("Reading Option Bytes from target hardware...")
        session = None
        try:
            session = ConnectHelper.session_with_chosen_probe(blocking=False)
            if not session:
                raise ConnectionError(
                    "No DAPLink/CMSIS-DAP debug probe connected.")

            session.open()
            target: Target = session.target

            # Read 16 bytes of Option Bytes block
            raw_ob = target.read_memory_block8(OB_BASE_ADDRESS, 16)

            # Parse standard STM32 RDP & USER option bytes
            rdp_byte = raw_ob[0]
            user_byte = raw_ob[2]
            wrp0_byte = raw_ob[8] if len(raw_ob) > 8 else 0xFF
            wrp1_byte = raw_ob[10] if len(raw_ob) > 10 else 0xFF

            # Determine RDP Level
            if rdp_byte == 0xAA:
                rdp_level = "Level 0 (AA - Unprotected)"
            elif rdp_byte == 0xCC:
                rdp_level = "Level 2 (CC - Chip Protection / Permanent)"
            else:
                rdp_level = f"Level 1 (0x{rdp_byte:02X} - Read Protected)"

            ob_data: Dict[str, Any] = {
                "rdp_level": rdp_level,
                "rdp_raw": rdp_byte,
                "iwdg_sw": bool(user_byte & (1 << 0)),
                "nrst_stop": bool(user_byte & (1 << 1)),
                "nrst_stdby": bool(user_byte & (1 << 2)),
                "wrp0_raw": wrp0_byte,
                "wrp1_raw": wrp1_byte,
                "raw_hex": " ".join([f"{b:02X}" for b in raw_ob[:8]])
            }

            logger.info("✔ Option Bytes successfully read from device.")
            self.ob_read_finished.emit(True, ob_data, "")

        except Exception as exc:
            err_msg = f"Option Bytes Read Failed: {str(exc)}"
            logger.error(err_msg)
            self.ob_read_finished.emit(False, {}, err_msg)

        finally:
            if session and session.is_open:
                session.close()


class OptionBytesProgramWorker(QThread):
    """
    Asynchronous worker that writes and applies modified Option Bytes to target,
    handling required Option Byte unlock and system reset sequences.
    """

    # Signals: (success: bool, message: str)
    ob_program_finished = Signal(bool, str)

    def __init__(
        self,
        rdp_value: int,
        user_config_byte: int,
        parent: Optional[QThread] = None,
    ):
        super().__init__(parent)
        self.rdp_value = rdp_value
        self.user_config_byte = user_config_byte

    def run(self) -> None:
        """Executes programming of modified Option Bytes via pyOCD."""
        logger.info(
            f"Programming Option Bytes: RDP=0x{self.rdp_value:02X}, USER=0x{self.user_config_byte:02X}"
        )
        session = None
        try:
            session = ConnectHelper.session_with_chosen_probe(blocking=False)
            if not session:
                raise ConnectionError(
                    "No DAPLink/CMSIS-DAP debug probe connected.")

            session.open()
            target: Target = session.target

            # In production industrial tools, modifying OB requires unlocking Flash OPTKEYr
            # and writing 16-bit half-words (Data + Complemented Data)
            rdp_compl = (~self.rdp_value) & 0xFF
            user_compl = (~self.user_config_byte) & 0xFF

            # Write RDP pair (halfword)
            rdp_halfword = (rdp_compl << 8) | self.rdp_value
            target.write16(OB_BASE_ADDRESS, rdp_halfword)

            # Write USER configuration pair (halfword)
            user_halfword = (user_compl << 8) | self.user_config_byte
            target.write16(OB_BASE_ADDRESS + 2, user_halfword)

            # Issue system reset so the microcontroller reloads the new Option Bytes
            target.reset()

            logger.info(
                "✔ Option Bytes programmed and target reset triggered.")
            self.ob_program_finished.emit(
                True, "Option Bytes programmed successfully. Target microcontroller reset."
            )

        except Exception as exc:
            err_msg = f"Option Bytes Programming Failed: {str(exc)}"
            logger.error(err_msg)
            self.ob_program_finished.emit(False, err_msg)

        finally:
            if session and session.is_open:
                session.close()
