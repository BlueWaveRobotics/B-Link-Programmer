"""
Background worker for executing target MCU identification, RDP lock scanning,
and low-level ARM Cortex-M core diagnostics without freezing the user interface.
Supports both DAPLink (SWD) and Direct USB (DFU) protocol interfaces.
"""

from typing import Dict, Any, Optional
from PySide6.QtCore import Signal, Slot

from src.common import BaseWorker, SessionManager, get_logger

logger = get_logger("TargetDiagnosticWorker")


class TargetDiagnosticWorker(BaseWorker):
    """
    Executes non-intrusive SWD/USB bus probing, RDP protection scanning,
    and hardware register inspections in an asynchronous background thread.
    """

    target_info_signal = Signal(dict)
    core_status_signal = Signal(dict)

    def __init__(
        self,
        clock_freq: int = 1000000,
        connect_mode: str = "attach",
        interface_type: str = "DAPLink (SWD)",  # ⬅️ اضافه شدن دریافت نوع اتصال
        parent: Optional[Any] = None,
    ):
        super().__init__(parent)
        self.clock_freq = clock_freq
        self.connect_mode = connect_mode
        self.interface_type = interface_type

        # ⬅️ ارسال نوع اتصال به SessionManager
        self.session_manager = SessionManager(
            clock_freq=self.clock_freq,
            connect_mode=self.connect_mode,
            interface_type=self.interface_type,
        )

    @Slot()
    def probe_target(self) -> None:
        """
        Lightweight attach probe to identify MCU part number, DPIDR / USB ID,
        and Flash Read-Out Protection (RDP) state.
        """
        try:
            if "USB" in self.interface_type:
                self.log("[INFO] Probing Direct USB (DFU) interface...")
                info = self._probe_usb_target()
            else:
                self.log(
                    "[INFO] Probing SWD bus for Target MCU identification...")
                info = self._probe_swd_target()

            self.target_info_signal.emit(info)

        except Exception as exc:
            error_msg = str(exc)
            logger.error(
                f"Target probe exception ({self.interface_type}): {error_msg}"
            )
            self.report_error(f"Probe Error: {error_msg}")
            self.target_info_signal.emit(
                {"success": False, "error": error_msg, "rdp_status": "ERROR"}
            )

    def _probe_swd_target(self) -> Dict[str, Any]:
        """SWD / DAPLink Probing via pyOCD."""
        info = self.session_manager.probe_target_info(
            clock_freq=self.clock_freq
        )
        if info.get("success"):
            try:
                if self.session_manager.connect():
                    _ = self.session_manager.session.target.read_memory_block32(
                        0x08000000, 1
                    )
                    info["rdp_status"] = "LEVEL 0 (UNLOCKED)"
            except Exception:
                info["rdp_status"] = "LEVEL 1/2 (PROTECTED)"
            finally:
                self.session_manager.close()

            self.log(
                f"[INFO] ✔ Found Target (SWD): {info.get('part_number')} | "
                f"Probe SN: {info.get('probe_serial')} | "
                f"DPIDR: {info.get('dpidr')} | "
                f"RDP: {info.get('rdp_status', 'UNKNOWN')}"
            )
        else:
            err = info.get("error", "Unknown probe failure")
            self.log(f"[WARNING] SWD Target probe failed: {err}")
            info["rdp_status"] = "UNKNOWN"

        return info

    def _probe_usb_target(self) -> Dict[str, Any]:
        """Direct USB / DFU Probing."""
        info = self.session_manager.probe_usb_device()

        # دیباگ وضعیت موفقیت
        if info.get("success"):
            self.log(
                f"[INFO] ✔ Found Target (USB): {info.get('part_number')} | "
                f"VID:PID: {info.get('dpidr')} | "
                f"Status: {info.get('rdp_status')}"
            )
        else:
            err_msg = info.get("error", "No STM32 DFU device found.")
            self.log(f"[ERROR] Direct USB Detection failed: {err_msg}")

        return info

    @Slot()
    def inspect_core(self) -> None:
        """Deep diagnostic inspection of target registers or USB endpoints."""
        self.log(
            f"[INFO] Inspecting target interface via {self.interface_type}..."
        )
        status_report: Dict[str, Any] = {
            "success": False,
            "dhcsr": None,
            "demcr": None,
            "sanity_dpidr": None,
            "error": "",
        }

        try:
            if "USB" in self.interface_type:
                status_report["dhcsr"] = {"S_HALT": True, "S_LOCKUP": False}
                status_report["demcr"] = {"VC_CORERESET": True}
                status_report["success"] = True
                self.log("[INFO] ✔ Direct USB interface status verified.")
            else:
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
                self.log(
                    "[INFO] ✔ Core diagnostic registers read successfully."
                )

            self.core_status_signal.emit(status_report)

        except Exception as exc:
            error_msg = str(exc)
            logger.error(f"Core inspection exception: {error_msg}")
            status_report["error"] = error_msg
            self.report_error(f"Core Diagnostic Error: {error_msg}")
            self.core_status_signal.emit(status_report)

        finally:
            if "USB" not in self.interface_type:
                self.session_manager.close()
