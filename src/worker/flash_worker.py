import os
import logging
from typing import Optional

# PySide6 Thread & Signal tools
from PySide6.QtCore import QObject, Signal, Slot

# pyOCD Flash programming libraries
from pyocd.core.helpers import ConnectHelper
from pyocd.flash.file_programmer import FileProgrammer
from pyocd.flash.eraser import FlashEraser
# Configure Python logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DAPLinkSuite")


# =====================================================================
# Worker 1: SWD / pyOCD Flash Programmer Worker
# =====================================================================
class FlashWorker(QObject):
    """
    Background worker for executing pyOCD flash programming and diagnostics
    in a dedicated QThread to prevent GUI freezing (Target-Agnostic / Auto-Detect).
    """
    log_signal = Signal(str)
    progress_signal = Signal(int)
    finished_signal = Signal(bool, str)
    target_info_signal = Signal(dict)

    def __init__(
        self,
        file_path: str,
        clock_freq: int = 100000,
        connect_mode: str = "under-reset"
    ):
        super().__init__()
        self.file_path = file_path
        self.clock_freq = clock_freq
        self.connect_mode = connect_mode
        self._is_running = True

    @Slot()
    def check_target_connection(self) -> None:
        """
        Slot to refresh/detect the target chip and emit the info back to GUI.
        """
        self.log_signal.emit("[INFO] Probing SWD bus for Target ID...")
        try:
            info = self.controller.get_target_info(clock_freq=self.clock_freq)
            if info["success"]:
                self.log_signal.emit(
                    f"[INFO] ✔ Chip Detected — MCU: {info['part_number']} | Core: {info['core_type']} | DPIDR: {info['dpidr']}"
                )
            else:
                self.log_signal.emit(
                    f"[WARNING] Target detection failed: {info['error']}"
                )
            self.target_info_signal.emit(info)
        except Exception as e:
            err_msg = str(e)
            self.log_signal.emit(f"[ERROR] SWD Probe Exception: {err_msg}")
            self.target_info_signal.emit({"success": False, "error": err_msg})

    @Slot()
    def run_chip_erase(self) -> None:
        """
        Robust Full Chip Erase that prevents CPU Lockup on blank flash,
        allowing unlimited consecutive Erase/Program operations.
        """
        session = None
        try:
            self.log_signal.emit("[INFO] Starting Full Chip Erase sequence...")
            safe_clock = min(self.clock_freq, 50000)
            self.log_signal.emit(
                f"[INFO] Connecting to target via auto-detection @ {safe_clock//1000} kHz..."
            )

            options = {
                'connect_mode': 'under-reset',
                'frequency': safe_clock,
                'target_override': None,
                'reset_type': 'hw',
                'halt_on_connect': True,
                'resume_on_disconnect': False
            }

            try:
                session = ConnectHelper.session_with_chosen_probe(
                    options=options)
                session.open()
            except Exception as e:
                err_lower = str(e).lower()
                if "not recognized" in err_lower or "target" in err_lower:
                    self.log_signal.emit(
                        "[WARNING] Specific target pack not found. Using generic 'cortex_m' mode..."
                    )
                    options['target_override'] = "cortex_m"
                    session = ConnectHelper.session_with_chosen_probe(
                        options=options)
                    session.open()
                elif "no ack" in err_lower or "communication failure" in err_lower:
                    self.log_signal.emit(
                        "[WARNING] Under-reset connect failed (No ACK). Retrying in 'attach' mode..."
                    )
                    options['connect_mode'] = 'attach'
                    session = ConnectHelper.session_with_chosen_probe(
                        options=options)
                    session.open()
                else:
                    raise e

            target = session.board.target
            self.log_signal.emit(
                f"[INFO] SWD Connection established! Detected MCU: {target.part_number.upper()}"
            )

            self.log_signal.emit(
                "[INFO] Halting core and clearing active interrupts...")
            try:
                target.reset_and_halt()
            except Exception:
                target.halt()

            self.progress_signal.emit(10)
            self.log_signal.emit(
                "[INFO] Executing Mass/Chip Erase on all Flash regions... Please wait."
            )

            try:
                eraser = FlashEraser(session, mode=FlashEraser.Mode.CHIP)
                eraser.erase()
            except Exception as e_chip:
                self.log_signal.emit(
                    "[WARNING] Chip Erase algorithm faulted. Retrying with Hardware MASS Erase..."
                )
                try:
                    target.halt()
                except Exception:
                    pass
                eraser_mass = FlashEraser(session, mode=FlashEraser.Mode.MASS)
                eraser_mass.erase()

            self.progress_signal.emit(100)
            self.log_signal.emit(
                "[INFO] ✔ Full Chip Erase completed successfully! Memory is now blank."
            )

            try:
                target.halt()
            except Exception:
                pass

            self.finished_signal.emit(
                True, "Full Chip Erase completed successfully.")

        except Exception as e:
            error_msg = f"Chip Erase failed: {str(e)}"
            self.log_signal.emit(f"[ERROR] {error_msg}")
            self.finished_signal.emit(False, error_msg)

        finally:
            if session:
                try:
                    session.close()
                    self.log_signal.emit("[INFO] SWD session closed.")
                except Exception:
                    pass

    def _progress_callback(self, progress: float) -> None:
        if self._is_running:
            percent = int(progress * 100)
            self.progress_signal.emit(percent)

    @Slot()
    def run_production_flash(self) -> None:
        session = None
        try:
            self.log_signal.emit(
                f"[INFO] Starting Production Mode for file: {os.path.basename(self.file_path)}"
            )
            self.log_signal.emit(
                f"[INFO] Connecting to target via auto-detection @ {self.clock_freq//1000} kHz..."
            )

            options = {
                'connect_mode': self.connect_mode,
                'frequency': self.clock_freq,
                'target_override': None,
                'reset_type': 'hw' if self.connect_mode == 'under-reset' else 'sw',
                'resume_on_disconnect': False
            }

            try:
                session = ConnectHelper.session_with_chosen_probe(
                    options=options)
                session.open()
            except Exception as e:
                err_lower = str(e).lower()
                if "not recognized" in err_lower or "target" in err_lower:
                    self.log_signal.emit(
                        "[WARNING] Specific target pack not found. Using generic 'cortex_m' mode..."
                    )
                    options['target_override'] = "cortex_m"
                    session = ConnectHelper.session_with_chosen_probe(
                        options=options)
                    session.open()
                else:
                    raise e

            board = session.board
            target = board.target
            self.log_signal.emit(
                f"[INFO] SWD Connection established! Detected MCU: {target.part_number.upper()}"
            )

            dpidr = session.probe.read_dp(0x0)
            self.log_signal.emit(f"[INFO] Read DP IDCODE: 0x{dpidr:08X}")

            self.log_signal.emit(
                "[INFO] Initializing Flash Erase, Program, and Verify sequence..."
            )
            self.progress_signal.emit(0)

            programmer = FileProgrammer(
                session,
                progress=self._progress_callback,
                chip_erase="sector"
            )
            programmer.program(self.file_path)

            self.progress_signal.emit(100)
            self.log_signal.emit(
                "[INFO] ✔ Flash Program & Verify completed successfully!"
            )

            self.log_signal.emit(
                "[INFO] Resetting target core to run application..."
            )
            session.target.reset_and_halt()
            session.target.resume()
            self.log_signal.emit("[INFO] Target MCU is now running.")

            self.finished_signal.emit(
                True, "Production flash sequence completed successfully."
            )

        except Exception as e:
            error_msg = f"Flash operation failed: {str(e)}"
            self.log_signal.emit(f"[ERROR] {error_msg}")
            self.finished_signal.emit(False, error_msg)

        finally:
            if session:
                try:
                    session.close()
                    self.log_signal.emit("[INFO] SWD session closed.")
                except Exception:
                    pass
