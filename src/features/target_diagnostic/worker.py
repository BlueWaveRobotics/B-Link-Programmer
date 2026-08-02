"""
Background worker for executing target MCU identification and low-level
ARM Cortex-M core diagnostics without freezing the user interface.
"""

from typing import Dict, Any, Optional
from PySide6.QtCore import Signal, Slot

from src.common import BaseWorker, SessionManager, get_logger

logger = get_logger("TargetDiagnosticWorker")


class TargetDiagnosticWorker(BaseWorker):
    """
    Executes non-intrusive SWD bus probing and hardware register inspections
    in an asynchronous background thread.
    """

    # Emit target chip identity (Probe SN, MCU Part Number, DPIDR)
    target_info_signal = Signal(dict)

    # Emit decoded core status registers (DHCSR, DEMCR flags)
    core_status_signal = Signal(dict)

    def __init__(
        self,
        clock_freq: int = 1000000,
        connect_mode: str = "attach",
        parent: Optional[Any] = None,
    ):
        super().__init__(parent)
        self.clock_freq = clock_freq
        self.connect_mode = connect_mode
        self.session_manager = SessionManager(
            clock_freq=self.clock_freq,
            connect_mode=self.connect_mode,
        )

    @Slot()
    def probe_target(self) -> None:
        """
        Lightweight attach probe to identify MCU part number and DPIDR
        without resetting or halting the running microcontroller.
        """
        self.log("[INFO] Probing SWD bus for Target MCU identification...")
        try:
            info = self.session_manager.probe_target_info(
                clock_freq=self.clock_freq
            )
            if info.get("success"):
                self.log(
                    f"[INFO] ✔ Found Target: {info.get('part_number')} | "
                    f"Probe SN: {info.get('probe_serial')} | "
                    f"DPIDR: {info.get('dpidr')}"
                )
            else:
                err = info.get("error", "Unknown probe failure")
                self.log(f"[WARNING] Target probe failed: {err}")

            self.target_info_signal.emit(info)

        except Exception as exc:
            error_msg = str(exc)
            logger.error(f"Target probe exception: {error_msg}")
            self.report_error(f"SWD Probe Error: {error_msg}")
            self.target_info_signal.emit(
                {"success": False, "error": error_msg})

    @Slot()
    def inspect_core(self) -> None:
        """
        Deep diagnostic inspection of ARM Cortex-M core status registers
        (DHCSR and DEMCR) to check for LOCKUP state or trap configurations.
        """
        self.log("[INFO] Reading low-level ARM Cortex-M debug registers...")
        status_report: Dict[str, Any] = {
            "success": False,
            "dhcsr": None,
            "demcr": None,
            "sanity_dpidr": None,
            "error": "",
        }

        try:
            if not self.session_manager.connect():
                status_report["error"] = "Failed to establish SWD session."
                self.core_status_signal.emit(status_report)
                return

            status_report["sanity_dpidr"] = (
                self.session_manager.check_swd_sanity()
            )
            status_report["dhcsr"] = self.session_manager.inspect_dhcsr()
            status_report["demcr"] = self.session_manager.inspect_demcr()
            status_report["success"] = True

            self.log("[INFO] ✔ Core diagnostic registers read successfully.")
            self.core_status_signal.emit(status_report)

        except Exception as exc:
            error_msg = str(exc)
            logger.error(f"Core inspection exception: {error_msg}")
            status_report["error"] = error_msg
            self.report_error(f"Core Diagnostic Error: {error_msg}")
            self.core_status_signal.emit(status_report)

        finally:
            self.session_manager.close()
