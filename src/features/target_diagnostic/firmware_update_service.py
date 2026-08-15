"""
B-Link Probe Firmware Update Service.
Handles auto-switching from B-LINK to MAINTENANCE mode,
downloading firmware with clean filenames, and copying to drive.
"""

import os
import time
import json
import tempfile
import urllib.request
import shutil
import psutil
import ctypes
import ssl


class ProbeFirmwareUpdateService:
    """
    Automated Online Firmware Update Service for B-Link Probe.
    """

    @staticmethod
    def get_drive_info() -> tuple[str | None, str]:
        """
        Scans drives and returns (drive_path, mode) where mode is 'MAINTENANCE' or 'B-LINK'.
        """
        for partition in psutil.disk_partitions():
            if 'cdrom' in partition.opts or partition.fstype == '':
                continue

            drive_path = partition.mountpoint

            # بررسی Volume Label در ویندوز
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

                    if "MAINTENANCE" in vol_name:
                        return drive_path, "MAINTENANCE"
                    if "B-LINK" in vol_name or "B_LINK" in vol_name or "DAPLINK" in vol_name:
                        return drive_path, "B-LINK"
                except Exception:
                    pass

            # بررسی فایل DETAILS.TXT
            details_path = os.path.join(drive_path, "DETAILS.TXT")
            if os.path.exists(details_path):
                try:
                    with open(details_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read().upper()
                        if "MAINTENANCE" in content:
                            return drive_path, "MAINTENANCE"
                        return drive_path, "B-LINK"
                except Exception:
                    pass

        return None, "NONE"

    @classmethod
    def ensure_maintenance_mode(cls) -> str | None:
        """
        Ensures the probe is in MAINTENANCE mode. If in B-LINK mode, sends Magic File
        to trigger soft-reset into MAINTENANCE.
        """
        drive, mode = cls.get_drive_info()

        if mode == "MAINTENANCE":
            print(
                f">>> [DEBUG-SERVICE] Probe already in MAINTENANCE mode at [{drive}]")
            return drive

        if mode == "B-LINK" and drive:
            print(
                f">>> [DEBUG-SERVICE] Probe in B-LINK mode at [{drive}]. Sending Magic File trigger...")
            magic_files = ["PROBE.ACT", "MODE_TYPE.TXT"]
            for mf in magic_files:
                try:
                    with open(os.path.join(drive, mf), "wb") as f:
                        f.write(b"1")
                except Exception as e:
                    print(f">>> [DEBUG-SERVICE] Warning creating {mf}: {e}")

            print(
                ">>> [DEBUG-SERVICE] Waiting 5 seconds for reboot to MAINTENANCE mode...")
            for _ in range(8):
                time.sleep(1)
                m_drive, m_mode = cls.get_drive_info()
                if m_mode == "MAINTENANCE":
                    print(
                        f">>> [DEBUG-SERVICE] Switched to MAINTENANCE mode at [{m_drive}]!")
                    return m_drive

            # اگر سوئیچ اتوماتیک انجام نشد، همان درایو موجود استفاده می‌شود
            print(
                ">>> [DEBUG-SERVICE] Soft-reset timeout, proceeding with current drive...")
            return drive

        return None

    @classmethod
    def update_firmware_online(
        cls,
        remote_config_url: str = "https://www.bluewaverobotics.ir/app_config.json"
    ) -> tuple[bool, str]:
        """
        Fetches online JSON, downloads binary firmware, and copies it to drive with valid filename.
        """
        print(">>> [DEBUG-SERVICE] Step 1: Checking Probe Drive Mode...")
        drive = cls.ensure_maintenance_mode()

        if not drive:
            return False, "B-Link Probe drive not found!\nPlease connect the probe to USB."

        print(">>> [DEBUG-SERVICE] Step 2: Fetching Server Config...")
        proxy_handler = urllib.request.ProxyHandler({})
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

        opener = urllib.request.build_opener(
            proxy_handler,
            urllib.request.HTTPSHandler(context=ssl_ctx)
        )

        try:
            req = urllib.request.Request(
                remote_config_url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )

            with opener.open(req, timeout=10) as response:
                full_config = json.loads(response.read().decode('utf-8'))

            blink_section = full_config.get("BLink_firmware", {})
            url = blink_section.get("firmware_url")
            version = blink_section.get("lstest_version") or blink_section.get(
                "latest_version", "v1.0.0")

            if not url:
                return False, "Firmware URL missing in server JSON."

            print(
                f">>> [DEBUG-SERVICE] Step 3: Config Parsed (Version {version}).")

        except Exception as e:
            print(f">>> [DEBUG-SERVICE] ERROR fetching JSON: {e}")
            return False, f"Network Connection Error.\nError: {str(e)}"

        # دانلود و کپی با نام فایل استاندارد
        temp_bin_path = ""
        try:
            print(">>> [DEBUG-SERVICE] Step 4: Downloading binary firmware...")
            fd, temp_bin_path = tempfile.mkstemp(suffix=".bin")
            os.close(fd)

            bin_req = urllib.request.Request(
                url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            with opener.open(bin_req, timeout=30) as bin_response, open(temp_bin_path, 'wb') as out_file:
                shutil.copyfileobj(bin_response, out_file)

            # استفاده از نام فایل استاندارد firmware.bin جهت جلوگیری از خطای VFS
            dest_path = os.path.join(drive, "firmware.bin")
            print(
                f">>> [DEBUG-SERVICE] Step 5: Copying '{temp_bin_path}' -> '{dest_path}'...")
            shutil.copy2(temp_bin_path, dest_path)

            print(">>> [DEBUG-SERVICE] Step 6: Copy completed successfully!")

            return True, f"✔ B-Link Probe updated successfully to version {version}!"

        except Exception as e:
            print(f">>> [DEBUG-SERVICE] ERROR during download/copy: {e}")
            return False, f"Failed to update firmware.\nError: {str(e)}"

        finally:
            if temp_bin_path and os.path.exists(temp_bin_path):
                try:
                    os.remove(temp_bin_path)
                except Exception:
                    pass
