"""
Background worker executing firmware programming, full chip erasing,
and flash verification sequences in a dedicated asynchronous thread.
Now fully supports BOTH DAPLink(SWD) and Direct USB(DFU) interfaces.
"""

import os
import time
import subprocess
from typing import Optional, Any, List
from PySide6.QtCore import Slot, Signal

from pyocd.flash.file_programmer import FileProgrammer

from src.common import BaseWorker, get_logger, SessionManager
from src.features.production_programmer.verify_service import VerifyService
from src.features.production_programmer.provisioning import ProvisioningService

logger = get_logger("ProductionProgrammerWorker")

DEFAULT_STM32_UID_ADDRESS = 0x1FFFF7E8


class ProductionProgrammerWorker(BaseWorker):
    """
    Worker class responsible for executing Production Flash, Full Chip Erase,
    UID reading, and Serial Provisioning operations via SWD or USB DFU interfaces
    without blocking the GUI thread.
    """

    uid_read_signal = Signal(str)
    cycle_time_signal = Signal(float)

    finished_signal = Signal(bool, str)

    def __init__(
        self,
        file_path: str = "",
        base_address: int = 0x08000000,
        clock_freq: int = 1000000,
        connect_mode: str = "under-reset",
        verify_enabled: bool = True,
        enable_provisioning: bool = False,
        serial_payload: Optional[List[int]] = None,
        serial_address: int = 0x0801FC00,
        interface_type: str = "DAPLink (SWD)",
        parent: Optional[Any] = None,
    ):
        super().__init__(parent)
        self.file_path = file_path
        self.base_address = base_address
        self.clock_freq = clock_freq
        self.connect_mode = connect_mode
        self.verify_enabled = verify_enabled
        self.enable_provisioning = enable_provisioning
        self.serial_payload = serial_payload or []
        self.serial_address = serial_address
        self.interface_type = interface_type

    def _progress_callback(self, progress: float) -> None:
        """Translate pyOCD decimal progress(0.0 - 1.0) to integer percentage(0 - 100)."""
        if self._is_running:
            percent = int(progress * 100)
            self.report_progress(percent)

    @Slot()
    def run_chip_erase(self) -> None:
        """Executes robust full chip erase sequence (SWD or USB DFU)."""
        start_time = time.perf_counter()

        sm = SessionManager(
            connect_mode=self.connect_mode,
            clock_freq=self.clock_freq,
            interface_type=self.interface_type
        )

        try:
            self.log(
                f"[INFO] Starting Full Chip Erase sequence via {self.interface_type}...")

            if not sm.connect():
                raise ConnectionError(
                    f"Failed to connect to target via {self.interface_type}.")

            self.report_progress(10)
            self.log(
                "[INFO] Executing Flash Erase on all memory sectors... Please wait.")

            # ==================================================================
            # بررسی نوع اتصال برای انتخاب روش Erase
            # ==================================================================
            if "USB" in self.interface_type:
                import tempfile
                import subprocess

                self.log(
                    "[INFO] Preparing dummy payload to force DFU Mass Erase...")

                # 1. ساخت یک فایل موقت ۴ بایتی شامل 0xFF (حالت پیش‌فرض فلش)
                fd, temp_path = tempfile.mkstemp(suffix=".bin")
                with os.fdopen(fd, 'wb') as f:
                    f.write(b'\xFF\xFF\xFF\xFF')

                # 2. ارسال فایل موقت با دستور پاکسازی اجباری (mass-erase:force)
                hex_addr = f"0x{self.base_address:08X}"
                cmd = [
                    "dfu-util",
                    "-a", "0",
                    "-s", f"{hex_addr}:mass-erase:force",
                    "-D", temp_path
                ]

                self.log("[INFO] Executing dfu-util mass erase command...")
                result = subprocess.run(cmd, capture_output=True, text=True)

                # 3. حذف فایل موقت از روی سیستم عامل
                os.remove(temp_path)

                # 4. بررسی نتیجه
                if result.returncode != 0:
                    error_details = result.stderr if result.stderr else result.stdout
                    self.log(f"[ERROR] dfu-util output: {error_details}")
                    raise RuntimeError("USB DFU Chip Erase failed.")

            else:
                # منطق قبلی برای حالت SWD (pyOCD)
                if not sm.erase_chip():
                    raise RuntimeError("Chip Erase operation failed.")
            # ==================================================================

            self.report_progress(100)
            elapsed_time = time.perf_counter() - start_time
            self.cycle_time_signal.emit(elapsed_time)

            self.log(
                f"[INFO] ✔ Full Chip Erase completed successfully in {elapsed_time:.2f} s! Memory is now blank.")
            self.finished_signal.emit(
                True, "Full Chip Erase completed successfully.")

        except Exception as exc:
            elapsed_time = time.perf_counter() - start_time
            self.cycle_time_signal.emit(elapsed_time)
            error_msg = f"Chip Erase failed: {str(exc)}"
            self.report_error(error_msg)
            self.finished_signal.emit(False, error_msg)

        finally:
            sm.close()

    @Slot()
    def run_production_flash(self) -> None:
        """
        Executes one-click production deployment with QA cycle time tracking
        supporting both pyOCD(SWD) and dfu-util(USB DFU).
        """
        start_time = time.perf_counter()

        sm = SessionManager(
            connect_mode=self.connect_mode,
            clock_freq=self.clock_freq,
            interface_type=self.interface_type
        )

        try:
            filename = os.path.basename(self.file_path)
            self.log(
                f"[INFO] Launching Production Flash for image: {filename} @ 0x{self.base_address:08X}")
            self.log(
                f"[INFO] Connecting to target via {self.interface_type}...")

            if not sm.connect():
                raise ConnectionError(
                    f"Failed to connect to target via {self.interface_type}.")

            # ------------------------------------------------------------------
            # Step 1: Read 96-bit Unique Device ID (UID) - SWD ONLY
            # ------------------------------------------------------------------
            if "USB" not in self.interface_type and sm.target:
                try:
                    raw_uid_words = sm.target.read_memory_block32(
                        DEFAULT_STM32_UID_ADDRESS, 3)
                    formatted_uid = ProvisioningService.format_96bit_uid(
                        raw_uid_words)
                    self.log(f"[INFO] 96-bit Unique ID (UID): {formatted_uid}")
                    self.uid_read_signal.emit(formatted_uid)
                except Exception as uid_err:
                    self.log(
                        f"[WARNING] Could not read UID from 0x{DEFAULT_STM32_UID_ADDRESS:08X}: {uid_err}")
                    self.uid_read_signal.emit("UID-READ-ERROR")
            else:
                self.log(
                    "[INFO] 96-bit UID reading bypassed (Not fully supported in USB DFU).")
                self.uid_read_signal.emit("DFU-DEVICE-UID")

            # ------------------------------------------------------------------
            # Step 2: Program Firmware Image
            # ------------------------------------------------------------------
            self.log(
                f"[INFO] Programming firmware starting at 0x{self.base_address:08X}...")
            self.report_progress(5)

            if "USB" in self.interface_type:
                # ==========================================================
                # شروع کدهای جدید برای پروگرام DFU
                # ==========================================================
                _, ext = os.path.splitext(self.file_path.lower())

                cmd = ["dfu-util", "-a", "0"]

                if ext == '.dfu':
                    self.log(
                        "[INFO] Detected .dfu file. Using embedded addresses.")
                    cmd.extend(["-D", self.file_path])
                elif ext == '.bin':
                    hex_addr = f"0x{self.base_address:08X}"
                    self.log(
                        f"[INFO] Detected .bin file. Flashing to {hex_addr}.")
                    cmd.extend(
                        ["-s", f"{hex_addr}:leave", "-D", self.file_path])
                else:
                    raise ValueError(
                        f"Unsupported file format for DFU: {ext}. Use .dfu or .bin")

                self.log("[INFO] Executing dfu-util command in background...")
                result = subprocess.run(cmd, capture_output=True, text=True)

                if result.returncode != 0:
                    # در صورت خطا، خروجی کنسول را در لاگ چاپ میکنیم تا بفهمیم مشکل از کجاست
                    error_details = result.stderr if result.stderr else result.stdout
                    self.log(f"[ERROR] dfu-util output: {error_details}")
                    raise RuntimeError("USB DFU firmware programming failed!")

                self.report_progress(95)
                self.log("[INFO] ✔ Firmware Flashed successfully via USB DFU.")
                # ==========================================================
                # پایان کدهای جدید
                # ==========================================================

            else:
                # برنامه‌ریزی با SWD (این قسمت از کد خودت دست‌نخورده باقی می‌ماند)
                programmer = FileProgrammer(
                    sm.session,
                    progress=self._progress_callback,
                    chip_erase="sector",
                )
                programmer.program(
                    self.file_path,
                    base_address=self.base_address,
                    verify=self.verify_enabled,
                )
                if self.verify_enabled:
                    self.log(
                        "[INFO] ✔ Program & Verify verification successful!")

            # ------------------------------------------------------------------
            # Step 3: Inject Serial Number Payload (Provisioning) - SWD ONLY
            # ------------------------------------------------------------------
            if self.enable_provisioning and len(self.serial_payload) > 0:
                if "USB" in self.interface_type:
                    self.log(
                        "[WARNING] Serial payload injection is bypassed in USB DFU mode.")
                elif sm.target:
                    self.log(
                        f"[PROVISIONING] Injecting {len(self.serial_payload)}-byte serial payload at 0x{self.serial_address:08X}...")
                    try:
                        sm.target.write_memory_block8(
                            self.serial_address, self.serial_payload)
                        self.log(
                            "[INFO] ✔ Serial number injected into Flash successfully!")
                    except Exception as prov_err:
                        self.log(
                            f"[WARNING] Serial number injection failed: {prov_err}")

            # ------------------------------------------------------------------
            # Step 4: System Reset & Resume Execution
            # ------------------------------------------------------------------
            self.report_progress(100)
            self.log(
                "[INFO] Resetting MCU core to launch application firmware...")

            sm.reset_target(halt=False)
            if "USB" not in self.interface_type and sm.target:
                try:
                    sm.target.resume()
                except Exception:
                    pass

            self.log("[INFO] ✔ Target MCU is now running normally.")

            elapsed_time = time.perf_counter() - start_time
            self.cycle_time_signal.emit(elapsed_time)
            self.finished_signal.emit(
                True, "Production Flash deployed successfully.")

        except Exception as exc:
            elapsed_time = time.perf_counter() - start_time
            self.cycle_time_signal.emit(elapsed_time)
            error_msg = f"Production Flash failed: {str(exc)}"
            self.report_error(error_msg)
            self.finished_signal.emit(False, error_msg)

        finally:
            sm.close()
