"""
Provisioning Service for Production Programmer.
Handles Serial Number auto-incrementing, UID formatting, and payload generation.
"""

from typing import List
from src.common import get_logger

logger = get_logger("ProvisioningService")


class ProvisioningService:
    """
    Manages serial number generation and formatting for STM32 production line injection.
    """

    def __init__(self, prefix: str = "BLINK-", start_counter: int = 1, padding: int = 4):
        self.prefix = prefix
        self.current_counter = start_counter
        self.padding = padding

    def get_current_serial_string(self) -> str:
        """
        Returns the formatted serial number string (e.g., 'BLINK-0001').
        """
        number_str = str(self.current_counter).zfill(self.padding)
        return f"{self.prefix}{number_str}"

    def increment(self) -> str:
        """
        Increments the internal counter and returns the new serial string.
        """
        self.current_counter += 1
        serial = self.get_current_serial_string()
        logger.info(f"Serial number incremented to: {serial}")
        return serial

    def build_serial_payload(self, max_length: int = 32) -> List[int]:
        """
        Converts the current serial number string into a fixed-length byte array
        padded with 0x00 (Null terminator) for clean memory inspection.
        """
        serial_str = self.get_current_serial_string()
        raw_bytes = list(serial_str.encode("ascii", errors="ignore"))

        if len(raw_bytes) > max_length:
            logger.warning(
                f"Serial '{serial_str}' truncated to fit {max_length} bytes."
            )
            raw_bytes = raw_bytes[:max_length]
        else:
            # Pad with zeros to keep fixed memory length
            raw_bytes.extend([0x00] * (max_length - len(raw_bytes)))

        return raw_bytes

    @staticmethod
    def format_96bit_uid(raw_words: List[int]) -> str:
        """
        Formats three 32-bit words read from STM32 Unique ID register
        into an industrial canonical hex string (e.g., '003C0020-31385108-36383336').
        """
        if len(raw_words) < 3:
            return "UNKNOWN-UID"

        # Format as uppercase hex with hyphen separation
        return f"{raw_words[0]:08X}-{raw_words[1]:08X}-{raw_words[2]:08X}"
