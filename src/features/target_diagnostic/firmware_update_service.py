"""
B-Link Probe Firmware Update Service.
Flow: B-LINK drive -> START_BL.ACT -> MAINTENANCE -> validate -> copy -> verify.
"""

from PySide6.QtCore import QThread, Signal
import os
import time
import json
import struct
import tempfile
import urllib.request
import shutil
import psutil
import ctypes
import ssl

# ─── این مقادیر را دقیقاً مطابق daplink_addr.h پروژه‌ی فریمورت تنظیم کن ───
IF_ROM_START = 0x08003000   # DAPLINK_ROM_IF_START
IF_ROM_END = 0x08010000   # انتهای فلش (F103RB=128K -> 0x08020000 و ...)
RAM_START = 0x20000000
RAM_END = 0x20005000   # F103CB/RB = 20KB


class ProbeFirmwareUpdateService:

    # ────────────────────────── تشخیص درایو ──────────────────────────
    @staticmethod
    def get_drive_info() -> tuple[str | None, str]:
        """Returns (drive_path, mode): mode in {'MAINTENANCE', 'B-LINK', 'NONE'}"""
        for partition in psutil.disk_partitions():
            if 'cdrom' in partition.opts or partition.fstype == '':
                continue
            drive_path = partition.mountpoint

            if os.name == 'nt':
                buf = ctypes.create_unicode_buffer(1024)
                try:
                    ctypes.windll.kernel32.GetVolumeInformationW(
                        ctypes.c_wchar_p(drive_path), buf,
                        ctypes.sizeof(buf), None, None, None, None, 0)
                    vol = buf.value.upper()
                    if "MAINTENANCE" in vol:
                        return drive_path, "MAINTENANCE"
                    if any(k in vol for k in ("B-LINK", "B_LINK", "BLINK", "DAPLINK")):
                        return drive_path, "B-LINK"
                except Exception:
                    pass

            details = os.path.join(drive_path, "DETAILS.TXT")
            if os.path.exists(details):
                try:
                    with open(details, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read().upper()
                    if "BOOTLOADER" in content.split("DAPLINK MODE:")[-1][:40] \
                       or "MAINTENANCE" in content:
                        return drive_path, "MAINTENANCE"
                    return drive_path, "B-LINK"
                except Exception:
                    pass
        return None, "NONE"

    @classmethod
    def _wait_for_mode(cls, target_mode: str, timeout: float) -> str | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            drive, mode = cls.get_drive_info()
            if mode == target_mode:
                time.sleep(1.0)          # فرصت پایدار شدن mount
                return drive
            time.sleep(0.5)
        return None

    # ─────────────────── سوییچ نرم‌افزاری به بوت‌لودر ───────────────────
    @classmethod
    def ensure_maintenance_mode(cls) -> tuple[str | None, str]:
        drive, mode = cls.get_drive_info()

        if mode == "MAINTENANCE":
            return drive, "MAINTENANCE"

        if mode == "B-LINK" and drive:
            print(
                ">>> [SERVICE] Sending START_BL.ACT (standard DAPLink trigger)...")
            try:
                path = os.path.join(drive, "START_BL.ACT")
                with open(path, "wb") as f:
                    f.write(b"")
                    f.flush()
                    os.fsync(f.fileno())
            except Exception as e:
                # قطع شدن ناگهانی درایو حین ریبوت طبیعی است
                print(f">>> [SERVICE] (expected) write interrupted: {e}")

            m_drive = cls._wait_for_mode("MAINTENANCE", timeout=15)
            if m_drive:
                print(f">>> [SERVICE] MAINTENANCE mode at [{m_drive}]")
                return m_drive, "MAINTENANCE"
            return drive, "B-LINK"

        return None, "NONE"

    # ───────────────────── اعتبارسنجی فایل فریمور ─────────────────────
    @staticmethod
    def validate_firmware_file(path: str) -> tuple[bool, str]:
        size = os.path.getsize(path)
        with open(path, 'rb') as f:
            head = f.read(512)

        if head[:1] == b':':
            return True, "hex"
        if head.lstrip()[:1] in (b'<', b'{'):
            return False, "Server returned an HTML/JSON page instead of binary."
        if head[:2] == b'\x1f\x8b':
            return False, "Server returned gzip data. Check server config."
        if size < 1024:
            return False, f"File too small ({size} bytes) — download is broken."

        sp, pc = struct.unpack('<II', head[:8])
        if not (RAM_START < sp <= RAM_END):
            return False, f"Invalid initial SP 0x{sp:08X}. Bootloader will reject this."
        if not (IF_ROM_START <= (pc & ~1) < IF_ROM_END):
            return False, (f"Reset vector 0x{pc:08X} points outside interface region "
                           f"(expected >= 0x{IF_ROM_START:08X}). The server file is a "
                           f"STANDALONE image — upload the *_if_crc.bin build instead.")
        return True, "bin"

    # ─────────────────── تایید نتیجه‌ی واقعی فلش ───────────────────
    @classmethod
    def verify_flash_result(cls, timeout: float = 30) -> tuple[bool, str]:
        time.sleep(4)  # فرصت flash + remount
        deadline = time.time() + timeout
        while time.time() < deadline:
            drive, mode = cls.get_drive_info()
            if mode == "B-LINK":
                return True, "Probe rebooted to interface mode — update verified."
            if mode == "MAINTENANCE" and drive:
                fail = os.path.join(drive, "FAIL.TXT")
                if os.path.exists(fail):
                    try:
                        with open(fail, "r", errors="ignore") as f:
                            return False, f"Bootloader rejected firmware:\n{f.read().strip()}"
                    except Exception:
                        pass
            time.sleep(1.5)
        return False, "Timeout: probe did not reboot to interface mode."

    # ───────────────────────── فرایند اصلی ─────────────────────────
    @classmethod
    def update_firmware_online(
        cls,
        remote_config_url: str = "https://www.bluewaverobotics.ir/app_config.json",
        progress_cb=None,
    ) -> tuple[bool, str]:

        def report(msg):
            print(f">>> [SERVICE] {msg}")
            if progress_cb:
                progress_cb(msg)

        report("Step 1/6: Checking probe mode...")
        drive, mode = cls.ensure_maintenance_mode()
        if not drive:
            return False, "B-Link probe not found. Please connect it via USB."
        if mode != "MAINTENANCE":
            return False, (
                "Could not switch probe to MAINTENANCE mode.\n\n"
                "The firmware on this probe does not handle START_BL.ACT, or the "
                "bootloader ignores the hold_in_bl flag.\n"
                "Flash the probe once with ST-Link using the corrected build.")

        report("Step 2/6: Fetching server config...")
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(context=cls._ssl_ctx()))
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                   'Accept-Encoding': 'identity'}
        try:
            req = urllib.request.Request(remote_config_url, headers=headers)
            with opener.open(req, timeout=10) as r:
                cfg = json.loads(r.read().decode('utf-8'))
            sec = cfg.get("BLink_firmware", {})
            url = sec.get("firmware_url")
            version = sec.get("latest_version") or sec.get(
                "lstest_version", "v1.0.0")
            if not url:
                return False, "firmware_url missing in server JSON."
        except Exception as e:
            return False, f"Network error while fetching config:\n{e}"

        report(f"Step 3/6: Downloading firmware {version}...")
        suffix = ".hex" if url.lower().endswith(".hex") else ".bin"
        fd, temp_path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        try:
            req = urllib.request.Request(url, headers=headers)
            with opener.open(req, timeout=60) as r, open(temp_path, 'wb') as out:
                shutil.copyfileobj(r, out)
        except Exception as e:
            cls._cleanup(temp_path)
            return False, f"Firmware download failed:\n{e}"

        report("Step 4/6: Validating firmware image...")
        ok, kind = cls.validate_firmware_file(temp_path)
        if not ok:
            # فایل را برای بازرسی نگه می‌داریم
            return False, f"Firmware validation FAILED:\n{kind}\n\nTemp file kept at:\n{temp_path}"

        report("Step 5/6: Copying to MAINTENANCE drive...")
        try:
            dest = os.path.join(drive, "firmware" + suffix)
            with open(temp_path, 'rb') as src, open(dest, 'wb') as dst:
                shutil.copyfileobj(src, dst)
                dst.flush()
                os.fsync(dst.fileno())
        except Exception as e:
            # قطع درایو وسط کپی می‌تواند یعنی فلش شروع شده؛ ادامه به verify
            print(f">>> [SERVICE] copy interrupted (may be normal): {e}")
        finally:
            cls._cleanup(temp_path)

        report("Step 6/6: Verifying flash result...")
        ok, msg = cls.verify_flash_result()
        if ok:
            return True, f"✔ B-Link probe updated to {version}!\n{msg}"
        return False, msg

    # ───────────────────────── helpers ─────────────────────────
    @staticmethod
    def _ssl_ctx():
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    @staticmethod
    def _cleanup(path):
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
