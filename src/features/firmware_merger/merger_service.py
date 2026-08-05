"""
Firmware Merging and Memory Offset Patching Service.
Combines multiple binary/hex segments (Bootloader, Application, Data)
into a single unified image file padded with 0xFF bytes.
"""

import os
from typing import List, Tuple, Dict, Any
from src.common import get_logger

logger = get_logger("FirmwareMergerService")


class FirmwareSegment:
    """
    Data model representing a single memory segment (e.g., Bootloader or App).
    """

    def __init__(self, file_path: str, offset_address: int, name: str = ""):
        self.file_path = file_path
        self.offset_address = offset_address
        self.name = name or os.path.basename(file_path)
        self.raw_data: bytes = b""
        self.size_bytes: int = 0
        self._load_file()

    def _load_file(self) -> None:
        """Loads raw byte content from disk."""
        if os.path.exists(self.file_path):
            with open(self.file_path, "rb") as f:
                self.raw_data = f.read()
            self.size_bytes = len(self.raw_data)


class FirmwareMergerService:
    """
    Core engine for merging multiple firmware binary segments into one unified memory image.
    """

    @staticmethod
    def merge_segments(
        segments: List[FirmwareSegment], fill_byte: int = 0xFF
    ) -> Tuple[bytes, int, Dict[str, Any]]:
        """
        Sorts segments by base offset address, calculates total memory span,
        pads unallocated gaps with fill_byte (0xFF), and returns unified bytes.
        """
        if not segments:
            raise ValueError("No firmware segments provided for merging.")

        # Sort segments strictly by offset address
        sorted_segments = sorted(segments, key=lambda s: s.offset_address)

        # Calculate global base address and total span
        base_address = sorted_segments[0].offset_address
        highest_address = max(
            s.offset_address + s.size_bytes for s in sorted_segments)
        total_span = highest_address - base_address

        # Initialize bytearray filled with 0xFF
        merged_buffer = bytearray([fill_byte & 0xFF] * total_span)

        # Overlay each segment onto the buffer
        for seg in sorted_segments:
            buffer_start = seg.offset_address - base_address
            buffer_end = buffer_start + seg.size_bytes
            merged_buffer[buffer_start:buffer_end] = seg.raw_data
            logger.info(
                f"Merged '{seg.name}' ({seg.size_bytes} bytes) @ 0x{seg.offset_address:08X}"
            )

        metadata = {
            "base_address": base_address,
            "highest_address": highest_address,
            "total_size_bytes": total_span,
            "segment_count": len(sorted_segments),
        }

        return bytes(merged_buffer), base_address, metadata

    @staticmethod
    def export_to_file(output_path: str, merged_data: bytes) -> bool:
        """Writes the combined byte array to an output binary file."""
        try:
            with open(output_path, "wb") as f:
                f.write(merged_data)
            logger.info(
                f"✔ Unified binary successfully exported to: {output_path}")
            return True
        except Exception as exc:
            logger.error(f"Failed to export merged binary file: {str(exc)}")
            return False
