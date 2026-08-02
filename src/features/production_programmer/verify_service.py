"""
Firmware verification service for validation of programmed target flash memory
against original binary or hex file data.
"""

import os
from typing import Optional, Callable
from pyocd.core.session import Session
from pyocd.flash.file_programmer import FileProgrammer

from src.common import get_logger

logger = get_logger("VerifyService")


class VerifyService:
    """
    Dedicated verification service to ensure programmed firmware integrity
    by comparing target MCU flash contents against the source binary/hex image.
    """

    @staticmethod
    def verify_firmware(
        session: Session,
        file_path: str,
        file_format: Optional[str] = None,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> bool:
        """
        Executes verification sequence on an active pyOCD session.

        :param session: Active open pyOCD Session instance.
        :param file_path: Absolute path to firmware file (.hex / .bin).
        :param file_format: Explicit file format ('hex' or 'bin'), auto-detected if None.
        :param progress_callback: Optional callback receiving percentage values (0-100).
        :return: True if flash contents match file image exactly, False otherwise.
        """
        if not session or not session.is_open:
            logger.error(
                "Cannot verify firmware: Active SWD session is required.")
            return False

        if not os.path.exists(file_path):
            logger.error(f"Verification target file not found: {file_path}")
            return False

        try:
            logger.info("Initializing firmware verification routine...")

            def _internal_progress(value: float) -> None:
                if progress_callback:
                    percent = max(0, min(int(value * 100), 100))
                    progress_callback(percent)

            # Create programmer instance configured strictly for verification
            programmer = FileProgrammer(
                session,
                progress=_internal_progress,
                chip_erase="sector",
            )

            # Execute programmatic verification against flash memory
            programmer.program(
                file_path,
                file_format=file_format,
                verify=True,
            )

            logger.info(
                "✔ Firmware verification PASSED: Memory contents match source image.")
            return True

        except Exception as exc:
            logger.error(f"Firmware verification FAILED: {str(exc)}")
            return False
