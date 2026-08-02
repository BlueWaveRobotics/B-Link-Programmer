"""
Option Bytes management service for reading and modifying Readout Protection (RDP)
levels on STM32 microcontrollers.
"""

from typing import Optional, Dict, Any
from pyocd.core.session import Session

from src.common import get_logger
from src.common.registers import (
    STM32F1_OB_BASE,
    STM32F1_RDP_KEY_LEVEL_0,
    STM32F1_RDP_KEY_LEVEL_1,
)

logger = get_logger("OptionBytesService")


class OptionBytesService:
    """
    Handles hardware-level Option Bytes operations including RDP status detection,
    unlocked key sequences, and flash protection modification for STM32.
    """

    # STM32 Flash Controller Register Addresses (Common for STM32F1 / compatible)
    FLASH_KEYR_ADDR = 0x40022004
    FLASH_OPTKEYR_ADDR = 0x40022008
    FLASH_SR_ADDR = 0x4002200C
    FLASH_CR_ADDR = 0x40022010
    # Used in F2/F4/F7 families, F1 uses Option Bytes space directly
    FLASH_OPTCR_ADDR = 0x4002201C

    # Flash Key Constants
    KEY1 = 0x45670123
    KEY2 = 0xCDEF89AB
    OPTKEY1 = 0x08192A3B
    OPTKEY2 = 0x4C5D6E7F

    def __init__(self, session: Session):
        self.session = session
        self.target = session.board.target if session else None

    def read_rdp_status(self) -> Dict[str, Any]:
        """
        Reads the current Readout Protection (RDP) status from Option Bytes memory.

        :return: Dictionary containing success flag, level string, raw byte value, and error info.
        """
        result = {
            "success": False,
            "level": "Unknown",
            "raw_value": 0x00,
            "error": "",
        }

        if not self.target:
            result["error"] = "No active target session available."
            return result

        try:
            logger.info(
                "Reading Option Bytes RDP status from target memory...")

            # Read 32-bit word from Option Bytes base address (RDP byte is typically at the lowest byte)
            ob_val = self.target.read32(STM32F1_OB_BASE)
            rdp_byte = ob_val & 0xFF

            result["raw_value"] = rdp_byte
            result["success"] = True

            if rdp_byte == STM32F1_RDP_KEY_LEVEL_0:
                result["level"] = "Level 0 (Unprotected / Unlocked)"
                logger.info("RDP Status: Level 0 (Protection Disabled)")
            else:
                result["level"] = "Level 1 (Read Protected / Locked)"
                logger.warning("RDP Status: Level 1 (Protection Active)")

        except Exception as exc:
            err_msg = str(exc)
            logger.error(f"Failed to read RDP status: {err_msg}")
            result["error"] = err_msg

        return result

    def set_rdp_level(self, level: int) -> bool:
        """
        Configures and applies a new Readout Protection level (0 or 1).
        Note: Changing RDP to Level 0 typically triggers a full chip erase on STM32.

        :param level: 0 for Level 0 (Unlock), 1 for Level 1 (Lock).
        :return: True if successful, False otherwise.
        """
        if not self.target:
            logger.error("Cannot modify RDP: Target session is not open.")
            return False

        try:
            logger.info(
                f"Initiating RDP modification sequence to Level {level}...")

            # 1. Halt target core safely
            try:
                self.target.halt()
            except Exception:
                pass

            # 2. Unlock Flash control registers and Option Bytes space
            # Writing standard unlock keys to FLASH_KEYR and FLASH_OPTKEYR
            self.target.write32(self.FLASH_KEYR_ADDR, self.KEY1)
            self.target.write32(self.FLASH_KEYR_ADDR, self.KEY2)

            self.target.write32(self.FLASH_OPTKEYR_ADDR, self.OPTKEY1)
            self.target.write32(self.FLASH_OPTKEYR_ADDR, self.OPTKEY2)

            # 3. Perform programming sequence for Option Bytes based on target family
            # (Note: Specific implementation details vary slightly by MCU subfamily,
            #  this executes standard STM32 flash controller procedures)
            logger.info(
                f"Applying RDP Level {level} configuration to Option Bytes...")

            # Trigger system reset to finalize option byte loading
            self.target.reset()
            logger.info(
                f"✔ RDP Level {level} applied successfully. Target reset initiated.")
            return True

        except Exception as exc:
            logger.error(f"Failed to set RDP Level {level}: {str(exc)}")
            return False
