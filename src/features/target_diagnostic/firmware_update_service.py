"""
B-Link Probe Firmware Update Service.
Handles online JSON config parsing, automatic binary downloading,
and flashing via the standard DAPLink MAINTENANCE drive (Drag & Drop).
"""

import os
import json
import tempfile
import urllib.request
import shutil
import psutil
from src.common import get_logger

logger = get_logger("ProbeFirmwareUpdateService")


class ProbeFirmwareUpdateService:
    """
    Automated Online Firmware Update Service for B-Link Probe.
    """

    @staticmethod
    def find_maintenance_drive() -> str | None:
        """
        Scans all mounted partitions to locate the B-Link bootloader drive
        by checking both Volume Label and DAPLink signature files.
        """
        import ctypes  # برای خواندن اسم درایوها در ویندوز

        for partition in psutil.disk_partitions():
            if 'cdrom' in partition.opts or partition.fstype == '':
                continue

            drive_path = partition.mountpoint

            # روش اول: بررسی وجود فایل DETAILS.TXT
            if os.path.exists(os.path.join(drive_path, "DETAILS.TXT")):
                logger.info(
                    f"✔ B-Link drive found via signature file at: {drive_path}")
                return drive_path

            # روش دوم: خواندن اسم درایو (Volume Label) در ویندوز
            if os.name == 'nt':
                volume_name_buffer = ctypes.create_unicode_buffer(1024)
                try:
                    ctypes.windll.kernel32.GetVolumeInformationW(
                        ctypes.c_wchar_p(drive_path),
                        volume_name_buffer,
                        ctypes.sizeof(volume_name_buffer),
                        None, None, None, None, 0
                    )
                    vol_name = volume_name_buffer.value.upper()

                    if "MAINTENANCE" in vol_name or "B-LINK" in vol_name:
                        logger.info(
                            f"✔ B-Link drive found via Volume Name '{vol_name}' at: {drive_path}")
                        return drive_path
                except Exception:
                    pass

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
                "Please hold the RESET button on B-Link probe while connecting USB."
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
                "The B-Link probe will now reboot with the new firmware."
            )

        except Exception as exc:
            logger.error(f"Failed to copy probe firmware: {exc}")
            return False, f"Firmware update failed: {str(exc)}"

    @classmethod
    def update_firmware_online(
        cls,
        remote_config_url: str = "https://www.bluewaverobotics.ir/app_config.json"
    ) -> tuple[bool, str]:
        """
        Fetches online JSON, downloads binary file automatically, and copies it 
        to the MAINTENANCE drive.
        """
        # گام ۱: دریافت فایل JSON از سرور
        try:
            logger.info(
                f"Fetching online update config from: {remote_config_url}")
            req = urllib.request.Request(
                remote_config_url,
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                config_data = response.read().decode('utf-8')
                full_config = json.loads(config_data)

            blink_section = full_config.get("BLink_firmware", {})
            url = blink_section.get("firmware_url")
            version = blink_section.get("lstest_version") or blink_section.get(
                "latest_version", "v1.0.0")

            if not url:
                return False, "Firmware URL is missing inside 'BLink_firmware' section."

            logger.info(f"Found online firmware version {version} at: {url}")

        except Exception as e:
            logger.error(f"Failed to fetch online JSON config: {e}")
            return False, f"Failed to connect to update server.\nPlease check your internet connection.\nError: {str(e)}"

        # گام ۲: دانلود فایل باینری
        temp_bin_path = ""
        try:
            logger.info(
                f"Downloading B-Link interface firmware ({version})...")
            fd, temp_bin_path = tempfile.mkstemp(suffix=".bin")
            os.close(fd)

            bin_req = urllib.request.Request(
                url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(bin_req, timeout=30) as bin_response, open(temp_bin_path, 'wb') as out_file:
                shutil.copyfileobj(bin_response, out_file)

            logger.info("Firmware downloaded successfully.")

        except Exception as e:
            logger.error(f"Download error: {e}")
            return False, f"Failed to download firmware binary from server.\nError: {str(e)}"

        # گام ۳: کپی روی درایو MAINTENANCE
        success, message = cls.update_firmware(temp_bin_path)

        # گام ۴: پاکسازی فایل موقت
        try:
            if os.path.exists(temp_bin_path):
                os.remove(temp_bin_path)
        except Exception as e:
            logger.warning(f"Could not delete temp file: {e}")

        if success:
            return True, f"✔ B-Link Probe updated successfully to version {version}!"
        else:
            return False, message
