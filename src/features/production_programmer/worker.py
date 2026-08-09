# """
# Background worker executing firmware programming, full chip erasing,
# and flash verification sequences in a dedicated asynchronous thread,
# supporting custom start memory addresses, 96-bit UID reading,
# serial number payload injection, and accurate cycle time tracking.
# """

# import os
# import time
# from typing import Optional, Any, List
# from PySide6.QtCore import Slot, Signal

# from pyocd.core.helpers import ConnectHelper
# from pyocd.flash.file_programmer import FileProgrammer
# from pyocd.flash.eraser import FlashEraser

# from src.common import BaseWorker, get_logger
# from src.features.production_programmer.verify_service import VerifyService
# from src.features.production_programmer.provisioning import ProvisioningService

# logger = get_logger("ProductionProgrammerWorker")

# DEFAULT_STM32_UID_ADDRESS = 0x1FFFF7E8


# class ProductionProgrammerWorker(BaseWorker):
#     """
#     Worker class responsible for executing Production Flash, Full Chip Erase,
#     UID reading, and Serial Provisioning operations via SWD interface
#     without blocking the GUI thread.
#     """

#     uid_read_signal = Signal(str)
#     cycle_time_signal = Signal(float)

#     def __init__(
#         self,
#         file_path: str = "",
#         base_address: int = 0x08000000,
#         clock_freq: int = 1000000,
#         connect_mode: str = "under-reset",
#         verify_enabled: bool = True,
#         enable_provisioning: bool = False,
#         serial_payload: Optional[List[int]] = None,
#         serial_address: int = 0x0801FC00,
#         parent: Optional[Any] = None,
#     ):
#         super().__init__(parent)
#         self.file_path = file_path
#         self.base_address = base_address
#         self.clock_freq = clock_freq
#         self.connect_mode = connect_mode
#         self.verify_enabled = verify_enabled
#         self.enable_provisioning = enable_provisioning
#         self.serial_payload = serial_payload or []
#         self.serial_address = serial_address

#     def _progress_callback(self, progress: float) -> None:
#         """Translate pyOCD decimal progress (0.0 - 1.0) to integer percentage (0 - 100)."""
#         if self._is_running:
#             percent = int(progress * 100)
#             self.report_progress(percent)

#     @Slot()
#     def run_chip_erase(self) -> None:
#         """
#         Executes robust full chip erase sequence with automatic MASS erase fallback
#         to clear locked or corrupted target memory.
#         """
#         session = None
#         start_time = time.perf_counter()
#         try:
#             self.log("[INFO] Starting Full Chip Erase sequence...")
#             safe_clock = min(self.clock_freq, 50000)
#             self.log(
#                 f"[INFO] Connecting to target via auto-detection @ {safe_clock // 1000} kHz..."
#             )

#             options = {
#                 "connect_mode": self.connect_mode,
#                 "frequency": safe_clock,
#                 "target_override": None,
#                 "reset_type": "hw" if self.connect_mode == "under-reset" else "sw",
#                 "halt_on_connect": True,
#                 "resume_on_disconnect": False,
#             }

#             try:
#                 session = ConnectHelper.session_with_chosen_probe(
#                     options=options)
#                 session.open()
#             except Exception as e:
#                 err_lower = str(e).lower()
#                 if "not recognized" in err_lower or "target" in err_lower:
#                     self.log(
#                         "[WARNING] Specific target pack not found. Using 'cortex_m' fallback..."
#                     )
#                     options["target_override"] = "cortex_m"
#                     session = ConnectHelper.session_with_chosen_probe(
#                         options=options)
#                     session.open()
#                 elif "no ack" in err_lower or "communication failure" in err_lower:
#                     self.log(
#                         "[WARNING] Under-reset connect failed. Retrying in 'attach' mode..."
#                     )
#                     options["connect_mode"] = "attach"
#                     session = ConnectHelper.session_with_chosen_probe(
#                         options=options)
#                     session.open()
#                 else:
#                     raise e

#             target = session.board.target
#             self.log(
#                 f"[INFO] SWD Connected! MCU Part: {str(target.part_number).upper()}"
#             )

#             self.log("[INFO] Halting core and clearing active exceptions...")
#             try:
#                 target.reset_and_halt()
#             except Exception:
#                 target.halt()

#             self.report_progress(10)
#             self.log(
#                 "[INFO] Executing Flash Erase on all memory sectors... Please wait."
#             )

#             try:
#                 eraser = FlashEraser(session, mode=FlashEraser.Mode.CHIP)
#                 eraser.erase()
#             except Exception:
#                 self.log(
#                     "[WARNING] Chip Erase algorithm faulted. Attempting Hardware MASS Erase..."
#                 )
#                 try:
#                     target.halt()
#                 except Exception:
#                     pass
#                 eraser_mass = FlashEraser(session, mode=FlashEraser.Mode.MASS)
#                 eraser_mass.erase()

#             self.report_progress(100)
#             elapsed_time = time.perf_counter() - start_time
#             self.cycle_time_signal.emit(elapsed_time)
#             self.log(
#                 f"[INFO] ✔ Full Chip Erase completed successfully in {elapsed_time:.2f} s! Memory is now blank."
#             )
#             self.finished_signal.emit(
#                 True, "Full Chip Erase completed successfully."
#             )

#         except Exception as exc:
#             elapsed_time = time.perf_counter() - start_time
#             self.cycle_time_signal.emit(elapsed_time)
#             error_msg = f"Chip Erase failed: {str(exc)}"
#             self.report_error(error_msg)
#             self.finished_signal.emit(False, error_msg)

#         finally:
#             if session:
#                 try:
#                     session.close()
#                     self.log("[INFO] SWD session closed.")
#                 except Exception:
#                     pass

#     @Slot()
#     def run_production_flash(self) -> None:
#         """
#         Executes one-click production deployment with QA cycle time tracking:
#         1. Auto-connect and identify ARM MCU.
#         2. Read 96-bit Unique Device ID (UID).
#         3. Erase required sectors and program firmware image at the specified base address.
#         4. Verify firmware integrity if enabled.
#         5. Inject serial number payload if provisioning is enabled.
#         6. Reset core to run application.
#         """
#         session = None
#         start_time = time.perf_counter()
#         try:
#             filename = os.path.basename(self.file_path)
#             self.log(
#                 f"[INFO] Launching Production Flash for image: {filename} @ 0x{self.base_address:08X}"
#             )
#             self.log(
#                 f"[INFO] Connecting to target @ {self.clock_freq // 1000} kHz | "
#                 f"Mode: {self.connect_mode}"
#             )

#             options = {
#                 "connect_mode": self.connect_mode,
#                 "frequency": self.clock_freq,
#                 "target_override": None,
#                 "reset_type": "hw" if self.connect_mode == "under-reset" else "sw",
#                 "resume_on_disconnect": False,
#             }

#             try:
#                 session = ConnectHelper.session_with_chosen_probe(
#                     options=options)
#                 session.open()
#             except Exception as e:
#                 err_lower = str(e).lower()
#                 if "not recognized" in err_lower or "target" in err_lower:
#                     self.log(
#                         "[WARNING] Target pack unknown. Using generic 'cortex_m' profile..."
#                     )
#                     options["target_override"] = "cortex_m"
#                     session = ConnectHelper.session_with_chosen_probe(
#                         options=options)
#                     session.open()
#                 else:
#                     raise e

#             board = session.board
#             target = board.target
#             self.log(
#                 f"[INFO] ✔ Connected! Target MCU: {str(target.part_number).upper()}"
#             )

#             dpidr = session.probe.read_dp(0x0)
#             self.log(f"[INFO] Target DPIDR IDCODE: 0x{dpidr:08X}")

#             # ------------------------------------------------------------------
#             # Step 1: Read 96-bit Unique Device ID (UID)
#             # ------------------------------------------------------------------
#             try:
#                 raw_uid_words = target.read_memory_block32(
#                     DEFAULT_STM32_UID_ADDRESS, 3)
#                 formatted_uid = ProvisioningService.format_96bit_uid(
#                     raw_uid_words)
#                 self.log(f"[INFO] 96-bit Unique ID (UID): {formatted_uid}")
#                 self.uid_read_signal.emit(formatted_uid)
#             except Exception as uid_err:
#                 self.log(
#                     f"[WARNING] Could not read UID from 0x{DEFAULT_STM32_UID_ADDRESS:08X}: {uid_err}"
#                 )
#                 self.uid_read_signal.emit("UID-READ-ERROR")

#             # ------------------------------------------------------------------
#             # Step 2: Program Firmware Image
#             # ------------------------------------------------------------------
#             self.log(
#                 f"[INFO] Programming firmware image into flash memory starting at 0x{self.base_address:08X}..."
#             )
#             self.report_progress(0)

#             programmer = FileProgrammer(
#                 session,
#                 progress=self._progress_callback,
#                 chip_erase="sector",
#             )
#             programmer.program(
#                 self.file_path,
#                 base_address=self.base_address,
#                 verify=self.verify_enabled,
#             )

#             if self.verify_enabled:
#                 self.log("[INFO] ✔ Program & Verify verification successful!")
#             else:
#                 self.log(
#                     "[INFO] ✔ Programming completed (Verification was skipped)."
#                 )

#             # ------------------------------------------------------------------
#             # Step 3: Inject Serial Number Payload (Provisioning)
#             # ------------------------------------------------------------------
#             if self.enable_provisioning and len(self.serial_payload) > 0:
#                 self.log(
#                     f"[PROVISIONING] Injecting {len(self.serial_payload)}-byte serial payload at 0x{self.serial_address:08X}..."
#                 )
#                 try:
#                     target.write_memory_block8(
#                         self.serial_address, self.serial_payload)
#                     self.log(
#                         "[INFO] ✔ Serial number injected into Flash successfully!")
#                 except Exception as prov_err:
#                     self.log(
#                         f"[WARNING] Serial number injection failed: {prov_err}")

#             # ------------------------------------------------------------------
#             # Step 4: System Reset & Resume Execution
#             # ------------------------------------------------------------------
#             self.report_progress(100)
#             self.log(
#                 "[INFO] Resetting MCU core to launch application firmware..."
#             )
#             try:
#                 session.target.reset_and_halt()
#                 session.target.resume()
#                 self.log("[INFO] ✔ Target MCU is now running normally.")
#             except Exception as e_reset:
#                 self.log(f"[WARNING] Post-flash reset warning: {str(e_reset)}")

#             elapsed_time = time.perf_counter() - start_time
#             self.cycle_time_signal.emit(elapsed_time)
#             self.finished_signal.emit(
#                 True, "Production Flash deployed successfully."
#             )

#         except Exception as exc:
#             elapsed_time = time.perf_counter() - start_time
#             self.cycle_time_signal.emit(elapsed_time)
#             error_msg = f"Production Flash failed: {str(exc)}"
#             self.report_error(error_msg)
#             self.finished_signal.emit(False, error_msg)

#         finally:
#             if session:
#                 try:
#                     session.close()
#                     self.log("[INFO] SWD session closed.")
#                 except Exception:
#                     pass
"""
Background worker executing firmware programming, full chip erasing,
and flash verification sequences in a dedicated asynchronous thread.
Now fully supports BOTH DAPLink (SWD) and Direct USB (DFU) interfaces.
"""

import os
import time
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
        """Translate pyOCD decimal progress (0.0 - 1.0) to integer percentage (0 - 100)."""
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

            if not sm.erase_chip():
                raise RuntimeError("Chip Erase operation failed.")

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
        supporting both pyOCD (SWD) and dfu-util (USB DFU).
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

                if not sm.program_firmware(self.file_path, self.base_address):
                    raise RuntimeError("USB DFU firmware programming failed!")
                self.report_progress(95)
                self.log("[INFO] ✔ Firmware Flashed successfully via USB DFU.")
            else:
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
