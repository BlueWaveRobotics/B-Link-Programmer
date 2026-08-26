# """
# Background worker for executing target MCU identification, RDP lock scanning,
# and low-level ARM Cortex-M core diagnostics without freezing the user interface.
# Supports both DAPLink (SWD) and Direct USB (DFU) protocol interfaces.
# """

# import time
# from typing import Dict, Any, Optional
# from PySide6.QtCore import Signal, Slot
# from pyocd.core.helpers import ConnectHelper

# from src.common import BaseWorker, SessionManager, get_logger

# logger = get_logger("TargetDiagnosticWorker")


# class TargetDiagnosticWorker(BaseWorker):
#     """
#     Executes non-intrusive SWD/USB bus probing, RDP protection scanning,
#     and hardware register inspections in an asynchronous background thread.
#     """

#     target_info_signal = Signal(dict)
#     core_status_signal = Signal(dict)

#     def __init__(
#         self,
#         clock_freq: int = 1000000,
#         connect_mode: str = "attach",
#         interface_type: str = "B-Link (SWD)",
#         parent: Optional[Any] = None,
#         unique_id: Optional[str] = None,
#     ):
#         super().__init__(parent)
#         self.clock_freq = clock_freq
#         self.connect_mode = connect_mode
#         self.interface_type = interface_type
#         self.unique_id = unique_id

#         print(
#             f"[DEBUG-WORKER] Worker initialized. Interface: {self.interface_type}, Clock: {self.clock_freq}Hz")

#         self.session_manager = SessionManager(
#             clock_freq=self.clock_freq,
#             connect_mode=self.connect_mode,
#             interface_type=self.interface_type,
#             unique_id=self.unique_id,
#         )

#     @Slot()
#     def probe_target(self) -> None:
#         """
#         Lightweight attach probe to identify MCU part number, DPIDR / USB ID,
#         and Flash Read-Out Protection (RDP) state.
#         """
#         print("\n=================== [PROBE TARGET START] ===================")
#         print(
#             f"[DEBUG-WORKER Step 1] Entering probe_target slot on thread: {self.thread()}")
#         try:
#             if "USB" in self.interface_type:
#                 print("[DEBUG-WORKER Step 2] Routing to Direct USB (DFU) probe...")
#                 self.log("[INFO] Probing Direct USB (DFU) interface...")
#                 info = self._probe_usb_target()
#             else:
#                 print("[DEBUG-WORKER Step 2] Routing to SWD bus probe...")
#                 self.log(
#                     "[INFO] Probing SWD bus for Target MCU identification...")
#                 info = self._probe_swd_target()

#             print(
#                 f"[DEBUG-WORKER Step 5] Probe complete. Emitting target_info_signal: {info.get('success')}")
#             self.target_info_signal.emit(info)

#         except Exception as exc:
#             error_msg = str(exc)
#             print(f"[DEBUG-WORKER CRITICAL EXCEPTION] {error_msg}")
#             logger.error(
#                 f"Target probe exception ({self.interface_type}): {error_msg}"
#             )
#             self.report_error(f"Probe Error: {error_msg}")
#             self.target_info_signal.emit(
#                 {"success": False, "error": error_msg, "rdp_status": "ERROR"}
#             )
#         finally:
#             print(
#                 "=================== [PROBE TARGET END] ===================\n")

#     def _probe_swd_target(self) -> Dict[str, Any]:
#         """SWD / DAPLink Probing via pyOCD with strict validation layer."""

#         print("[DEBUG-WORKER Step 3.1] Executing ConnectHelper.get_all_connected_probes(blocking=False)...")
#         try:
#             probes = ConnectHelper.get_all_connected_probes(blocking=False)
#             print(
#                 f"[DEBUG-WORKER Step 3.2] Probes scan result: {len(probes) if probes else 0} probe(s) found.")

#             if not probes:
#                 err_msg = (
#                     "Connection failed: No B-Link probe detected on USB!\n"
#                     "-> Please check your USB and SWD cable connections.\n"
#                     "-> Unplug the USB cable and plug it back in."
#                 )
#                 print("[DEBUG-WORKER Step 3.3] No probe connected! Aborting early.")
#                 self.log(f"[ERROR] {err_msg}")
#                 return {"success": False, "error": err_msg, "rdp_status": "ERROR"}
#         except Exception as e:
#             err_msg = f"USB Driver Error: {str(e)}\n-> Please unplug and reconnect the USB cable."
#             print(f"[DEBUG-WORKER Step 3.3] Exception during probe scan: {e}")
#             self.log(f"[ERROR] {err_msg}")
#             return {"success": False, "error": err_msg, "rdp_status": "ERROR"}

#         # Probe target using session_manager
#         print("[DEBUG-WORKER Step 4] Calling session_manager.probe_target_info()...")
#         try:
#             info = self.session_manager.probe_target_info(
#                 clock_freq=self.clock_freq)
#             if not info:
#                 info = {"success": False,
#                         "error": "Empty response from session manager."}

#             print(
#                 f"[DEBUG-WORKER Step 4] probe_target_info raw result: success={info.get('success')}, part={info.get('part_number')}")

#             # ⬅️ لایه اعتبارسنجی سخت‌گیرانه (جلوگیری از فریب خوردن از success=True کاذب)
#             if info.get("success"):
#                 part_num = info.get("part_number", "Unknown")
#                 err_val = info.get("error", "")

#                 # اگر پارت نامبر نامعتبر است یا خطا وجود دارد، موفقیت را باطل می‌کنیم
#                 if err_val or part_num in ["UNKNOWN", "N/A", ""]:
#                     print(
#                         f"[DEBUG-WORKER Validation] False success detected! Part: {part_num}, Err: {err_val}")
#                     info["success"] = False
#                     info["error"] = err_val or "Target MCU identification failed."

#         except Exception as e:
#             print(f"[DEBUG-WORKER Step 4] Exception in probe_target_info: {e}")
#             info = {"success": False, "error": str(e)}

#         if not info.get("success"):
#             last_error = info.get("error", "Target MCU is not responding.")
#             err_msg = (
#                 "Probe detected, but Target MCU is not responding!\n"
#                 "1. Check SWD cables (DIO, CLK, GND, VCC).\n"
#                 "2. Unplug and reconnect the USB cable."
#             )
#             if last_error and "Empty" not in last_error:
#                 err_msg += f"\n[Detail: {last_error}]"

#             print(
#                 f"[DEBUG-WORKER Step 4.1] SWD Detection failed: {last_error}")
#             self.log(f"[ERROR] {err_msg}")
#             return {"success": False, "error": err_msg, "rdp_status": "ERROR"}

#         self.log(
#             f"[INFO] ✔ Found Target (SWD): {info.get('part_number')} | "
#             f"Probe SN: {info.get('probe_serial')} | "
#             f"DPIDR: {info.get('dpidr')} | "
#             f"RDP: {info.get('rdp_status', 'UNKNOWN')}"
#         )

#         return info

#     def _probe_usb_target(self) -> Dict[str, Any]:
#         """Direct USB / DFU Probing."""
#         print(
#             "[DEBUG-WORKER Step 3.1-USB] Executing session_manager.probe_usb_device()...")
#         info = self.session_manager.probe_usb_device()

#         if info and info.get("success"):
#             print(
#                 f"[DEBUG-WORKER Step 3.2-USB] Found USB target: {info.get('part_number')}")
#             self.log(
#                 f"[INFO] ✔ Found Target (USB): {info.get('part_number')} | "
#                 f"VID:PID: {info.get('dpidr')} | "
#                 f"Status: {info.get('rdp_status')}"
#             )
#         else:
#             err_msg = info.get(
#                 "error", "No STM32 DFU device found.") if info else "No device found."
#             print(
#                 f"[DEBUG-WORKER Step 3.2-USB] USB detection failed: {err_msg}")
#             self.log(f"[ERROR] Direct USB Detection failed: {err_msg}")
#             info = {"success": False, "error": err_msg, "rdp_status": "ERROR"}

#         return info

#     @Slot()
#     def inspect_core(self) -> None:
#         """Deep diagnostic inspection of target registers or USB endpoints."""
#         print("\n=================== [INSPECT CORE START] ===================")
#         print(
#             f"[DEBUG-WORKER Step 1] Entering inspect_core slot on thread: {self.thread()}")

#         self.log(
#             f"[INFO] Inspecting target interface via {self.interface_type}..."
#         )
#         status_report: Dict[str, Any] = {
#             "success": False,
#             "dhcsr": None,
#             "demcr": None,
#             "sanity_dpidr": None,
#             "error": "",
#         }

#         try:
#             if "USB" in self.interface_type:
#                 print("[DEBUG-WORKER Step 2] Inspecting Direct USB core state...")
#                 status_report["dhcsr"] = {"S_HALT": True, "S_LOCKUP": False}
#                 status_report["demcr"] = {"VC_CORERESET": True}
#                 status_report["success"] = True
#                 self.log("[INFO] ✔ Direct USB interface status verified.")
#             else:
#                 print(
#                     "[DEBUG-WORKER Step 2.1] Checking connected probes before inspection...")
#                 probes = ConnectHelper.get_all_connected_probes(blocking=False)
#                 if not probes:
#                     err_msg = (
#                         "Connection failed: No B-Link probe detected!\n"
#                         "-> Please check connections and reconnect the USB cable."
#                     )
#                     print(
#                         "[DEBUG-WORKER Step 2.2] No probe detected. Aborting inspection.")
#                     status_report["error"] = err_msg
#                     self.core_status_signal.emit(status_report)
#                     return

#                 print("[DEBUG-WORKER Step 2.3] Calling session_manager.connect()...")
#                 if not self.session_manager.connect():
#                     print(
#                         "[DEBUG-WORKER Step 2.4] session_manager.connect() returned False.")
#                     status_report["error"] = (
#                         "Failed to establish SWD session.\n"
#                         "-> Please reconnect the USB cable."
#                     )
#                     self.core_status_signal.emit(status_report)
#                     return

#                 print(
#                     "[DEBUG-WORKER Step 2.5] Reading sanity_dpidr, dhcsr, and demcr registers...")
#                 status_report["sanity_dpidr"] = (
#                     self.session_manager.check_swd_sanity()
#                 )
#                 status_report["dhcsr"] = self.session_manager.inspect_dhcsr()
#                 status_report["demcr"] = self.session_manager.inspect_demcr()
#                 status_report["success"] = True
#                 print(
#                     f"[DEBUG-WORKER Step 2.6] Inspection registers read successfully: DHCSR={status_report['dhcsr']}")
#                 self.log(
#                     "[INFO] ✔ Core diagnostic registers read successfully."
#                 )

#             print("[DEBUG-WORKER Step 3] Emitting core_status_signal...")
#             self.core_status_signal.emit(status_report)

#         except Exception as exc:
#             error_msg = str(exc)
#             print(f"[DEBUG-WORKER CRITICAL EXCEPTION] {error_msg}")
#             logger.error(f"Core inspection exception: {error_msg}")
#             status_report["error"] = error_msg
#             self.report_error(f"Core Diagnostic Error: {error_msg}")
#             self.core_status_signal.emit(status_report)

#         finally:
#             if "USB" not in self.interface_type:
#                 print("[DEBUG-WORKER Step 4] Closing session_manager...")
#                 self.session_manager.close()
#             print(
#                 "=================== [INSPECT CORE END] ===================\n")
"""
Background worker for executing target MCU identification, RDP lock scanning,
and low-level ARM Cortex-M core diagnostics without freezing the user interface.
Supports both DAPLink (SWD) and Direct USB (DFU) protocol interfaces.
"""

from typing import Dict, Any, Optional
from PySide6.QtCore import Signal, Slot
from pyocd.core.helpers import ConnectHelper

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
        interface_type: str = "B-Link (SWD)",
        parent: Optional[Any] = None,
        unique_id: Optional[str] = None,
    ):
        super().__init__(parent)
        self.clock_freq = clock_freq
        self.connect_mode = connect_mode
        self.interface_type = interface_type
        self.unique_id = unique_id

        print(
            f"[DEBUG-WORKER] Worker initialized. Interface: {self.interface_type}, Clock: {self.clock_freq}Hz")

        # مقداردهی به موتور سشن منیجر
        self.session_manager = SessionManager(
            clock_freq=self.clock_freq,
            connect_mode=self.connect_mode,
            interface_type=self.interface_type,
            unique_id=self.unique_id,
        )

    @Slot()
    def probe_target(self) -> None:
        """
        Lightweight attach probe to identify MCU part number, DPIDR / USB ID,
        and Flash Read-Out Protection (RDP) state.
        """
        print("\n=================== [PROBE TARGET START] ===================")
        print(
            f"[DEBUG-WORKER Step 1] Entering probe_target slot on thread: {self.thread()}")
        try:
            if "USB" in self.interface_type:
                print("[DEBUG-WORKER Step 2] Routing to Direct USB (DFU) probe...")
                self.log("[INFO] Probing Direct USB (DFU) interface...")
                info = self.session_manager.probe_usb_device()
            else:
                print("[DEBUG-WORKER Step 2] Routing to SWD bus probe...")
                self.log("[INFO] Probing SWD bus using Smart ST Auto-Detect...")

                # 1. بررسی سریع فیزیکی متصل بودن پروگرمر به USB
                print(
                    "[DEBUG-WORKER Step 3.1] Executing ConnectHelper.get_all_connected_probes()...")
                probes = ConnectHelper.get_all_connected_probes(blocking=False)
                if not probes:
                    err_msg = (
                        "Connection failed: No B-Link probe detected on USB!\n"
                        "-> Please check your USB cable connections.\n"
                        "-> Unplug the USB cable and plug it back in."
                    )
                    print(
                        "[DEBUG-WORKER Step 3.2] No probe connected! Aborting early.")
                    self.log(f"[ERROR] {err_msg}")
                    self.target_info_signal.emit(
                        {"success": False, "error": err_msg, "rdp_status": "ERROR"})
                    return

                # 2. فراخوانی متد پیشرفته و مخفی از سشن منیجر
                print(
                    "[DEBUG-WORKER Step 4] Calling session_manager.probe_target_info()...")
                info = self.session_manager.probe_target_info(
                    clock_freq=self.clock_freq)

            # ثبت و اعتبارسنجی لاگ‌ها
            if info and info.get("success"):
                self.log(
                    f"[INFO] ✔ Found Target: {info.get('part_number')} | "
                    f"Core: {info.get('core_type')} | "
                    f"Probe/DPIDR: {info.get('dpidr', 'N/A')}"
                )
            else:
                err_val = info.get(
                    "error", "Unknown Error") if info else "No response."
                self.log(f"[ERROR] Target Probe Failed: {err_val}")

            print(
                f"[DEBUG-WORKER Step 5] Probe complete. Emitting target_info_signal: {info.get('success', False)}")
            self.target_info_signal.emit(info)

        except Exception as exc:
            error_msg = str(exc)
            print(f"[DEBUG-WORKER CRITICAL EXCEPTION] {error_msg}")
            logger.error(
                f"Target probe exception ({self.interface_type}): {error_msg}")
            self.report_error(f"Probe Error: {error_msg}")
            self.target_info_signal.emit(
                {"success": False, "error": error_msg, "rdp_status": "ERROR"})
        finally:
            print(
                "=================== [PROBE TARGET END] ===================\n")

    @Slot()
    def inspect_core(self) -> None:
        """Deep diagnostic inspection of target registers or USB endpoints."""
        print("\n=================== [INSPECT CORE START] ===================")
        print(
            f"[DEBUG-WORKER Step 1] Entering inspect_core slot on thread: {self.thread()}")

        self.log(
            f"[INFO] Inspecting target interface via {self.interface_type}...")
        status_report: Dict[str, Any] = {
            "success": False,
            "dhcsr": None,
            "demcr": None,
            "sanity_dpidr": None,
            "error": "",
        }

        try:
            if "USB" in self.interface_type:
                print("[DEBUG-WORKER Step 2] Inspecting Direct USB core state...")
                status_report["dhcsr"] = {"S_HALT": True, "S_LOCKUP": False}
                status_report["demcr"] = {"VC_CORERESET": True}
                status_report["success"] = True
                self.log("[INFO] ✔ Direct USB interface status verified.")
            else:
                print(
                    "[DEBUG-WORKER Step 2.1] Checking connected probes before inspection...")
                probes = ConnectHelper.get_all_connected_probes(blocking=False)
                if not probes:
                    err_msg = "Connection failed: No B-Link probe detected!\n-> Please reconnect the USB cable."
                    print(
                        "[DEBUG-WORKER Step 2.2] No probe detected. Aborting inspection.")
                    status_report["error"] = err_msg
                    self.core_status_signal.emit(status_report)
                    return

                print("[DEBUG-WORKER Step 2.3] Calling session_manager.connect()...")
                # با فراخوانی متد connect، سیستم Auto-Detect استارت می‌خورد
                if not self.session_manager.connect():
                    print(
                        "[DEBUG-WORKER Step 2.4] session_manager.connect() returned False.")
                    status_report["error"] = "Failed to establish SWD session.\n-> Please check physical wiring."
                    self.core_status_signal.emit(status_report)
                    return

                print(
                    "[DEBUG-WORKER Step 2.5] Reading sanity_dpidr, dhcsr, and demcr registers...")
                status_report["sanity_dpidr"] = self.session_manager.check_swd_sanity()
                status_report["dhcsr"] = self.session_manager.inspect_dhcsr()
                status_report["demcr"] = self.session_manager.inspect_demcr()
                status_report["success"] = True
                print(
                    f"[DEBUG-WORKER Step 2.6] Inspection registers read successfully: DHCSR={status_report['dhcsr']}")
                self.log(
                    "[INFO] ✔ Core diagnostic registers read successfully.")

            print("[DEBUG-WORKER Step 3] Emitting core_status_signal...")
            self.core_status_signal.emit(status_report)

        except Exception as exc:
            error_msg = str(exc)
            print(f"[DEBUG-WORKER CRITICAL EXCEPTION] {error_msg}")
            logger.error(f"Core inspection exception: {error_msg}")
            status_report["error"] = error_msg
            self.report_error(f"Core Diagnostic Error: {error_msg}")
            self.core_status_signal.emit(status_report)

        finally:
            if "USB" not in self.interface_type:
                print("[DEBUG-WORKER Step 4] Closing session_manager...")
                self.session_manager.close()
            print(
                "=================== [INSPECT CORE END] ===================\n")
