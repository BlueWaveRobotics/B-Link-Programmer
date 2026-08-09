"""
B-Link Probe Firmware Update Service.
Handles detection of DAPLink Maintenance drive and firmware binary injection.
"""

import os
import shutil
import psutil
from src.common import get_logger

logger = get_logger("ProbeFirmwareUpdateService")


class ProbeFirmwareUpdateService:
    """
    Service for updating B-Link Probe firmware via DAPLink Mass Storage Bootloader.
    """

    @staticmethod
    def find_maintenance_drive() -> str | None:
        """
        Scans all mounted partitions to locate the DAPLink bootloader drive.
        """
        for partition in psutil.disk_partitions():
            mount_point = partition.mountpoint.upper()
            if "MAINTENANCE" in mount_point or "B-LINK" in mount_point:
                logger.info(
                    f"DAPLink Maintenance drive detected at: {partition.mountpoint}")
                return partition.mountpoint
        return None

    @classmethod
    def update_firmware(cls, firmware_path: str) -> tuple[bool, str]:
        """
        Copies the provided firmware binary into the probe's maintenance drive.
        """
        if not os.path.exists(firmware_path):
            return False, "Selected firmware file does not exist."

        drive = cls.find_maintenance_drive()
        if not drive:
            return (
                False,
                "B-Link Probe Maintenance drive not found.\n"
                "Please hold the RESET button on B-Link probe while connecting USB.",
            )

        try:
            filename = os.path.basename(firmware_path)
            dest_path = os.path.join(drive, filename)

            logger.info(
                f"Copying firmware '{firmware_path}' to '{dest_path}'...")
            shutil.copy2(firmware_path, dest_path)

            return (
                True,
                "✔ Firmware copied successfully!\n"
                "The B-Link probe will now reboot with the new firmware.",
            )

        except Exception as exc:
            logger.error(f"Failed to copy probe firmware: {exc}")
            return False, f"Firmware update failed: {str(exc)}"
