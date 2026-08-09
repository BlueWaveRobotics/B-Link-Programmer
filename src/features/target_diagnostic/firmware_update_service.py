"""
B-Link Probe Firmware Update Service.
Handles detection of DAPLink Maintenance drive and firmware binary injection.
"""

import os
import shutil
import psutil
from src.common import get_logger
import json
import urllib.request
import tempfile


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

    @classmethod
    def update_firmware_online(cls, config_path: str = "update_config.json") -> tuple[bool, str]:
        """
        Reads URL from JSON config, downloads the latest firmware to a temp folder,
        and flashes it directly to the probe.
        """
        # ۱. خواندن فایل JSON و استخراج لینک
        try:
            logger.info(f"Reading update config from {config_path}...")
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            url = config.get("firmware_url")
            if not url:
                return False, "Firmware URL is missing in the config file."
        except Exception as e:
            logger.error(f"Config read error: {e}")
            return False, f"Failed to read configuration JSON: {str(e)}"

        # ۲. دانلود فایل باینری از سرور
        temp_bin_path = ""
        try:
            logger.info(f"Downloading firmware from {url}...")
            # ساخت یک فایل موقت برای ذخیره دانلود
            fd, temp_bin_path = tempfile.mkstemp(suffix=".bin")
            os.close(fd)  # بستن هندلر تا urllib بتواند روی آن بنویسد

            # دانلود فایل و ذخیره در مسیر موقت
            urllib.request.urlretrieve(url, temp_bin_path)
            logger.info("Download completed successfully.")

        except Exception as e:
            logger.error(f"Download error: {e}")
            return False, f"Failed to download firmware from server.\nPlease check your internet connection.\nError: {str(e)}"

        # ۳. استفاده از متد قبلی برای ریختن فایل دانلود شده روی پروگرمر
        success, message = cls.update_firmware(temp_bin_path)

        # ۴. پاک‌سازی فایل موقت دانلود شده از روی سیستم کاربر
        try:
            if os.path.exists(temp_bin_path):
                os.remove(temp_bin_path)
        except Exception as e:
            logger.warning(f"Could not delete temp file: {e}")

        return success, message
