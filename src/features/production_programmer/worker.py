"""
Background worker executing firmware programming, full chip erasing,
and flash verification sequences in a dedicated asynchronous thread,
supporting custom start memory addresses for RAW binaries and bootloaders.
"""

import os
from typing import Optional, Any
from PySide6.QtCore import Slot

from pyocd.core.helpers import ConnectHelper
from pyocd.flash.file_programmer import FileProgrammer
from pyocd.flash.eraser import FlashEraser

from src.common import BaseWorker, get_logger
from src.features.production_programmer.verify_service import VerifyService

logger = get_logger("ProductionProgrammerWorker")


class ProductionProgrammerWorker(BaseWorker):
    """
    Worker class responsible for executing Production Flash and Full Chip Erase
    operations via SWD interface without blocking the GUI thread.
    """

    def __init__(
        self,
        file_path: str = "",
        base_address: int = 0x08000000,
        clock_freq: int = 1000000,
        connect_mode: str = "under-reset",
        verify_enabled: bool = True,
        parent: Optional[Any] = None,
    ):
        super().__init__(parent)
        self.file_path = file_path
        self.base_address = base_address
        self.clock_freq = clock_freq
        self.connect_mode = connect_mode
        self.verify_enabled = verify_enabled

    def _progress_callback(self, progress: float) -> None:
        """Translate pyOCD decimal progress (0.0 - 1.0) to integer percentage (0 - 100)."""
        if self._is_running:
            percent = int(progress * 100)
            self.report_progress(percent)

    @Slot()
    def run_chip_erase(self) -> None:
        """
        Executes robust full chip erase sequence with automatic MASS erase fallback
        to clear locked or corrupted target memory.
        """
        session = None
        try:
            self.log("[INFO] Starting Full Chip Erase sequence...")
            safe_clock = min(self.clock_freq, 50000)
            self.log(
                f"[INFO] Connecting to target via auto-detection @ {safe_clock // 1000} kHz..."
            )

            options = {
                "connect_mode": self.connect_mode,
                "frequency": safe_clock,
                "target_override": None,
                "reset_type": "hw" if self.connect_mode == "under-reset" else "sw",
                "halt_on_connect": True,
                "resume_on_disconnect": False,
            }

            try:
                session = ConnectHelper.session_with_chosen_probe(
                    options=options)
                session.open()
            except Exception as e:
                err_lower = str(e).lower()
                if "not recognized" in err_lower or "target" in err_lower:
                    self.log(
                        "[WARNING] Specific target pack not found. Using 'cortex_m' fallback...")
                    options["target_override"] = "cortex_m"
                    session = ConnectHelper.session_with_chosen_probe(
                        options=options)
                    session.open()
                elif "no ack" in err_lower or "communication failure" in err_lower:
                    self.log(
                        "[WARNING] Under-reset connect failed. Retrying in 'attach' mode...")
                    options["connect_mode"] = "attach"
                    session = ConnectHelper.session_with_chosen_probe(
                        options=options)
                    session.open()
                else:
                    raise e

            target = session.board.target
            self.log(
                f"[INFO] SWD Connected! MCU Part: {str(target.part_number).upper()}")

            self.log("[INFO] Halting core and clearing active exceptions...")
            try:
                target.reset_and_halt()
            except Exception:
                target.halt()

            self.report_progress(10)
            self.log(
                "[INFO] Executing Flash Erase on all memory sectors... Please wait.")

            try:
                eraser = FlashEraser(session, mode=FlashEraser.Mode.CHIP)
                eraser.erase()
            except Exception:
                self.log(
                    "[WARNING] Chip Erase algorithm faulted. Attempting Hardware MASS Erase...")
                try:
                    target.halt()
                except Exception:
                    pass
                eraser_mass = FlashEraser(session, mode=FlashEraser.Mode.MASS)
                eraser_mass.erase()

            self.report_progress(100)
            self.log(
                "[INFO] ✔ Full Chip Erase completed successfully! Memory is now blank.")
            self.finished_signal.emit(
                True, "Full Chip Erase completed successfully.")

        except Exception as exc:
            error_msg = f"Chip Erase failed: {str(exc)}"
            self.report_error(error_msg)
            self.finished_signal.emit(False, error_msg)

        finally:
            if session:
                try:
                    session.close()
                    self.log("[INFO] SWD session closed.")
                except Exception:
                    pass

    @Slot()
    def run_production_flash(self) -> None:
        """
        Executes one-click production deployment:
        1. Auto-connect and identify ARM MCU.
        2. Erase required sectors and program firmware image at the specified base address.
        3. Verify firmware integrity if enabled.
        4. Reset core to run application.
        """
        session = None
        try:
            filename = os.path.basename(self.file_path)
            self.log(
                f"[INFO] Launching Production Flash for image: {filename} @ 0x{self.base_address:08X}"
            )
            self.log(
                f"[INFO] Connecting to target @ {self.clock_freq // 1000} kHz | "
                f"Mode: {self.connect_mode}"
            )

            options = {
                "connect_mode": self.connect_mode,
                "frequency": self.clock_freq,
                "target_override": None,
                "reset_type": "hw" if self.connect_mode == "under-reset" else "sw",
                "resume_on_disconnect": False,
            }

            try:
                session = ConnectHelper.session_with_chosen_probe(
                    options=options)
                session.open()
            except Exception as e:
                err_lower = str(e).lower()
                if "not recognized" in err_lower or "target" in err_lower:
                    self.log(
                        "[WARNING] Target pack unknown. Using generic 'cortex_m' profile...")
                    options["target_override"] = "cortex_m"
                    session = ConnectHelper.session_with_chosen_probe(
                        options=options)
                    session.open()
                else:
                    raise e

            board = session.board
            target = board.target
            self.log(
                f"[INFO] ✔ Connected! Target MCU: {str(target.part_number).upper()}")

            dpidr = session.probe.read_dp(0x0)
            self.log(f"[INFO] Target DPIDR IDCODE: 0x{dpidr:08X}")

            self.log(
                f"[INFO] Programming firmware image into flash memory starting at 0x{self.base_address:08X}..."
            )
            self.report_progress(0)

            programmer = FileProgrammer(
                session,
                progress=self._progress_callback,
                chip_erase="sector",
            )
            programmer.program(
                self.file_path,
                base_address=self.base_address,
                verify=self.verify_enabled,
            )

            if self.verify_enabled:
                self.log("[INFO] ✔ Program & Verify verification successful!")
            else:
                self.log(
                    "[INFO] ✔ Programming completed (Verification was skipped).")

            self.report_progress(100)
            self.log(
                "[INFO] Resetting MCU core to launch application firmware...")
            try:
                session.target.reset_and_halt()
                session.target.resume()
                self.log("[INFO] ✔ Target MCU is now running normally.")
            except Exception as e_reset:
                self.log(f"[WARNING] Post-flash reset warning: {str(e_reset)}")

            self.finished_signal.emit(
                True, "Production Flash deployed successfully.")

        except Exception as exc:
            error_msg = f"Production Flash failed: {str(exc)}"
            self.report_error(error_msg)
            self.finished_signal.emit(False, error_msg)

        finally:
            if session:
                try:
                    session.close()
                    self.log("[INFO] SWD session closed.")
                except Exception:
                    pass
