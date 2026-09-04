# """
# Low-level SWD/pyOCD and Direct USB session manager handling probe connections,
# USB DFU discovery, stealth auto-detect strategies, core register inspection,
# and unified memory read/write operations.
# (Features Universal ARM Global Pack Auto-Downloader with Global Signal Bus)
# """

# import subprocess
# import os
# import tempfile
# import glob
# import re
# import sys
# import time
# from typing import Optional, Dict, Any, List

# from pyocd.core.helpers import ConnectHelper
# from pyocd.core.session import Session
# from pyocd.core.target import Target
# from pyocd.flash.file_programmer import FileProgrammer
# from pyocd.flash.eraser import FlashEraser
# from pyocd.target.pack import pack_target

# from src.common.logger import get_logger
# from src.common.registers import (
#     DHCSR_ADDR,
#     DEMCR_ADDR,
#     DHCSR_BITS,
#     DEMCR_BITS,
#     DBGMCU_IDCODE_ADDR,
#     STM32_DEVID_MAP
# )
# from src.common.resources import EXE_DFU
# from src.common.paths import get_path

# # ایمپورت سیستم سیگنال سراسری
# from src.common.pack_downloader import DownloadSignalBus

# logger = get_logger("SessionManager")


# class SessionManager:
#     """
#     Manages physical SWD debug probe sessions (via pyOCD) as well as
#     Direct USB (DFU/CDC) hardware interfaces with ARM Cortex-M microcontrollers.
#     """

#     def __init__(
#         self,
#         target_type: Optional[str] = None,
#         clock_freq: int = 1000000,
#         connect_mode: str = "under-reset",
#         interface_type: str = "B-Link (SWD)",
#         unique_id: Optional[str] = None,
#     ):
#         self.target_type = target_type
#         self.clock_freq = clock_freq
#         self.connect_mode = connect_mode
#         self.interface_type = interface_type
#         self.unique_id = unique_id

#         # SWD Session / Target objects
#         self.session: Optional[Session] = None
#         self.target: Optional[Target] = None

#         # USB Direct Session state
#         self.is_usb_connected: bool = False

#         self.available_packs = []

#         print(f"\n[DEBUG-SESSION INIT] SessionManager created.")
#         print(f"  -> Interface Type: {self.interface_type}")
#         print(f"  -> Target Type: {self.target_type}")
#         print(f"  -> Clock Frequency: {self.clock_freq} Hz")
#         print(f"  -> Connect Mode: {self.connect_mode}")
#         print(
#             f"  -> Target Probe UID: {self.unique_id or 'Auto-Detect (First Available)'}\n")

#     def _stealth_auto_detect(self) -> Optional[str]:
#         """Connects via generic 'cortex_m', reads DBGMCU_IDCODE, and resolves true MCU name."""
#         print(
#             "\n[DEBUG-SESSION AUTO-DETECT] Launching Stealth Probe for Smart ST Detection...")
#         try:
#             options = {
#                 "connect_mode": "attach",
#                 "frequency": 1000000,
#                 "target_override": "cortex_m",  # اجبار به اتصال کور و عمومی
#                 "halt_on_connect": False,
#             }
#             session = ConnectHelper.session_with_chosen_probe(
#                 blocking=False, options=options, unique_id=self.unique_id
#             )
#             if not session:
#                 print("[DEBUG-SESSION AUTO-DETECT] No probe found.")
#                 return None

#             session.open()
#             target = session.board.target

#             try:
#                 # خواندن رجیستر اختصاصی ST
#                 idcode = target.read32(DBGMCU_IDCODE_ADDR)
#                 dev_id = idcode & 0xFFF
#                 rev_id = (idcode >> 16) & 0xFFFF

#                 if dev_id in STM32_DEVID_MAP:
#                     detected_mcu = STM32_DEVID_MAP[dev_id]
#                     print(
#                         f"[DEBUG-SESSION AUTO-DETECT] ✔ Found ST MCU: DEV_ID=0x{dev_id:03X}, REV=0x{rev_id:04X} -> {detected_mcu.upper()}")
#                     return detected_mcu
#                 else:
#                     print(
#                         f"[DEBUG-SESSION AUTO-DETECT] ✖ Unknown DEV_ID 0x{dev_id:03X} at 0xE0042000.")
#             except Exception as mem_exc:
#                 print(
#                     f"[DEBUG-SESSION AUTO-DETECT] Memory read failed (Not an ST MCU or read-protected): {mem_exc}")
#             finally:
#                 session.close()

#         except Exception as e:
#             print(f"[DEBUG-SESSION AUTO-DETECT EXCEPTION] {e}")

#         return None

#     def _download_missing_pack(self, target_name: str) -> bool:
#         print(f"\n[DEBUG-SESSION] ===============================================")
#         print(f"[DEBUG-SESSION] 🌍 ONLINE CMSIS-PACK DOWNLOADER TRIGGERED")
#         print(
#             f"[DEBUG-SESSION] Fetching hardware definitions for: {target_name.upper()}")
#         print(f"[DEBUG-SESSION] ===============================================\n")

#         from src.common.pack_downloader import DownloadSignalBus
#         from PySide6.QtCore import QMetaObject, Qt, Q_RETURN_ARG, Q_ARG

#         bus = DownloadSignalBus.instance()
#         bus.download_preparing.emit(target_name.upper())

#         if bus.dialog_instance:
#             user_agreed = False
#             try:
#                 user_agreed = QMetaObject.invokeMethod(
#                     bus.dialog_instance,
#                     "ask_permission",
#                     Qt.ConnectionType.BlockingQueuedConnection,
#                     Q_RETURN_ARG(bool),
#                     Q_ARG(str, target_name.upper())
#                 )
#             except Exception as e:
#                 logger.error(f"Could not ask for permission: {e}")
#                 user_agreed = True

#             if not user_agreed:
#                 logger.warning(
#                     f"User cancelled the required download for {target_name.upper()}.")
#                 bus.download_finished.emit(False, "Cancelled by user.")
#                 return False

#         logger.warning(
#             f"Downloading required CMSIS-Pack for {target_name.upper()} from ARM global index... Please wait.")
#         bus.download_started.emit(target_name.upper())

#         class OutputCatcher:
#             def __init__(self, signal_bus):
#                 self.bus = signal_bus
#                 self.terminal = sys.__stdout__
#                 self.last_pct = -1
#                 self.buffer = ""

#             def write(self, message):
#                 if self.bus.cancel_requested:
#                     raise InterruptedError("USER_CANCELLED")

#                 self.terminal.write(message)
#                 self.buffer += message

#                 if '\n' in message or '\r' in message:
#                     match = re.search(r'\((\d+)\s*/\s*(\d+)\)', self.buffer)
#                     if match:
#                         current = int(match.group(1))
#                         total = int(match.group(2))
#                         if total > 0:
#                             pct = int((current / total) * 100)
#                             if pct != self.last_pct:
#                                 self.last_pct = pct
#                                 self.bus.download_progress.emit(
#                                     pct, f"Downloading Index & Packages: {current} / {total}")
#                     elif "Downloading packs" in self.buffer:
#                         self.bus.download_progress.emit(
#                             -1, f"Downloading pack for {target_name.upper()}...")
#                     elif "Extracting" in self.buffer or "Parsing" in self.buffer:
#                         self.bus.download_progress.emit(100, "")
#                     self.buffer = ""

#             def flush(self):
#                 self.terminal.flush()

#         old_stdout = sys.stdout
#         old_argv = sys.argv
#         sys.argv = ["pyocd", "pack", "install", target_name]

#         try:
#             sys.stdout = OutputCatcher(bus)
#             from pyocd.__main__ import main as pyocd_main
#             pyocd_main()

#             try:
#                 pack_target.PackTargets.clear_cache()
#             except AttributeError:
#                 pass

#             msg = f"✔ Pack for {target_name.upper()} downloaded and cached successfully!"
#             logger.info(msg)
#             bus.download_finished.emit(True, msg)
#             return True

#         except InterruptedError:
#             msg = f"Download for {target_name.upper()} was cancelled by user."
#             logger.warning(msg)
#             bus.download_finished.emit(False, msg)
#             return False

#         except SystemExit as se:
#             if se.code == 0:
#                 try:
#                     pack_target.PackTargets.clear_cache()
#                 except AttributeError:
#                     pass
#                 msg = f"✔ Pack for {target_name.upper()} downloaded and cached successfully!"
#                 logger.info(msg)
#                 bus.download_finished.emit(True, msg)
#                 return True
#             else:
#                 msg = f"Failed to download pack for {target_name.upper()} (Exit code {se.code}). Check internet connection."
#                 logger.error(msg)
#                 bus.download_finished.emit(False, msg)
#                 return False

#         except Exception as e:
#             msg = f"Error communicating with ARM index: {str(e)}"
#             print(f"[DEBUG-SESSION] Pack downloader exception: {e}")
#             logger.error(msg)
#             bus.download_finished.emit(False, msg)
#             return False

#         finally:
#             sys.argv = old_argv
#             sys.stdout = old_stdout

#     @staticmethod
#     def list_probes() -> List[Any]:
#         print("[DEBUG-SESSION list_probes] Scanning for connected debug probes...")
#         probes = ConnectHelper.get_all_connected_probes()
#         print(
#             f"[DEBUG-SESSION list_probes] Found {len(probes) if probes else 0} probe(s).")
#         if not probes:
#             logger.warning("No B-Link debug probes found via USB.")
#         return probes

#     def probe_usb_device(self) -> Dict[str, Any]:
#         print("\n[DEBUG-SESSION USB_PROBE] Starting USB DFU device discovery...")
#         logger.info(
#             "Probing for Direct USB (DFU) target devices using dfu-util...")
#         info = {
#             "success": False,
#             "probe_serial": "N/A",
#             "part_number": "STM32_DFU_DEVICE",
#             "dpidr": "N/A",
#             "core_type": "CORTEX-M (USB)",
#             "rdp_status": "UNKNOWN",
#             "error": "",
#         }

#         try:
#             print(f"[DEBUG-SESSION USB_PROBE] Running command: {EXE_DFU} -l")
#             result = subprocess.run(
#                 [EXE_DFU, "-l"], capture_output=True, text=True, check=False)
#             output = result.stdout.lower()

#             if "found dfu" in output and "0483:df11" in output:
#                 info["success"] = True
#                 info["dpidr"] = "0483:DF11 (VID:PID)"
#                 info["probe_serial"] = "USB_DFU_Link"
#                 info["rdp_status"] = "LEVEL 0 (ASSUMED)"
#                 logger.info(
#                     "✔ STM32 DFU Device detected successfully via dfu-util.")
#             else:
#                 info["error"] = "No STM32 DFU device found. Make sure BOOT0=1 and device is plugged in."
#                 logger.warning("✖ No Direct USB (DFU) device detected.")

#         except FileNotFoundError:
#             err_msg = f"dfu-util not found at {EXE_DFU}! Please ensure it is bundled correctly."
#             info["error"] = err_msg
#             logger.error(err_msg)
#         except Exception as e:
#             info["error"] = str(e)
#             logger.error(f"DFU probe exception: {str(e)}")

#         return info

#     def probe_target_info(self, clock_freq: int = 1000000, target_type: Optional[str] = None) -> Dict[str, Any]:
#         """
#         Lightweight attach session.
#         If target_type is 'auto', resolves ST MCU names via DBGMCU.
#         Otherwise, connects using the user-specified target.
#         """
#         current_target = target_type or self.target_type or "auto"
#         print(
#             f"\n[DEBUG-SESSION PROBE_INFO] Starting probe_target_info with clock={clock_freq}Hz, Target='{current_target}'")

#         if "USB" in self.interface_type:
#             print("[DEBUG-SESSION PROBE_INFO] Routing to USB probe handler.")
#             return self.probe_usb_device()

#         info = {
#             "success": False,
#             "probe_serial": "Unknown",
#             "part_number": "Unknown",
#             "dpidr": "N/A",
#             "core_type": "Unknown",
#             "error": "",
#         }

#         resolved_target = "cortex_m"
#         is_auto_mode = current_target.lower(
#         ) in ["auto", "none", "", "cortex_m", "stmicroelectronics"]

#         if is_auto_mode:
#             detected = self._stealth_auto_detect()
#             if detected:
#                 resolved_target = detected
#         else:
#             resolved_target = current_target

#         try:
#             options = {
#                 "connect_mode": "attach",
#                 "frequency": clock_freq,
#                 "target_override": resolved_target,
#                 "halt_on_connect": False,
#             }

#             print(f"[DEBUG-SESSION PROBE_INFO] Connecting options: {options}")

#             session = ConnectHelper.session_with_chosen_probe(
#                 blocking=False, options=options, unique_id=self.unique_id
#             )

#             if session is None:
#                 raise Exception("No B-Link/SWD probe detected on USB.")

#             print("[DEBUG-SESSION PROBE_INFO] Probe found. Opening session...")
#             session.open()

#             try:
#                 info["probe_serial"] = str(session.probe.unique_id)
#             except Exception:
#                 info["probe_serial"] = "Detected"

#             target = session.board.target
#             dpidr_val = 0
#             try:
#                 dpidr_val = session.probe.read_dp(0x0)
#             except:
#                 pass

#             info["dpidr"] = f"0x{dpidr_val:08X}" if dpidr_val else "Detected"

#             # استخراج هسته
#             try:
#                 code = target.cores[0].core_type
#                 try:
#                     from pyocd.coresight.core_ids import CORE_TYPE_NAME
#                     info["core_type"] = str(
#                         CORE_TYPE_NAME.get(code, code)).upper()
#                 except ImportError:
#                     info["core_type"] = str(code).upper()
#             except Exception:
#                 info["core_type"] = "CORTEX-M"

#             # 🌟 جادوی تشخیص اتوماتیک قطعه (بدون تکیه بر سریال پروگرمر)
#             if is_auto_mode:
#                 info["part_number"] = "CORTEX-M (Generic)"
#                 try:
#                     idcode = target.read32(DBGMCU_IDCODE_ADDR)
#                     dev_id = idcode & 0xFFF
#                     if dev_id in STM32_DEVID_MAP:
#                         info["part_number"] = STM32_DEVID_MAP[dev_id].upper()
#                 except:
#                     pass  # قفل شده یا غیر ST
#             else:
#                 info["part_number"] = current_target.upper()

#             info["success"] = True
#             print(
#                 f"[DEBUG-SESSION PROBE_INFO] Success! Target Part: {info['part_number']}, Core: {info['core_type']}")
#             session.close()

#         except Exception as e:
#             print(f"[DEBUG-SESSION PROBE_INFO EXCEPTION] Attempt failed: {e}")
#             info["error"] = str(e)

#         print(f"[DEBUG-SESSION PROBE_INFO] Final result: {info}\n")
#         return info

#     def _open_session(self, freq: int, mode: str, target_name: Optional[str], _auto_downloaded: bool = False) -> bool:
#         print(
#             f"\n[DEBUG-SESSION _open_session] Attempting -> Target: '{target_name}' | Clock: {freq}Hz | Mode: '{mode}'")
#         options: Dict[str, Any] = {
#             "connect_mode": mode,
#             "frequency": freq,
#             "target_override": target_name,
#             "reset_type": "hw" if mode == "under-reset" else "sw",
#             "resume_on_disconnect": False,
#         }

#         if self.available_packs:
#             options["pack"] = self.available_packs

#         try:
#             logger.info(
#                 f"Attempting SWD connection -> Target: '{target_name}' | Clock: {freq // 1000} kHz | Mode: '{mode}'...")
#             self.session = ConnectHelper.session_with_chosen_probe(
#                 options=options, unique_id=self.unique_id)

#             if self.session is None:
#                 print(
#                     "[DEBUG-SESSION _open_session] session_with_chosen_probe returned None.")
#                 return False

#             print("[DEBUG-SESSION _open_session] Opening session...")
#             self.session.open()
#             self.target = self.session.target
#             print("[DEBUG-SESSION _open_session] SWD session successfully established!")
#             logger.info("SWD session established successfully.")
#             return True

#         except Exception as e:
#             err_str = str(e)
#             match = re.search(
#                 r"target type (\w+) not recognized", err_str, re.IGNORECASE)
#             if match and not _auto_downloaded:
#                 missing_mcu = match.group(1)
#                 if self._download_missing_pack(missing_mcu):
#                     print(
#                         "[DEBUG-SESSION _open_session] Download complete. Retrying connection...")
#                     return self._open_session(freq, mode, target_name, _auto_downloaded=True)

#             print(f"[DEBUG-SESSION _open_session EXCEPTION] Failed: {err_str}")
#             logger.error(f"Connection attempt failed: {err_str}")
#             self.close()
#             return False

#     def connect(self) -> bool:
#         """Connect to target microcontroller smartly resolving its true identity."""
#         print(
#             f"\n[DEBUG-SESSION CONNECT] Starting connect() procedure. Interface: {self.interface_type}")
#         if "USB" in self.interface_type:
#             print(
#                 "[DEBUG-SESSION CONNECT] USB mode active. Bypassing SWD connection sequence.")
#             logger.info("Establishing direct USB session...")
#             self.is_usb_connected = True
#             return True

#         # =========================================================================
#         # 🌟 مرحله 0: تشخیص هوشمند پیش از اتصال
#         # =========================================================================
#         target_to_use = self.target_type
#         if not target_to_use or target_to_use.lower() in ["auto", "none", "", "cortex_m", "stmicroelectronics"]:
#             detected = self._stealth_auto_detect()
#             if detected:
#                 target_to_use = detected
#             else:
#                 target_to_use = "cortex_m"
#             self.target_type = target_to_use

#         print(
#             f"[DEBUG-SESSION CONNECT] Final Resolved Target: {self.target_type}")

#         # Level 1: Primary attempt
#         if self._open_session(self.clock_freq, self.connect_mode, self.target_type):
#             return True

#         # Level 2: Generic Cortex-M profile fallback
#         if self.target_type != "cortex_m":
#             print(
#                 "[DEBUG-SESSION CONNECT] Level 2 attempt -> Retrying with generic 'cortex_m' profile...")
#             logger.warning(
#                 "Retrying connection with generic 'cortex_m' profile...")
#             if self._open_session(self.clock_freq, self.connect_mode, "cortex_m"):
#                 self.target_type = "cortex_m"
#                 return True

#         # Level 3: Emergency diagnostic fallback (50kHz, attach mode)
#         print("[DEBUG-SESSION CONNECT] Level 3 attempt -> Diagnostics Fallback: 50 kHz clock & 'attach' mode...")
#         logger.warning(
#             "SWD connection error. Switching to Diagnostics Fallback: 50 kHz clock & 'attach' mode...")
#         fallback_target = "cortex_m" if self.target_type == "cortex_m" else self.target_type

#         if self._open_session(50000, "attach", fallback_target):
#             self.clock_freq = 50000
#             self.connect_mode = "attach"
#             self.target_type = fallback_target
#             print("[DEBUG-SESSION CONNECT] Diagnostics Fallback successful!")
#             return True

#         print(
#             "[DEBUG-SESSION CONNECT CRITICAL] All SWD connection strategies failed completely.")
#         logger.critical(
#             "All SWD connection strategies failed. Verify physical wiring.")
#         return False

#     def check_swd_sanity(self) -> Optional[int]:
#         print("\n[DEBUG-SESSION SANITY] Checking SWD physical bus integrity...")
#         if "USB" in self.interface_type:
#             print("[DEBUG-SESSION SANITY] USB mode active, skipping SWD check.")
#             logger.info("SWD Sanity bypassed (Direct USB mode active).")
#             return 0x00485740

#         if not self.session or not self.target:
#             print(
#                 "[DEBUG-SESSION SANITY ERROR] Session or target is not initialized. Connect first!")
#             logger.error("Session is not open. Call connect() first.")
#             return None

#         try:
#             dpidr = self.session.probe.read_dp(0x0)
#             expected_ids = [0x1BA01477, 0x2BA01477]

#             print(f"[DEBUG-SESSION SANITY] Read DPIDR register: 0x{dpidr:08X}")
#             logger.info(f"Read DP IDCODE: 0x{dpidr:08X}")
#             if dpidr in expected_ids:
#                 print("[DEBUG-SESSION SANITY] Pass! Valid DPIDR match found.")
#                 logger.info("SWD Sanity Check PASSED (Valid DPIDR detected).")
#             else:
#                 print(
#                     f"[DEBUG-SESSION SANITY WARNING] Unexpected DP IDCODE: 0x{dpidr:08X}")
#                 logger.warning(f"Unexpected DP IDCODE detected: 0x{dpidr:08X}")
#             return dpidr

#         except Exception as e:
#             print(
#                 f"[DEBUG-SESSION SANITY EXCEPTION] Failed to read DP IDCODE: {e}")
#             logger.error(f"Failed to read DP IDCODE: {str(e)}")
#             return None

#     def inspect_dhcsr(self) -> Optional[Dict[str, bool]]:
#         """Read and decode DHCSR (Debug Halting Control and Status Register)."""
#         print("\n[DEBUG-SESSION DHCSR] Inspecting DHCSR register...")
#         if "USB" in self.interface_type:
#             print("[DEBUG-SESSION DHCSR] USB mode active. Returning mock DHCSR flags.")
#             return {"S_HALT": True, "S_SLEEP": False, "S_LOCKUP": False, "C_DEBUGEN": True}

#         if not self.target:
#             print("[DEBUG-SESSION DHCSR ERROR] Target is not connected.")
#             return None

#         try:
#             raw_val = self.target.read32(DHCSR_ADDR)
#             print(
#                 f"[DEBUG-SESSION DHCSR] Raw DHCSR value at 0x{DHCSR_ADDR:08X}: 0x{raw_val:08X}")
#             decoded_flags = {}
#             for bit_pos, (label, _desc) in DHCSR_BITS.items():
#                 is_set = bool((raw_val >> bit_pos) & 1)
#                 decoded_flags[label] = is_set

#             print(f"[DEBUG-SESSION DHCSR] Decoded flags: {decoded_flags}")
#             if decoded_flags.get("S_LOCKUP"):
#                 print("[DEBUG-SESSION DHCSR CRITICAL] Core is in S_LOCKUP state!")
#                 logger.critical(
#                     "HARDWARE ALERT: Target core is in S_LOCKUP state!")
#             return decoded_flags

#         except Exception as e:
#             print(f"[DEBUG-SESSION DHCSR EXCEPTION] {e}")
#             logger.error(f"Failed to inspect DHCSR register: {str(e)}")
#             return None

#     def inspect_demcr(self) -> Optional[Dict[str, bool]]:
#         """Read and decode DEMCR (Debug Exception and Monitor Control Register)."""
#         print("\n[DEBUG-SESSION DEMCR] Inspecting DEMCR register...")
#         if "USB" in self.interface_type:
#             print("[DEBUG-SESSION DEMCR] USB mode active. Returning mock DEMCR flags.")
#             return {"TRCENA": True, "VC_CORERESET": True, "VC_HARDERR": False}

#         if not self.target:
#             print("[DEBUG-SESSION DEMCR ERROR] Target is not connected.")
#             return None

#         try:
#             raw_val = self.target.read32(DEMCR_ADDR)
#             print(
#                 f"[DEBUG-SESSION DEMCR] Raw DEMCR value at 0x{DEMCR_ADDR:08X}: 0x{raw_val:08X}")
#             decoded_flags = {}
#             for bit_pos, (label, _desc) in DEMCR_BITS.items():
#                 is_set = bool((raw_val >> bit_pos) & 1)
#                 decoded_flags[label] = is_set
#             print(f"[DEBUG-SESSION DEMCR] Decoded flags: {decoded_flags}")
#             return decoded_flags

#         except Exception as e:
#             print(f"[DEBUG-SESSION DEMCR EXCEPTION] {e}")
#             logger.error(f"Failed to inspect DEMCR register: {str(e)}")
#             return None

#     def read_memory_block8(self, addr: int, count: int) -> List[int]:
#         """Read raw bytes from physical hardware via USB DFU or SWD."""
#         print(
#             f"\n[DEBUG-SESSION READ8] Reading 8-bit memory block -> Addr: 0x{addr:08X}, Count: {count}")
#         if "USB" in self.interface_type:
#             logger.info(
#                 f"Executing Direct USB (DFU) Read at 0x{addr:08X} ({count} bytes)...")
#             temp_path = os.path.join(
#                 tempfile.gettempdir(), "dfu_read_dump.bin")

#             try:
#                 cmd = [
#                     EXE_DFU, "-a", "0", "-s", f"0x{addr:08X}:{count}", "-U", temp_path
#                 ]
#                 print(
#                     f"[DEBUG-SESSION READ8 USB] Executing command: {' '.join(cmd)}")
#                 result = subprocess.run(cmd, capture_output=True, text=True)
#                 print(
#                     f"[DEBUG-SESSION READ8 USB] Return code: {result.returncode}")

#                 if result.returncode == 0 and os.path.exists(temp_path):
#                     with open(temp_path, "rb") as f:
#                         raw_bytes = list(f.read())
#                     os.remove(temp_path)
#                     print(
#                         f"[DEBUG-SESSION READ8 USB] Successfully read {len(raw_bytes)} bytes.")
#                     logger.info("✔ DFU Memory Read successful.")
#                     return raw_bytes
#                 else:
#                     print(
#                         f"[DEBUG-SESSION READ8 USB ERROR] Stderr: {result.stderr}")
#                     logger.error(f"DFU Hardware Read Error: {result.stderr}")
#                     return []

#             except Exception as exc:
#                 print(f"[DEBUG-SESSION READ8 USB EXCEPTION] {exc}")
#                 logger.error(f"DFU Subprocess Error: {str(exc)}")
#                 return []

#         # DAPLink / SWD Mode
#         if self.target:
#             try:
#                 print(
#                     "[DEBUG-SESSION READ8 SWD] Reading memory block via SWD target object...")
#                 data = self.target.read_memory_block8(addr, count)
#                 print(
#                     f"[DEBUG-SESSION READ8 SWD] Read {len(data) if data else 0} bytes successfully.")
#                 return data
#             except Exception as e:
#                 print(f"[DEBUG-SESSION READ8 SWD EXCEPTION] {e}")
#                 logger.error(
#                     f"SWD Memory read failed at address 0x{addr:08X}: {str(e)}")
#                 return []
#         print("[DEBUG-SESSION READ8 ERROR] No active target session found.")
#         return []

#     def read_memory_32(self, addr: int, count: int = 1) -> Optional[List[int]]:
#         """Read 32-bit word(s) from target memory."""
#         print(
#             f"\n[DEBUG-SESSION READ32] Reading 32-bit words -> Addr: 0x{addr:08X}, Count: {count}")
#         if "USB" in self.interface_type:
#             byte_count = count * 4
#             raw_bytes = self.read_memory_block8(addr, byte_count)
#             if not raw_bytes or len(raw_bytes) < byte_count:
#                 print(
#                     "[DEBUG-SESSION READ32 USB] Insufficient bytes returned from memory read block.")
#                 return None

#             words = []
#             for i in range(0, len(raw_bytes), 4):
#                 chunk = raw_bytes[i:i+4]
#                 if len(chunk) == 4:
#                     word = chunk[0] | (chunk[1] << 8) | (
#                         chunk[2] << 16) | (chunk[3] << 24)
#                     words.append(word)
#             print(
#                 f"[DEBUG-SESSION READ32 USB] Reconstructed {len(words)} 32-bit words.")
#             return words

#         # DAPLink SWD Mode
#         if not self.target:
#             print("[DEBUG-SESSION READ32 ERROR] SWD target not initialized.")
#             return None
#         try:
#             print("[DEBUG-SESSION READ32 SWD] Calling target.read_memory_block32()...")
#             res = self.target.read_memory_block32(addr, count)
#             print(
#                 f"[DEBUG-SESSION READ32 SWD] Read {len(res) if res else 0} words successfully.")
#             return res
#         except Exception as e:
#             print(f"[DEBUG-SESSION READ32 SWD EXCEPTION] {e}")
#             logger.error(
#                 f"Memory read failed at address 0x{addr:08X}: {str(e)}")
#             return None

#     def write_memory_32(self, addr: int, val: int) -> bool:
#         """Write a 32-bit word to target memory address."""
#         print(
#             f"\n[DEBUG-SESSION WRITE32] Writing 32-bit word -> Addr: 0x{addr:08X}, Value: 0x{val:08X}")
#         if "USB" in self.interface_type:
#             print(
#                 "[DEBUG-SESSION WRITE32 USB] Direct USB memory write simulated/passed.")
#             logger.info(
#                 f"Direct USB memory write at 0x{addr:08X} = 0x{val:08X}")
#             return True

#         if not self.target:
#             print("[DEBUG-SESSION WRITE32 ERROR] Target session not open.")
#             return False
#         try:
#             self.target.write32(addr, val)
#             print("[DEBUG-SESSION WRITE32 SWD] Write operation completed successfully.")
#             return True
#         except Exception as e:
#             print(f"[DEBUG-SESSION WRITE32 SWD EXCEPTION] {e}")
#             logger.error(
#                 f"Memory write failed at address 0x{addr:08X}: {str(e)}")
#             return False

#     def erase_chip(self) -> bool:
#         """Executes Full Chip Erase over active interface (SWD or DFU)."""
#         print("\n[DEBUG-SESSION ERASE] Executing Full Chip Erase...")
#         if "USB" in self.interface_type:
#             logger.info("Executing Mass Erase via Direct USB DFU...")
#             try:
#                 cmd = [EXE_DFU, "-a", "0", "-s",
#                        "0x08000000:mass-erase:force", "-e"]
#                 print(
#                     f"[DEBUG-SESSION ERASE USB] Running command: {' '.join(cmd)}")
#                 result = subprocess.run(cmd, capture_output=True, text=True)
#                 print(
#                     f"[DEBUG-SESSION ERASE USB] Return code: {result.returncode}, Stdout: {result.stdout.strip()}")

#                 if result.returncode == 0 or "erasing" in result.stdout.lower():
#                     print("[DEBUG-SESSION ERASE USB] Full chip erase successful.")
#                     logger.info("✔ Full Chip Erase completed via USB DFU.")
#                     return True
#                 else:
#                     print(
#                         "[DEBUG-SESSION ERASE USB] Primary erase flag failed. Trying fallback command...")
#                     cmd_alt = [EXE_DFU, "-a", "0", "-s", "0x08000000", "-e"]
#                     res_alt = subprocess.run(
#                         cmd_alt, capture_output=True, text=True)
#                     print(
#                         f"[DEBUG-SESSION ERASE USB FALLBACK] Return code: {res_alt.returncode}")
#                     if res_alt.returncode == 0:
#                         print(
#                             "[DEBUG-SESSION ERASE USB FALLBACK] Fallback erase successful.")
#                         logger.info(
#                             "✔ Full Chip Erase completed via USB DFU (Fallback mode).")
#                         return True
#                     print(
#                         f"[DEBUG-SESSION ERASE USB ERROR] Erase failed. Stderr: {result.stderr or res_alt.stderr}")
#                     logger.error(
#                         f"DFU Erase Error: {result.stderr or res_alt.stderr}")
#                     return False
#             except Exception as e:
#                 print(f"[DEBUG-SESSION ERASE USB EXCEPTION] {e}")
#                 logger.error(f"DFU Mass Erase exception: {str(e)}")
#                 return False

#         # SWD Mode via pyOCD
#         if not self.session or not self.target:
#             print(
#                 "[DEBUG-SESSION ERASE SWD] Session not active. Attempting to connect...")
#             if not self.connect():
#                 return False
#         try:
#             # 🛡️ سپر امنیتی ضد تایم‌اوت
#             print(
#                 "[DEBUG-SESSION ERASE SWD] Engaging Anti-Timeout Shield (Halt & PRIMASK=1)...")
#             try:
#                 if self.target.get_state() != Target.State.HALTED:
#                     self.target.halt()
#                 self.target.write_core_register('primask', 1)
#             except Exception as e:
#                 print(
#                     f"[DEBUG-SESSION ERASE SWD] Warning during pre-erase halt: {e}")

#             print(
#                 "[DEBUG-SESSION ERASE SWD] Triggering FlashEraser with CHIP mode... (Waiting for Silicon)")
#             start_hw_time = time.time()

#             eraser = FlashEraser(self.session, FlashEraser.Mode.CHIP)
#             eraser.erase()

#             hw_duration = time.time() - start_hw_time
#             print(
#                 f"[DEBUG-SESSION ERASE SWD] ✔ Hardware Silicon Erase took {hw_duration:.2f} seconds!")
#             logger.info("✔ Full Chip Erase completed via SWD.")
#             return True
#         except Exception as e:
#             print(f"[DEBUG-SESSION ERASE SWD EXCEPTION] {e}")
#             logger.error(f"SWD Chip Erase failed: {str(e)}")
#             return False

#     def program_firmware(self, firmware_path: str, base_address: int = 0x08000000) -> bool:
#         """Programs binary/hex firmware file to target flash via SWD or DFU."""
#         print(
#             f"\n[DEBUG-SESSION PROGRAM] Flashing firmware -> File: {firmware_path}, Base Addr: 0x{base_address:08X}")
#         if not os.path.exists(firmware_path):
#             print(
#                 f"[DEBUG-SESSION PROGRAM ERROR] Firmware file path does not exist: {firmware_path}")
#             logger.error(f"Firmware file not found: {firmware_path}")
#             return False

#         if "USB" in self.interface_type:
#             logger.info(
#                 f"Flashing firmware via USB DFU: {firmware_path} -> 0x{base_address:08X}...")
#             try:
#                 cmd = [
#                     EXE_DFU, "-a", "0", "-s", f"0x{base_address:08X}:leave", "-D", firmware_path
#                 ]
#                 print(
#                     f"[DEBUG-SESSION PROGRAM USB] Running command: {' '.join(cmd)}")
#                 result = subprocess.run(cmd, capture_output=True, text=True)
#                 print(
#                     f"[DEBUG-SESSION PROGRAM USB] Return code: {result.returncode}")

#                 if result.returncode == 0:
#                     print(
#                         "[DEBUG-SESSION PROGRAM USB] Firmware successfully flashed and leave command sent.")
#                     logger.info(
#                         "✔ Firmware Flashed and reset executed successfully via USB DFU.")
#                     return True
#                 else:
#                     print(
#                         f"[DEBUG-SESSION PROGRAM USB ERROR] Stderr: {result.stderr}")
#                     logger.error(f"DFU Programming Error: {result.stderr}")
#                     return False
#             except Exception as e:
#                 print(f"[DEBUG-SESSION PROGRAM USB EXCEPTION] {e}")
#                 logger.error(f"DFU Programming exception: {str(e)}")
#                 return False

#         # SWD Mode via pyOCD
#         if not self.session or not self.target:
#             print(
#                 "[DEBUG-SESSION PROGRAM SWD] Session not active. Attempting to connect...")
#             if not self.connect():
#                 return False
#         try:
#             # 🛡️ سپر امنیتی ضد تایم‌اوت
#             print(
#                 "[DEBUG-SESSION PROGRAM SWD] Engaging Anti-Timeout Shield (Halt & PRIMASK=1)...")
#             try:
#                 if self.target.get_state() != Target.State.HALTED:
#                     self.target.halt()
#                 self.target.write_core_register('primask', 1)
#             except Exception as e:
#                 print(
#                     f"[DEBUG-SESSION PROGRAM SWD] Warning during pre-program halt: {e}")

#             print(
#                 "[DEBUG-SESSION PROGRAM SWD] Initializing FileProgrammer... (Waiting for Silicon)")
#             start_hw_time = time.time()

#             programmer = FileProgrammer(self.session)
#             programmer.program(firmware_path, base_address=base_address)

#             hw_duration = time.time() - start_hw_time
#             print(
#                 f"[DEBUG-SESSION PROGRAM SWD] ✔ Hardware Flash & Verify took {hw_duration:.2f} seconds!")
#             logger.info("✔ Firmware Flashed successfully via SWD.")
#             return True
#         except Exception as e:
#             print(f"[DEBUG-SESSION PROGRAM SWD EXCEPTION] {e}")
#             logger.error(f"SWD Programming failed: {str(e)}")
#             return False

#     def halt_target(self) -> bool:
#         """Send halt request to target core."""
#         print("[DEBUG-SESSION HALT] Sending halt request to target...")
#         if "USB" in self.interface_type:
#             print("[DEBUG-SESSION HALT] USB mode active, bypass.")
#             return True

#         if not self.target:
#             print("[DEBUG-SESSION HALT ERROR] Target is not connected.")
#             return False
#         try:
#             self.target.halt()
#             print("[DEBUG-SESSION HALT] Target halted successfully.")
#             return True
#         except Exception as e:
#             print(f"[DEBUG-SESSION HALT EXCEPTION] {e}")
#             logger.error(f"Failed to halt target core: {str(e)}")
#             return False

#     def reset_target(self, halt: bool = False) -> bool:
#         """Reset target core, optionally halting immediately upon reset."""
#         print(
#             f"[DEBUG-SESSION RESET] Resetting target (halt_on_reset={halt})...")
#         if "USB" in self.interface_type:
#             print("[DEBUG-SESSION RESET] USB mode active, bypass.")
#             return True

#         if not self.target:
#             print("[DEBUG-SESSION RESET ERROR] Target is not connected.")
#             return False
#         try:
#             if halt:
#                 self.target.reset_and_halt()
#                 print("[DEBUG-SESSION RESET] Target reset and halted.")
#             else:
#                 self.target.reset()
#                 print("[DEBUG-SESSION RESET] Target reset executed.")
#             return True
#         except Exception as e:
#             print(f"[DEBUG-SESSION RESET EXCEPTION] {e}")
#             logger.error(f"Failed to reset target: {str(e)}")
#             return False

#     def close(self) -> None:
#         print("\n[DEBUG-SESSION CLOSE] Closing session and releasing resources...")
#         if "USB" in self.interface_type:
#             self.is_usb_connected = False
#             print("[DEBUG-SESSION CLOSE] Direct USB session flags cleared.")
#             logger.info("Direct USB session closed successfully.")
#             return

#         if self.session:
#             try:
#                 print("[DEBUG-SESSION CLOSE] Closing active pyOCD session...")
#                 self.session.close()
#                 print("[DEBUG-SESSION CLOSE] pyOCD session closed successfully.")
#                 logger.info("SWD session closed successfully.")
#             except Exception as e:
#                 print(f"[DEBUG-SESSION CLOSE EXCEPTION] {e}")
#                 logger.debug(f"Error closing session: {str(e)}")
#             finally:
#                 self.session = None
#                 self.target = None
#                 print("[DEBUG-SESSION CLOSE] References cleaned up.")
#         else:
#             print("[DEBUG-SESSION CLOSE] No active session to close.")

#     def __enter__(self):
#         print("[DEBUG-SESSION CONTEXT] Entering SessionManager context manager...")
#         self.connect()
#         return self

#     def __exit__(self, exc_type, exc_val, exc_tb):
#         print(
#             f"[DEBUG-SESSION CONTEXT] Exiting context manager (Exception: {exc_type})...")
#         self.close()
"""
Low-level SWD/pyOCD and Direct USB session manager handling probe connections,
USB DFU discovery, stealth auto-detect strategies, core register inspection,
and unified memory read/write operations.
(Features Universal ARM Global Pack Auto-Downloader with Global Signal Bus and Cross-Validation Shields)
"""

import subprocess
import os
import tempfile
import glob
import re
import sys
import time
from typing import Optional, Dict, Any, List

from pyocd.core.helpers import ConnectHelper
from pyocd.core.session import Session
from pyocd.core.target import Target
from pyocd.flash.file_programmer import FileProgrammer
from pyocd.flash.eraser import FlashEraser
from pyocd.target.pack import pack_target

from src.common.logger import get_logger
from src.common.registers import (
    DHCSR_ADDR,
    DEMCR_ADDR,
    DHCSR_BITS,
    DEMCR_BITS,
    DBGMCU_IDCODE_ADDR,
    STM32_DEVID_MAP
)
from src.common.resources import EXE_DFU
from src.common.paths import get_path

# ایمپورت سیستم سیگنال سراسری
from src.common.pack_downloader import DownloadSignalBus

logger = get_logger("SessionManager")


class SessionManager:
    """
    Manages physical SWD debug probe sessions (via pyOCD) as well as
    Direct USB (DFU/CDC) hardware interfaces with ARM Cortex-M microcontrollers.
    """

    def __init__(
        self,
        target_type: Optional[str] = None,
        clock_freq: int = 1000000,
        connect_mode: str = "under-reset",
        interface_type: str = "B-Link (SWD)",
        unique_id: Optional[str] = None,
    ):
        self.target_type = target_type
        self.clock_freq = clock_freq
        self.connect_mode = connect_mode
        self.interface_type = interface_type
        self.unique_id = unique_id

        # SWD Session / Target objects
        self.session: Optional[Session] = None
        self.target: Optional[Target] = None

        # USB Direct Session state
        self.is_usb_connected: bool = False
        # SWD Session / Target objects
        self.session: Optional[Session] = None
        self.target: Optional[Target] = None

        # USB Direct Session state
        self.is_usb_connected: bool = False

        self.available_packs: List[str] = []
        user_packs_dir = os.path.join(os.path.expanduser("~"), ".blink_packs")
        if os.path.exists(user_packs_dir):
            loaded_packs = glob.glob(os.path.join(user_packs_dir, "*.pack"))
            self.available_packs.extend(loaded_packs)
            if loaded_packs:
                print(
                    f"[DEBUG-SESSION INIT] Loaded {len(loaded_packs)} cached CMSIS-Pack(s) from {user_packs_dir}")
        print(f"\n[DEBUG-SESSION INIT] SessionManager created.")
        print(f"  -> Interface Type: {self.interface_type}")
        print(f"  -> Target Type: {self.target_type}")
        print(f"  -> Clock Frequency: {self.clock_freq} Hz")
        print(f"  -> Connect Mode: {self.connect_mode}")
        print(
            f"  -> Target Probe UID: {self.unique_id or 'Auto-Detect (First Available)'}\n")

    def _stealth_auto_detect(self) -> Optional[str]:
        """
        Connects via generic 'cortex_m', reads DBGMCU_IDCODE, and resolves true MCU name.
        Targeted to a specific probe if unique_id is provided.
        """
        print(
            "\n[DEBUG-SESSION AUTO-DETECT] Launching Stealth Probe for Smart ST Detection...")
        try:
            options = {
                "connect_mode": "attach",
                "frequency": 1000000,
                "target_override": "cortex_m",  # Force generic blind connection
                "halt_on_connect": False,
            }
            # Inject unique_id for multi-probe routing
            session = ConnectHelper.session_with_chosen_probe(
                blocking=False, options=options, unique_id=self.unique_id
            )

            if not session:
                print("[DEBUG-SESSION AUTO-DETECT] No probe found matching UID.")
                return None

            session.open()
            target = session.board.target

            try:
                # Read ST specific DBGMCU register
                idcode = target.read32(DBGMCU_IDCODE_ADDR)
                dev_id = idcode & 0xFFF
                rev_id = (idcode >> 16) & 0xFFFF

                if dev_id in STM32_DEVID_MAP:
                    detected_mcu = STM32_DEVID_MAP[dev_id]
                    print(
                        f"[DEBUG-SESSION AUTO-DETECT] ✔ Found ST MCU: DEV_ID=0x{dev_id:03X}, REV=0x{rev_id:04X} -> {detected_mcu.upper()}")
                    return detected_mcu
                else:
                    print(
                        f"[DEBUG-SESSION AUTO-DETECT] ✖ Unknown DEV_ID 0x{dev_id:03X} at 0xE0042000.")
            except Exception as mem_exc:
                print(
                    f"[DEBUG-SESSION AUTO-DETECT] Memory read failed (Not ST or read-protected): {mem_exc}")
            finally:
                session.close()

        except Exception as e:
            print(f"[DEBUG-SESSION AUTO-DETECT EXCEPTION] {e}")

        return None

    # def _download_missing_pack(self, target_name: str, timeout_sec: int = 180) -> bool:
    #     """
    #     True Universal ARM Cortex-M Pack Fetcher:
    #     Resolves ANY Cortex-M microcontroller (ST, NXP, Microchip, Nordic, TI, Renesas, RP2040, etc.)
    #     by querying the ARM Open-CMSIS Registry and streaming the official .pack directly to disk.
    #     """
    #     import os
    #     import re
    #     import json
    #     import requests

    #     print(f"\n[DEBUG-SESSION] ===============================================")
    #     print(f"[DEBUG-SESSION] 🌍 UNIVERSAL ARM CMSIS-PACK RESOLVER")
    #     print(f"[DEBUG-SESSION] Target Hardware: {target_name.upper()}")
    #     print(f"[DEBUG-SESSION] ===============================================\n")

    #     from src.common.pack_downloader import DownloadSignalBus
    #     from PySide6.QtCore import QMetaObject, Qt, Q_RETURN_ARG, Q_ARG

    #     bus = DownloadSignalBus.instance()
    #     bus.download_preparing.emit(target_name.upper())

    #     if bus.dialog_instance:
    #         user_agreed = False
    #         try:
    #             user_agreed = QMetaObject.invokeMethod(
    #                 bus.dialog_instance,
    #                 "ask_permission",
    #                 Qt.ConnectionType.BlockingQueuedConnection,
    #                 Q_RETURN_ARG(bool),
    #                 Q_ARG(str, target_name.upper())
    #             )
    #         except Exception as e:
    #             logger.error(f"Dialog invocation error: {e}")
    #             user_agreed = True

    #         if not user_agreed:
    #             logger.warning(
    #                 f"User rejected pack download for {target_name.upper()}.")
    #             bus.download_finished.emit(False, "Cancelled by user.")
    #             return False

    #     bus.download_started.emit(target_name.upper())

    #     local_packs_dir = os.path.join(os.path.expanduser("~"), ".blink_packs")
    #     os.makedirs(local_packs_dir, exist_ok=True)

    #     clean_target = target_name.strip().lower()
    #     download_url = None
    #     pack_filename = None

    #     headers = {
    #         'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)',
    #         'Accept': '*/*'
    #     }

    #     # -------------------------------------------------------------
    #     # مرحله ۱: استعلام داینامیک ایندکس رسمی Open-CMSIS بدون تحریم
    #     # -------------------------------------------------------------
    #     cache_index_path = os.path.join(
    #         local_packs_dir, "cmsis_registry_cache.json")
    #     packs_data = None

    #     # بارگذاری از کش محلی در صورت معتبر بودن (کمتر از ۷ روز گذشته باشد)
    #     if os.path.exists(cache_index_path):
    #         try:
    #             with open(cache_index_path, "r", encoding="utf-8") as f:
    #                 packs_data = json.load(f)
    #         except Exception:
    #             packs_data = None

    #     # اگر در کش نبود، دانلود مخزن رسمی بدون فیلتر ARM CMSIS
    #     if not packs_data:
    #         logger.info(
    #             "Fetching global CMSIS-Pack metadata from ARM Open-Registry...")
    #         endpoints = [
    #             "https://raw.githubusercontent.com/Open-CMSIS-Pack/registry/main/packs.json",
    #             "https://cdn.jsdelivr.net/gh/Open-CMSIS-Pack/registry@main/packs.json"  # آینه سریع CDN
    #         ]
    #         for ep in endpoints:
    #             try:
    #                 resp = requests.get(ep, headers=headers, timeout=10)
    #                 if resp.status_code == 200:
    #                     packs_data = resp.json().get("packs", [])
    #                     with open(cache_index_path, "w", encoding="utf-8") as f:
    #                         json.dump(packs_data, f)
    #                     break
    #             except Exception as e:
    #                 logger.warning(f"Registry endpoint {ep} unavailable: {e}")

    #     # -------------------------------------------------------------
    #     # مرحله ۲: جستجوی عمیق تطبیقی نام میکرو در بین پکیج‌های ثبت شده
    #     # -------------------------------------------------------------
    #     if packs_data:
    #         # استخراج الگوهای قطعه: نام کامل، خانواده، یا پیشوند پلتفرم
    #         # مثلاً stm32f103c8 -> خانواده stm32f1 یا lpc1768 -> lpc1700
    #         for pack in packs_data:
    #             p_name = pack.get("name", "").lower()
    #             p_vendor = pack.get("vendor", "")
    #             base_url = pack.get("url", "").rstrip("/")
    #             version = pack.get("version", "")

    #             # ساخت کلید عمومی جستجو
    #             # قطعات STM32 / GD32 / APM32
    #             m_st = re.match(r'^([a-z]{2,3}32[a-z][0-9])', clean_target)
    #             target_root = m_st.group(1) if m_st else clean_target[:6]

    #             # انطباق نام دیوایس با نام رسمی پکیج سازنده
    #             matched = False
    #             if target_root in p_name:
    #                 matched = True
    #             elif clean_target.startswith("lpc") and clean_target[:5] in p_name:
    #                 matched = True
    #             elif clean_target.startswith("nrf") and clean_target[:5] in p_name:
    #                 matched = True
    #             elif clean_target.startswith("sam") and clean_target[:5] in p_name:
    #                 matched = True
    #             elif "rp2040" in clean_target and "rp2040" in p_name:
    #                 matched = True

    #             if matched and version:
    #                 pack_filename = f"{p_vendor}.{pack.get('name')}.{version}.pack"
    #                 download_url = f"{base_url}/{pack_filename}"
    #                 logger.info(
    #                     f"Target matched to dynamic package: {pack_filename}")
    #                 break

    #     # -------------------------------------------------------------
    #     # مرحله ۳: فال‌بک رسمی CDN مایکروسافت/آژور برای شرایط عدم دسترسی به گیت‌هاب
    #     # -------------------------------------------------------------
    #     if not download_url:
    #         logger.warning(
    #             "Dynamic lookup missed, applying deterministic vendor rules...")
    #         vendor_rules = [
    #             (r'^stm32f1', 'Keil', 'STM32F1xx_DFP', '2.4.1'),
    #             (r'^stm32f4', 'Keil', 'STM32F4xx_DFP', '2.17.1'),
    #             (r'^stm32g0', 'Keil', 'STM32G0xx_DFP', '1.5.0'),
    #             (r'^stm32h7', 'Keil', 'STM32H7xx_DFP', '2.8.0'),
    #             (r'^stm32l4', 'Keil', 'STM32L4xx_DFP', '2.6.1'),
    #             (r'^lpc17',   'Keil', 'LPC1700_DFP',   '2.7.1'),
    #             (r'^lpc11',   'Keil', 'LPC1100_DFP',   '1.4.0'),
    #             (r'^nrf52',   'NordicSemiconductor',
    #              'nRF_DeviceFamilyPack', '8.44.1'),
    #             (r'^samd21',  'Microchip', 'SAMD21_DFP', '3.6.144'),
    #             (r'^rp2040',  'RaspberryPi', 'RP2040_DFP', '1.0.0'),
    #         ]
    #         for regex_pat, v_name, p_core, ver in vendor_rules:
    #             if re.search(regex_pat, clean_target):
    #                 pack_filename = f"{v_name}.{p_core}.{ver}.pack"
    #                 download_url = f"https://keilpack.azureedge.net/pack/{pack_filename}"
    #                 break

    #     if not download_url or not pack_filename:
    #         err_msg = f"Could not determine online CMSIS-Pack for target '{target_name.upper()}'."
    #         logger.error(err_msg)
    #         bus.download_finished.emit(False, err_msg)
    #         return False

    #     dest_path = os.path.join(local_packs_dir, pack_filename)
    #     logger.info(f"Resolved -> {pack_filename}")
    #     logger.info(f"Downloading from: {download_url}")

    #     # -------------------------------------------------------------
    #     # مرحله ۴: استریم باینری، مدیریت ریدایرکت‌های Azure و گزارش درصد پیشرفت
    #     # -------------------------------------------------------------
    #     try:
    #         with requests.get(download_url, headers=headers, stream=True, allow_redirects=True, timeout=timeout_sec) as r:
    #             r.raise_for_status()
    #             total_size = int(r.headers.get('content-length', 0))
    #             downloaded = 0
    #             chunk_size = 1024 * 64

    #             with open(dest_path, 'wb') as f:
    #                 for chunk in r.iter_content(chunk_size=chunk_size):
    #                     if bus.cancel_requested:
    #                         raise InterruptedError("USER_CANCELLED")
    #                     if chunk:
    #                         f.write(chunk)
    #                         downloaded += len(chunk)
    #                         if total_size > 0:
    #                             pct = int((downloaded / total_size) * 100)
    #                             bus.download_progress.emit(
    #                                 min(pct, 100), f"Downloading {pack_filename}...")

    #         # اضافه کردن فایل به لیست کش فعال همین سشن
    #         if dest_path not in self.available_packs:
    #             self.available_packs.append(dest_path)

    #         msg = f"✔ Pack for {target_name.upper()} successfully retrieved: {pack_filename}"
    #         logger.info(msg)
    #         bus.download_finished.emit(True, msg)
    #         return True

    #     except InterruptedError:
    #         if os.path.exists(dest_path):
    #             os.remove(dest_path)
    #         bus.download_finished.emit(False, "Cancelled by user.")
    #         return False
    #     except Exception as e:
    #         if os.path.exists(dest_path):
    #             os.remove(dest_path)
    #         logger.error(f"Download stream error: {e}")
    #         bus.download_finished.emit(False, f"Download failed: {e}")
    #         return False

    def _download_missing_pack(self, target_name: str, timeout_sec: int = 180) -> bool:
        """
        True Universal ARM Cortex-M Pack Fetcher:
        Prioritizes Offline Assets before Online Downloads (User Cache -> Bundled Asset -> Live Azure/Keil).
        """
        import os
        import re
        import requests
        from src.common.paths import get_path

        print(f"\n[DEBUG-SESSION] ===============================================")
        print(f"[DEBUG-SESSION] 🌍 UNIVERSAL ARM CMSIS-PACK RESOLVER")
        print(f"[DEBUG-SESSION] Resolving Target: {target_name.upper()}")
        print(f"[DEBUG-SESSION] ===============================================\n")

        from src.common.pack_downloader import DownloadSignalBus
        from PySide6.QtCore import QMetaObject, Qt, Q_RETURN_ARG, Q_ARG

        bus = DownloadSignalBus.instance()
        bus.download_preparing.emit(target_name.upper())

        if bus.dialog_instance:
            user_agreed = False
            try:
                user_agreed = QMetaObject.invokeMethod(
                    bus.dialog_instance,
                    "ask_permission",
                    Qt.ConnectionType.BlockingQueuedConnection,
                    Q_RETURN_ARG(bool),
                    Q_ARG(str, target_name.upper())
                )
            except Exception as e:
                logger.error(f"Dialog invocation error: {e}")
                user_agreed = True

            if not user_agreed:
                logger.warning(
                    f"User cancelled download for {target_name.upper()}.")
                bus.download_finished.emit(False, "Cancelled by user.")
                return False

        bus.download_started.emit(target_name.upper())

        local_packs_dir = os.path.join(os.path.expanduser("~"), ".blink_packs")
        os.makedirs(local_packs_dir, exist_ok=True)

        clean_target = target_name.strip().lower()
        download_url = None
        pack_filename = None

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*'
        }

        # -------------------------------------------------------------
        # مرحله ۱: تأمین قطعی محتوای ایندکس (Cache -> Bundled Asset -> Online)
        # -------------------------------------------------------------
        cache_index_path = os.path.join(local_packs_dir, "master_index.idx")
        index_content = ""

        # ۱.۱: اولویت اول -> بررسی کش سیستم کاربر
        if os.path.exists(cache_index_path):
            try:
                with open(cache_index_path, "r", encoding="utf-8", errors="ignore") as f:
                    index_content = f.read()
                if len(index_content) > 1000:
                    logger.info("Master index loaded from local user cache.")
            except Exception:
                index_content = ""

        # ۱.۲: اولویت دوم -> لایه آفلاین داخلی پروژه (assets/master_index.idx)
        if not index_content or len(index_content) <= 1000:
            bundled_idx = get_path("assets/master_index.idx")
            if os.path.exists(bundled_idx):
                try:
                    with open(bundled_idx, "r", encoding="utf-8", errors="ignore") as f:
                        index_content = f.read()
                    if len(index_content) > 1000:
                        logger.info(
                            "Loaded master index from bundled assets/master_index.idx.")
                        # انتقال به کش کاربر تا دفعات بعد مستقیم لود شود
                        try:
                            with open(cache_index_path, "w", encoding="utf-8", errors="ignore") as out_f:
                                out_f.write(index_content)
                        except Exception:
                            pass
                except Exception as ex:
                    logger.error(f"Failed to read bundled index: {ex}")

        # ۱.۳: اولویت سوم -> دانلود آنلاین فقط در صورتی که فایل آفلاین پیدا نشود
        if not index_content or len(index_content) <= 1000:
            logger.info(
                "No offline index available. Fetching global index from Azure/Keil...")
            index_mirrors = [
                "https://sadevicepacksprodus.blob.core.windows.net/idxfile/index.idx",
                "https://www.keil.com/pack/index.idx"
            ]
            for mirror in index_mirrors:
                try:
                    r = requests.get(mirror, headers=headers, timeout=10)
                    if r.status_code == 200 and len(r.text) > 1000:
                        index_content = r.text
                        try:
                            with open(cache_index_path, "w", encoding="utf-8", errors="ignore") as f:
                                f.write(index_content)
                        except Exception:
                            pass
                        logger.info(
                            f"Master index retrieved online and cached from: {mirror}")
                        break
                except Exception as ex:
                    logger.warning(f"Index mirror {mirror} unavailable: {ex}")

        # -------------------------------------------------------------
        # مرحله ۲: جستجوی داینامیک در شاخص جهانی
        # -------------------------------------------------------------
        if index_content:
            logger.info(
                f"Scanning index for target: {clean_target.upper()}...")
            m_family = re.match(
                r'^([a-z]{2,4}[0-9]{1,3}[a-z]?[0-9]?)', clean_target)
            search_key = m_family.group(1) if m_family else clean_target[:6]

            for line in index_content.splitlines():
                line_lower = line.lower()
                if search_key in line_lower and "dfp" in line_lower:
                    url_m = re.search(r'url="([^"]+)"', line, re.IGNORECASE)
                    name_m = re.search(r'name="([^"]+)"', line, re.IGNORECASE)
                    ver_m = re.search(
                        r'version="([^"]+)"', line, re.IGNORECASE)

                    if url_m and name_m and ver_m:
                        base_url = url_m.group(1).rstrip('/')
                        pdsc_name = name_m.group(1)
                        version = ver_m.group(1)

                        raw_name = pdsc_name[:-
                                             5] if pdsc_name.endswith(".pdsc") else pdsc_name
                        pack_filename = f"{raw_name}.{version}.pack"
                        download_url = f"{base_url}/{pack_filename}"
                        logger.info(
                            f"✔ Target dynamically resolved via Index: {pack_filename}")
                        break

        # -------------------------------------------------------------
        # مرحله ۳: نگاشت قطعی خانواده‌های اصلی برای خطاهای استثنایی
        # -------------------------------------------------------------
        if not download_url:
            logger.warning(
                "Stage 2 index lookup missed; falling back to static CDN rules...")
            offline_patterns = [
                (r'^stm32f1', 'Keil.STM32F1xx_DFP.2.4.1.pack',
                 'https://keilpack.azureedge.net/pack/Keil.STM32F1xx_DFP.2.4.1.pack'),
                (r'^stm32f4', 'Keil.STM32F4xx_DFP.2.17.1.pack',
                 'https://keilpack.azureedge.net/pack/Keil.STM32F4xx_DFP.2.17.1.pack'),
                (r'^stm32g0', 'Keil.STM32G0xx_DFP.1.5.0.pack',
                 'https://keilpack.azureedge.net/pack/Keil.STM32G0xx_DFP.1.5.0.pack'),
                (r'^stm32h7', 'Keil.STM32H7xx_DFP.2.8.0.pack',
                 'https://keilpack.azureedge.net/pack/Keil.STM32H7xx_DFP.2.8.0.pack'),
                (r'^stm32l4', 'Keil.STM32L4xx_DFP.2.6.1.pack',
                 'https://keilpack.azureedge.net/pack/Keil.STM32L4xx_DFP.2.6.1.pack'),
                (r'^lpc17',   'Keil.LPC1700_DFP.2.7.1.pack',
                 'https://keilpack.azureedge.net/pack/Keil.LPC1700_DFP.2.7.1.pack'),
                (r'^nrf52',   'NordicSemiconductor.nRF_DeviceFamilyPack.8.44.1.pack',
                 'https://keilpack.azureedge.net/pack/NordicSemiconductor.nRF_DeviceFamilyPack.8.44.1.pack'),
                (r'^samd21',  'Microchip.SAMD21_DFP.3.6.144.pack',
                 'https://keilpack.azureedge.net/pack/Microchip.SAMD21_DFP.3.6.144.pack'),
                (r'^rp2040',  'RaspberryPi.RP2040_DFP.1.0.0.pack',
                 'https://keilpack.azureedge.net/pack/RaspberryPi.RP2040_DFP.1.0.0.pack'),
            ]
            for pat, fname, u in offline_patterns:
                if re.search(pat, clean_target):
                    pack_filename = fname
                    download_url = u
                    break

        if not download_url or not pack_filename:
            err_msg = f"Could not determine online CMSIS-Pack for target '{target_name.upper()}'."
            logger.error(err_msg)
            bus.download_finished.emit(False, err_msg)
            return False

        dest_path = os.path.join(local_packs_dir, pack_filename)
        logger.info(f"Downloading pack from: {download_url}")

        # -------------------------------------------------------------
        # مرحله ۴: استریم باینری و تزریق به نشست فعال
        # -------------------------------------------------------------
        try:
            with requests.get(download_url, headers=headers, stream=True, allow_redirects=True, timeout=timeout_sec) as r:
                r.raise_for_status()
                total_size = int(r.headers.get('content-length', 0))
                downloaded = 0
                chunk_size = 1024 * 64

                with open(dest_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=chunk_size):
                        if bus.cancel_requested:
                            raise InterruptedError("USER_CANCELLED")
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                pct = int((downloaded / total_size) * 100)
                                bus.download_progress.emit(
                                    min(pct, 100), f"Downloading {pack_filename}...")

            if dest_path not in self.available_packs:
                self.available_packs.append(dest_path)

            msg = f"✔ Pack for {target_name.upper()} successfully retrieved: {pack_filename}"
            logger.info(msg)
            bus.download_finished.emit(True, msg)
            return True

        except InterruptedError:
            if os.path.exists(dest_path):
                os.remove(dest_path)
            bus.download_finished.emit(False, "Cancelled by user.")
            return False
        except Exception as e:
            if os.path.exists(dest_path):
                os.remove(dest_path)
            logger.error(f"Download stream error: {e}")
            bus.download_finished.emit(False, f"Download failed: {e}")
            return False

    def _fallback_cli_install(self, target_name: str, bus) -> bool:
        """اجرای دستور سیستمی به صورت کنترل‌شده و ایمن"""
        import subprocess
        # توجه: در خط فرمان pyOCD، برای جستجوی قطعه سوییچ find و برای نصب قطعه باید دقیقا نام میکرو به صورت حرف بزرگ پاس داده شود
        cmd = [sys.executable, "-m", "pyocd",
               "pack", "install", target_name.upper()]

        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        try:
            res = subprocess.run(cmd, capture_output=True,
                                 text=True, timeout=120, creationflags=flags)
            if res.returncode == 0:
                bus.download_finished.emit(
                    True, "Pack installed via pyOCD engine.")
                return True
        except Exception as e:
            logger.error(f"Fallback CLI pack installer failed: {e}")

        bus.download_finished.emit(
            False, f"Target '{target_name.upper()}' pack could not be located.")
        return False

    @staticmethod
    def list_probes() -> List[Any]:
        print("[DEBUG-SESSION list_probes] Scanning for connected debug probes...")
        probes = ConnectHelper.get_all_connected_probes()
        print(
            f"[DEBUG-SESSION list_probes] Found {len(probes) if probes else 0} probe(s).")
        if not probes:
            logger.warning("No B-Link debug probes found via USB.")
        return probes

    def probe_usb_device(self) -> Dict[str, Any]:
        print("\n[DEBUG-SESSION USB_PROBE] Starting USB DFU device discovery...")
        logger.info(
            "Probing for Direct USB (DFU) target devices using dfu-util...")
        info = {
            "success": False,
            "probe_serial": "N/A",
            "part_number": "STM32_DFU_DEVICE",
            "dpidr": "N/A",
            "core_type": "CORTEX-M (USB)",
            "rdp_status": "UNKNOWN",
            "error": "",
        }

        try:
            print(f"[DEBUG-SESSION USB_PROBE] Running command: {EXE_DFU} -l")
            result = subprocess.run(
                [EXE_DFU, "-l"], capture_output=True, text=True, check=False)
            output = result.stdout.lower()

            if "found dfu" in output and "0483:df11" in output:
                info["success"] = True
                info["dpidr"] = "0483:DF11 (VID:PID)"
                info["probe_serial"] = "USB_DFU_Link"
                info["rdp_status"] = "LEVEL 0 (ASSUMED)"
                logger.info(
                    "✔ STM32 DFU Device detected successfully via dfu-util.")
            else:
                info["error"] = "No STM32 DFU device found. Make sure BOOT0=1 and device is plugged in."
                logger.warning("✖ No Direct USB (DFU) device detected.")

        except FileNotFoundError:
            err_msg = f"dfu-util not found at {EXE_DFU}! Please ensure it is bundled correctly."
            info["error"] = err_msg
            logger.error(err_msg)
        except Exception as e:
            info["error"] = str(e)
            logger.error(f"DFU probe exception: {str(e)}")

        return info

    def probe_target_info(self, clock_freq: int = 1000000, target_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Lightweight attach session.
        Validates Target Type against physical hardware to prevent manual override crashes.
        """
        current_target = target_type or self.target_type or "auto"
        print(
            f"\n[DEBUG-SESSION PROBE_INFO] Starting probe_target_info with clock={clock_freq}Hz, Target='{current_target}'")

        if "USB" in self.interface_type:
            print("[DEBUG-SESSION PROBE_INFO] Routing to USB probe handler.")
            return self.probe_usb_device()

        info = {
            "success": False,
            "probe_serial": "Unknown",
            "part_number": "Unknown",
            "dpidr": "N/A",
            "core_type": "Unknown",
            "error": "",
        }

        resolved_target = "cortex_m"
        is_auto_mode = current_target.lower(
        ) in ["auto", "none", "", "cortex_m", "stmicroelectronics"]

        detected_st = self._stealth_auto_detect()

        if not is_auto_mode:
            if detected_st and not any(prefix in current_target.lower() for prefix in ["stm32", "gd32", "apm32", "at32", "cks32", "ch32"]):
                err_msg = f"Hardware Mismatch! You selected '{current_target.upper()}', but physical board is an ST-compatible MCU ({detected_st.upper()})."
                print(f"[DEBUG-SESSION PROBE_INFO] ✖ {err_msg}")
                logger.error(err_msg)
                info["error"] = err_msg
                return info
            resolved_target = current_target
        else:
            resolved_target = detected_st if detected_st else "cortex_m"

        try:
            options = {
                "connect_mode": "attach",
                "frequency": clock_freq,
                "target_override": resolved_target,
                "halt_on_connect": False,
            }
            if self.available_packs:
                options["pack"] = self.available_packs

            print(f"[DEBUG-SESSION PROBE_INFO] Connecting options: {options}")

            session = ConnectHelper.session_with_chosen_probe(
                blocking=False, options=options, unique_id=self.unique_id
            )

            if session is None:
                raise Exception("No B-Link/SWD probe detected on USB.")

            print("[DEBUG-SESSION PROBE_INFO] Probe found. Opening session...")
            session.open()

            try:
                info["probe_serial"] = str(session.probe.unique_id)
            except Exception:
                info["probe_serial"] = "Detected"

            target = session.board.target
            dpidr_val = 0
            try:
                dpidr_val = session.probe.read_dp(0x0)
            except:
                pass

            info["dpidr"] = f"0x{dpidr_val:08X}" if dpidr_val else "Detected"

            # استخراج هسته
            try:
                code = target.cores[0].core_type
                try:
                    from pyocd.coresight.core_ids import CORE_TYPE_NAME
                    info["core_type"] = str(
                        CORE_TYPE_NAME.get(code, code)).upper()
                except ImportError:
                    info["core_type"] = str(code).upper()
            except Exception:
                info["core_type"] = "CORTEX-M"

            # 🌟 جای‌گذاری نام صحیح به دست‌آمده از Shield
            if is_auto_mode and detected_st:
                info["part_number"] = detected_st.upper()
            elif is_auto_mode:
                info["part_number"] = "CORTEX-M (Generic)"
            else:
                info["part_number"] = current_target.upper()

            info["success"] = True
            print(
                f"[DEBUG-SESSION PROBE_INFO] Success! Target Part: {info['part_number']}, Core: {info['core_type']}")
            session.close()

        # except Exception as e:
        #     print(f"[DEBUG-SESSION PROBE_INFO EXCEPTION] Attempt failed: {e}")
        #     info["error"] = str(e)
        except Exception as e:
            err_str = str(e)

            print(
                f"[DEBUG-SESSION PROBE_INFO EXCEPTION] Attempt failed: {err_str}"
            )

            match = re.search(
                r"target type (\w+) not recognized",
                err_str,
                re.IGNORECASE
            )

            if match:
                missing_target = match.group(1)

                print(
                    f"[DEBUG-SESSION PROBE_INFO] "
                    f"Target '{missing_target}' is not installed."
                )

                print(
                    f"[DEBUG-SESSION PROBE_INFO] "
                    f"Attempting automatic CMSIS-Pack download..."
                )

                if self._download_missing_pack(missing_target):
                    print(
                        "[DEBUG-SESSION PROBE_INFO] "
                        "Pack download completed. Retrying target connection..."
                    )
                    if self.available_packs:
                        options["pack"] = list(self.available_packs)

                    try:
                        session = ConnectHelper.session_with_chosen_probe(
                            blocking=False,
                            options=options,
                            unique_id=self.unique_id
                        )

                        if session is None:
                            raise Exception(
                                "No B-Link/SWD probe detected on USB."
                            )

                        print(
                            "[DEBUG-SESSION PROBE_INFO] "
                            "Retry: Opening session..."
                        )

                        session.open()

                        self.session = session

                        info["probe_serial"] = str(
                            session.probe.unique_id
                        )

                        target = session.board.target

                        dpidr_val = 0

                        try:
                            dpidr_val = session.probe.read_dp(0x0)
                        except Exception:
                            pass

                        info["dpidr"] = (
                            f"0x{dpidr_val:08X}"
                            if dpidr_val
                            else "Detected"
                        )

                        try:
                            code = target.cores[0].core_type

                            try:
                                from pyocd.coresight.core_ids import CORE_TYPE_NAME

                                info["core_type"] = str(
                                    CORE_TYPE_NAME.get(code, code)
                                ).upper()

                            except ImportError:
                                info["core_type"] = str(code).upper()

                        except Exception:
                            info["core_type"] = "CORTEX-M"

                        info["part_number"] = (
                            detected_st.upper()
                            if detected_st
                            else missing_target.upper()
                        )

                        info["success"] = True

                        print(
                            "[DEBUG-SESSION PROBE_INFO] "
                            f"Retry successful! Target: {info['part_number']}"
                        )

                        session.close()

                        return info

                    except Exception as retry_exc:
                        print(
                            "[DEBUG-SESSION PROBE_INFO] "
                            f"Retry after pack download failed: {retry_exc}"
                        )

                        info["error"] = str(retry_exc)

                else:
                    print(
                        "[DEBUG-SESSION PROBE_INFO] "
                        "Automatic CMSIS-Pack download failed."
                    )

            info["error"] = err_str

        print(f"[DEBUG-SESSION PROBE_INFO] Final result: {info}\n")
        return info

    def _open_session(self, freq: int, mode: str, target_name: Optional[str], _auto_downloaded: bool = False) -> bool:
        print(
            f"\n[DEBUG-SESSION _open_session] Attempting -> Target: '{target_name}' | Clock: {freq}Hz | Mode: '{mode}'")
        options: Dict[str, Any] = {
            "connect_mode": mode,
            "frequency": freq,
            "target_override": target_name,
            "reset_type": "hw" if mode == "under-reset" else "sw",
            "resume_on_disconnect": False,
        }

        if self.available_packs:
            options["pack"] = self.available_packs

        try:
            logger.info(
                f"Attempting SWD connection -> Target: '{target_name}' | Clock: {freq // 1000} kHz | Mode: '{mode}'...")

            # Explicitly route connection to the targeted probe ID
            self.session = ConnectHelper.session_with_chosen_probe(
                options=options, unique_id=self.unique_id
            )

            if self.session is None:
                print(
                    "[DEBUG-SESSION _open_session] session_with_chosen_probe returned None. Probe unavailable.")
                return False

            print("[DEBUG-SESSION _open_session] Opening session...")
            self.session.open()
            self.target = self.session.target
            print("[DEBUG-SESSION _open_session] SWD session successfully established!")
            logger.info("SWD session established successfully.")
            return True

        except Exception as e:
            err_str = str(e)
            match = re.search(
                r"target type (\w+) not recognized", err_str, re.IGNORECASE)
            if match and not _auto_downloaded:
                missing_mcu = match.group(1)
                if self._download_missing_pack(missing_mcu):
                    print(
                        "[DEBUG-SESSION _open_session] Download complete. Retrying connection...")
                    return self._open_session(freq, mode, target_name, _auto_downloaded=True)

            print(f"[DEBUG-SESSION _open_session EXCEPTION] Failed: {err_str}")
            logger.error(f"Connection attempt failed: {err_str}")
            self.close()
            return False

    def connect(self) -> bool:
        """Connect to target microcontroller smartly resolving its true identity and preventing mismatch hardware damage."""
        print(
            f"\n[DEBUG-SESSION CONNECT] Starting connect() procedure. Interface: {self.interface_type}")
        if "USB" in self.interface_type:
            print(
                "[DEBUG-SESSION CONNECT] USB mode active. Bypassing SWD connection sequence.")
            logger.info("Establishing direct USB session...")
            self.is_usb_connected = True
            return True

        # =========================================================================
        # 🌟 مرحله 0: راستی‌آزمایی متقاطع (Cross-Validation) قبل از اجرای الگوریتم‌ها
        # =========================================================================
        target_to_use = (self.target_type or "auto").lower()
        is_auto_mode = target_to_use in [
            "auto", "none", "", "cortex_m", "stmicroelectronics"]

        detected_st = self._stealth_auto_detect()

        if not is_auto_mode:
            # بررسی تضاد خطرناک: آیا کاربر میکروی غیر ST انتخاب کرده اما قطعه در واقعیت ST است؟
            if detected_st and not any(prefix in target_to_use for prefix in ["stm32", "gd32", "apm32", "at32", "cks32", "ch32"]):
                err_msg = f"CRITICAL HARDWARE MISMATCH: You manually selected '{target_to_use.upper()}', but the physical hardware is an ST-compatible MCU ({detected_st.upper()}). Connection aborted for hardware safety."
                print(f"[DEBUG-SESSION CONNECT] ✖ {err_msg}")
                logger.critical(err_msg)
                # پرتاب خطا برای متوقف کردن جریان Workers
                raise RuntimeError(err_msg)
        else:
            target_to_use = detected_st if detected_st else "cortex_m"

        self.target_type = target_to_use

        print(
            f"[DEBUG-SESSION CONNECT] Final Resolved Target: {self.target_type}")

        # Level 1: Primary attempt
        if self._open_session(self.clock_freq, self.connect_mode, self.target_type):
            return True

        # Level 2: Generic Cortex-M profile fallback
        if self.target_type != "cortex_m":
            print(
                "[DEBUG-SESSION CONNECT] Level 2 attempt -> Retrying with generic 'cortex_m' profile...")
            logger.warning(
                "Retrying connection with generic 'cortex_m' profile...")
            if self._open_session(self.clock_freq, self.connect_mode, "cortex_m"):
                self.target_type = "cortex_m"
                return True

        # Level 3: Emergency diagnostic fallback (50kHz, attach mode)
        print("[DEBUG-SESSION CONNECT] Level 3 attempt -> Diagnostics Fallback: 50 kHz clock & 'attach' mode...")
        logger.warning(
            "SWD connection error. Switching to Diagnostics Fallback: 50 kHz clock & 'attach' mode...")
        fallback_target = "cortex_m" if self.target_type == "cortex_m" else self.target_type

        if self._open_session(50000, "attach", fallback_target):
            self.clock_freq = 50000
            self.connect_mode = "attach"
            self.target_type = fallback_target
            print("[DEBUG-SESSION CONNECT] Diagnostics Fallback successful!")
            return True

        print(
            "[DEBUG-SESSION CONNECT CRITICAL] All SWD connection strategies failed completely.")
        logger.critical(
            "All SWD connection strategies failed. Verify physical wiring.")
        return False

    def check_swd_sanity(self) -> Optional[int]:
        print("\n[DEBUG-SESSION SANITY] Checking SWD physical bus integrity...")
        if "USB" in self.interface_type:
            print("[DEBUG-SESSION SANITY] USB mode active, skipping SWD check.")
            logger.info("SWD Sanity bypassed (Direct USB mode active).")
            return 0x00485740

        if not self.session or not self.target:
            print(
                "[DEBUG-SESSION SANITY ERROR] Session or target is not initialized. Connect first!")
            logger.error("Session is not open. Call connect() first.")
            return None

        try:
            dpidr = self.session.probe.read_dp(0x0)
            expected_ids = [0x1BA01477, 0x2BA01477]

            print(f"[DEBUG-SESSION SANITY] Read DPIDR register: 0x{dpidr:08X}")
            logger.info(f"Read DP IDCODE: 0x{dpidr:08X}")
            if dpidr in expected_ids:
                print("[DEBUG-SESSION SANITY] Pass! Valid DPIDR match found.")
                logger.info("SWD Sanity Check PASSED (Valid DPIDR detected).")
            else:
                print(
                    f"[DEBUG-SESSION SANITY WARNING] Unexpected DP IDCODE: 0x{dpidr:08X}")
                logger.warning(f"Unexpected DP IDCODE detected: 0x{dpidr:08X}")
            return dpidr

        except Exception as e:
            print(
                f"[DEBUG-SESSION SANITY EXCEPTION] Failed to read DP IDCODE: {e}")
            logger.error(f"Failed to read DP IDCODE: {str(e)}")
            return None

    def inspect_dhcsr(self) -> Optional[Dict[str, bool]]:
        """Read and decode DHCSR (Debug Halting Control and Status Register)."""
        print("\n[DEBUG-SESSION DHCSR] Inspecting DHCSR register...")
        if "USB" in self.interface_type:
            print("[DEBUG-SESSION DHCSR] USB mode active. Returning mock DHCSR flags.")
            return {"S_HALT": True, "S_SLEEP": False, "S_LOCKUP": False, "C_DEBUGEN": True}

        if not self.target:
            print("[DEBUG-SESSION DHCSR ERROR] Target is not connected.")
            return None

        try:
            raw_val = self.target.read32(DHCSR_ADDR)
            print(
                f"[DEBUG-SESSION DHCSR] Raw DHCSR value at 0x{DHCSR_ADDR:08X}: 0x{raw_val:08X}")
            decoded_flags = {}
            for bit_pos, (label, _desc) in DHCSR_BITS.items():
                is_set = bool((raw_val >> bit_pos) & 1)
                decoded_flags[label] = is_set

            print(f"[DEBUG-SESSION DHCSR] Decoded flags: {decoded_flags}")
            if decoded_flags.get("S_LOCKUP"):
                print("[DEBUG-SESSION DHCSR CRITICAL] Core is in S_LOCKUP state!")
                logger.critical(
                    "HARDWARE ALERT: Target core is in S_LOCKUP state!")
            return decoded_flags

        except Exception as e:
            print(f"[DEBUG-SESSION DHCSR EXCEPTION] {e}")
            logger.error(f"Failed to inspect DHCSR register: {str(e)}")
            return None

    def inspect_demcr(self) -> Optional[Dict[str, bool]]:
        """Read and decode DEMCR (Debug Exception and Monitor Control Register)."""
        print("\n[DEBUG-SESSION DEMCR] Inspecting DEMCR register...")
        if "USB" in self.interface_type:
            print("[DEBUG-SESSION DEMCR] USB mode active. Returning mock DEMCR flags.")
            return {"TRCENA": True, "VC_CORERESET": True, "VC_HARDERR": False}

        if not self.target:
            print("[DEBUG-SESSION DEMCR ERROR] Target is not connected.")
            return None

        try:
            raw_val = self.target.read32(DEMCR_ADDR)
            print(
                f"[DEBUG-SESSION DEMCR] Raw DEMCR value at 0x{DEMCR_ADDR:08X}: 0x{raw_val:08X}")
            decoded_flags = {}
            for bit_pos, (label, _desc) in DEMCR_BITS.items():
                is_set = bool((raw_val >> bit_pos) & 1)
                decoded_flags[label] = is_set
            print(f"[DEBUG-SESSION DEMCR] Decoded flags: {decoded_flags}")
            return decoded_flags

        except Exception as e:
            print(f"[DEBUG-SESSION DEMCR EXCEPTION] {e}")
            logger.error(f"Failed to inspect DEMCR register: {str(e)}")
            return None

    def read_memory_block8(self, addr: int, count: int) -> List[int]:
        """Read raw bytes from physical hardware via USB DFU or SWD."""
        print(
            f"\n[DEBUG-SESSION READ8] Reading 8-bit memory block -> Addr: 0x{addr:08X}, Count: {count}")
        if "USB" in self.interface_type:
            logger.info(
                f"Executing Direct USB (DFU) Read at 0x{addr:08X} ({count} bytes)...")
            temp_path = os.path.join(
                tempfile.gettempdir(), "dfu_read_dump.bin")

            try:
                cmd = [
                    EXE_DFU, "-a", "0", "-s", f"0x{addr:08X}:{count}", "-U", temp_path
                ]
                print(
                    f"[DEBUG-SESSION READ8 USB] Executing command: {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, text=True)
                print(
                    f"[DEBUG-SESSION READ8 USB] Return code: {result.returncode}")

                if result.returncode == 0 and os.path.exists(temp_path):
                    with open(temp_path, "rb") as f:
                        raw_bytes = list(f.read())
                    os.remove(temp_path)
                    print(
                        f"[DEBUG-SESSION READ8 USB] Successfully read {len(raw_bytes)} bytes.")
                    logger.info("✔ DFU Memory Read successful.")
                    return raw_bytes
                else:
                    print(
                        f"[DEBUG-SESSION READ8 USB ERROR] Stderr: {result.stderr}")
                    logger.error(f"DFU Hardware Read Error: {result.stderr}")
                    return []

            except Exception as exc:
                print(f"[DEBUG-SESSION READ8 USB EXCEPTION] {exc}")
                logger.error(f"DFU Subprocess Error: {str(exc)}")
                return []

        # DAPLink / SWD Mode
        if self.target:
            try:
                print(
                    "[DEBUG-SESSION READ8 SWD] Reading memory block via SWD target object...")
                data = self.target.read_memory_block8(addr, count)
                print(
                    f"[DEBUG-SESSION READ8 SWD] Read {len(data) if data else 0} bytes successfully.")
                return data
            except Exception as e:
                print(f"[DEBUG-SESSION READ8 SWD EXCEPTION] {e}")
                logger.error(
                    f"SWD Memory read failed at address 0x{addr:08X}: {str(e)}")
                return []
        print("[DEBUG-SESSION READ8 ERROR] No active target session found.")
        return []

    def read_memory_32(self, addr: int, count: int = 1) -> Optional[List[int]]:
        """Read 32-bit word(s) from target memory."""
        print(
            f"\n[DEBUG-SESSION READ32] Reading 32-bit words -> Addr: 0x{addr:08X}, Count: {count}")
        if "USB" in self.interface_type:
            byte_count = count * 4
            raw_bytes = self.read_memory_block8(addr, byte_count)
            if not raw_bytes or len(raw_bytes) < byte_count:
                print(
                    "[DEBUG-SESSION READ32 USB] Insufficient bytes returned from memory read block.")
                return None

            words = []
            for i in range(0, len(raw_bytes), 4):
                chunk = raw_bytes[i:i+4]
                if len(chunk) == 4:
                    word = chunk[0] | (chunk[1] << 8) | (
                        chunk[2] << 16) | (chunk[3] << 24)
                    words.append(word)
            print(
                f"[DEBUG-SESSION READ32 USB] Reconstructed {len(words)} 32-bit words.")
            return words

        # DAPLink SWD Mode
        if not self.target:
            print("[DEBUG-SESSION READ32 ERROR] SWD target not initialized.")
            return None
        try:
            print("[DEBUG-SESSION READ32 SWD] Calling target.read_memory_block32()...")
            res = self.target.read_memory_block32(addr, count)
            print(
                f"[DEBUG-SESSION READ32 SWD] Read {len(res) if res else 0} words successfully.")
            return res
        except Exception as e:
            print(f"[DEBUG-SESSION READ32 SWD EXCEPTION] {e}")
            logger.error(
                f"Memory read failed at address 0x{addr:08X}: {str(e)}")
            return None

    def write_memory_32(self, addr: int, val: int) -> bool:
        """Write a 32-bit word to target memory address."""
        print(
            f"\n[DEBUG-SESSION WRITE32] Writing 32-bit word -> Addr: 0x{addr:08X}, Value: 0x{val:08X}")
        if "USB" in self.interface_type:
            print(
                "[DEBUG-SESSION WRITE32 USB] Direct USB memory write simulated/passed.")
            logger.info(
                f"Direct USB memory write at 0x{addr:08X} = 0x{val:08X}")
            return True

        if not self.target:
            print("[DEBUG-SESSION WRITE32 ERROR] Target session not open.")
            return False
        try:
            self.target.write32(addr, val)
            print("[DEBUG-SESSION WRITE32 SWD] Write operation completed successfully.")
            return True
        except Exception as e:
            print(f"[DEBUG-SESSION WRITE32 SWD EXCEPTION] {e}")
            logger.error(
                f"Memory write failed at address 0x{addr:08X}: {str(e)}")
            return False

    def erase_chip(self) -> bool:
        """Executes Full Chip Erase over active interface (SWD or DFU)."""
        print("\n[DEBUG-SESSION ERASE] Executing Full Chip Erase...")
        if "USB" in self.interface_type:
            logger.info("Executing Mass Erase via Direct USB DFU...")
            try:
                cmd = [EXE_DFU, "-a", "0", "-s",
                       "0x08000000:mass-erase:force", "-e"]
                print(
                    f"[DEBUG-SESSION ERASE USB] Running command: {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, text=True)
                print(
                    f"[DEBUG-SESSION ERASE USB] Return code: {result.returncode}, Stdout: {result.stdout.strip()}")

                if result.returncode == 0 or "erasing" in result.stdout.lower():
                    print("[DEBUG-SESSION ERASE USB] Full chip erase successful.")
                    logger.info("✔ Full Chip Erase completed via USB DFU.")
                    return True
                else:
                    print(
                        "[DEBUG-SESSION ERASE USB] Primary erase flag failed. Trying fallback command...")
                    cmd_alt = [EXE_DFU, "-a", "0", "-s", "0x08000000", "-e"]
                    res_alt = subprocess.run(
                        cmd_alt, capture_output=True, text=True)
                    print(
                        f"[DEBUG-SESSION ERASE USB FALLBACK] Return code: {res_alt.returncode}")
                    if res_alt.returncode == 0:
                        print(
                            "[DEBUG-SESSION ERASE USB FALLBACK] Fallback erase successful.")
                        logger.info(
                            "✔ Full Chip Erase completed via USB DFU (Fallback mode).")
                        return True
                    print(
                        f"[DEBUG-SESSION ERASE USB ERROR] Erase failed. Stderr: {result.stderr or res_alt.stderr}")
                    logger.error(
                        f"DFU Erase Error: {result.stderr or res_alt.stderr}")
                    return False
            except Exception as e:
                print(f"[DEBUG-SESSION ERASE USB EXCEPTION] {e}")
                logger.error(f"DFU Mass Erase exception: {str(e)}")
                return False

        # SWD Mode via pyOCD
        if not self.session or not self.target:
            print(
                "[DEBUG-SESSION ERASE SWD] Session not active. Attempting to connect...")
            if not self.connect():
                return False
        try:
            # 🛡️ سپر امنیتی ضد تایم‌اوت
            print(
                "[DEBUG-SESSION ERASE SWD] Engaging Anti-Timeout Shield (Halt & PRIMASK=1)...")
            try:
                if self.target.get_state() != Target.State.HALTED:
                    self.target.halt()
                self.target.write_core_register('primask', 1)
            except Exception as e:
                print(
                    f"[DEBUG-SESSION ERASE SWD] Warning during pre-erase halt: {e}")

            print(
                "[DEBUG-SESSION ERASE SWD] Triggering FlashEraser with CHIP mode... (Waiting for Silicon)")
            start_hw_time = time.time()

            eraser = FlashEraser(self.session, FlashEraser.Mode.CHIP)
            eraser.erase()

            hw_duration = time.time() - start_hw_time
            print(
                f"[DEBUG-SESSION ERASE SWD] ✔ Hardware Silicon Erase took {hw_duration:.2f} seconds!")
            logger.info("✔ Full Chip Erase completed via SWD.")
            return True
        except Exception as e:
            print(f"[DEBUG-SESSION ERASE SWD EXCEPTION] {e}")
            logger.error(f"SWD Chip Erase failed: {str(e)}")
            return False

    def program_firmware(self, firmware_path: str, base_address: int = 0x08000000) -> bool:
        """Programs binary/hex firmware file to target flash via SWD or DFU."""
        print(
            f"\n[DEBUG-SESSION PROGRAM] Flashing firmware -> File: {firmware_path}, Base Addr: 0x{base_address:08X}")
        if not os.path.exists(firmware_path):
            print(
                f"[DEBUG-SESSION PROGRAM ERROR] Firmware file path does not exist: {firmware_path}")
            logger.error(f"Firmware file not found: {firmware_path}")
            return False

        if "USB" in self.interface_type:
            logger.info(
                f"Flashing firmware via USB DFU: {firmware_path} -> 0x{base_address:08X}...")
            try:
                cmd = [
                    EXE_DFU, "-a", "0", "-s", f"0x{base_address:08X}:leave", "-D", firmware_path
                ]
                print(
                    f"[DEBUG-SESSION PROGRAM USB] Running command: {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, text=True)
                print(
                    f"[DEBUG-SESSION PROGRAM USB] Return code: {result.returncode}")

                if result.returncode == 0:
                    print(
                        "[DEBUG-SESSION PROGRAM USB] Firmware successfully flashed and leave command sent.")
                    logger.info(
                        "✔ Firmware Flashed and reset executed successfully via USB DFU.")
                    return True
                else:
                    print(
                        f"[DEBUG-SESSION PROGRAM USB ERROR] Stderr: {result.stderr}")
                    logger.error(f"DFU Programming Error: {result.stderr}")
                    return False
            except Exception as e:
                print(f"[DEBUG-SESSION PROGRAM USB EXCEPTION] {e}")
                logger.error(f"DFU Programming exception: {str(e)}")
                return False

        # SWD Mode via pyOCD
        if not self.session or not self.target:
            print(
                "[DEBUG-SESSION PROGRAM SWD] Session not active. Attempting to connect...")
            if not self.connect():
                return False
        try:
            # 🛡️ سپر امنیتی ضد تایم‌اوت
            print(
                "[DEBUG-SESSION PROGRAM SWD] Engaging Anti-Timeout Shield (Halt & PRIMASK=1)...")
            try:
                if self.target.get_state() != Target.State.HALTED:
                    self.target.halt()
                self.target.write_core_register('primask', 1)
            except Exception as e:
                print(
                    f"[DEBUG-SESSION PROGRAM SWD] Warning during pre-program halt: {e}")

            print(
                "[DEBUG-SESSION PROGRAM SWD] Initializing FileProgrammer... (Waiting for Silicon)")
            start_hw_time = time.time()

            programmer = FileProgrammer(self.session)
            programmer.program(firmware_path, base_address=base_address)

            hw_duration = time.time() - start_hw_time
            print(
                f"[DEBUG-SESSION PROGRAM SWD] ✔ Hardware Flash & Verify took {hw_duration:.2f} seconds!")
            logger.info("✔ Firmware Flashed successfully via SWD.")
            return True
        except Exception as e:
            print(f"[DEBUG-SESSION PROGRAM SWD EXCEPTION] {e}")
            logger.error(f"SWD Programming failed: {str(e)}")
            return False

    def halt_target(self) -> bool:
        """Send halt request to target core."""
        print("[DEBUG-SESSION HALT] Sending halt request to target...")
        if "USB" in self.interface_type:
            print("[DEBUG-SESSION HALT] USB mode active, bypass.")
            return True

        if not self.target:
            print("[DEBUG-SESSION HALT ERROR] Target is not connected.")
            return False
        try:
            self.target.halt()
            print("[DEBUG-SESSION HALT] Target halted successfully.")
            return True
        except Exception as e:
            print(f"[DEBUG-SESSION HALT EXCEPTION] {e}")
            logger.error(f"Failed to halt target core: {str(e)}")
            return False

    def reset_target(self, halt: bool = False) -> bool:
        """Reset target core, optionally halting immediately upon reset."""
        print(
            f"[DEBUG-SESSION RESET] Resetting target (halt_on_reset={halt})...")
        if "USB" in self.interface_type:
            print("[DEBUG-SESSION RESET] USB mode active, bypass.")
            return True

        if not self.target:
            print("[DEBUG-SESSION RESET ERROR] Target is not connected.")
            return False
        try:
            if halt:
                self.target.reset_and_halt()
                print("[DEBUG-SESSION RESET] Target reset and halted.")
            else:
                self.target.reset()
                print("[DEBUG-SESSION RESET] Target reset executed.")
            return True
        except Exception as e:
            print(f"[DEBUG-SESSION RESET EXCEPTION] {e}")
            logger.error(f"Failed to reset target: {str(e)}")
            return False

    def close(self) -> None:
        print("\n[DEBUG-SESSION CLOSE] Closing session and releasing resources...")
        if "USB" in self.interface_type:
            self.is_usb_connected = False
            print("[DEBUG-SESSION CLOSE] Direct USB session flags cleared.")
            logger.info("Direct USB session closed successfully.")
            return

        if self.session:
            try:
                print("[DEBUG-SESSION CLOSE] Closing active pyOCD session...")
                self.session.close()
                print("[DEBUG-SESSION CLOSE] pyOCD session closed successfully.")
                logger.info("SWD session closed successfully.")
            except Exception as e:
                print(f"[DEBUG-SESSION CLOSE EXCEPTION] {e}")
                logger.debug(f"Error closing session: {str(e)}")
            finally:
                self.session = None
                self.target = None
                print("[DEBUG-SESSION CLOSE] References cleaned up.")
        else:
            print("[DEBUG-SESSION CLOSE] No active session to close.")

    def __enter__(self):
        print("[DEBUG-SESSION CONTEXT] Entering SessionManager context manager...")
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        print(
            f"[DEBUG-SESSION CONTEXT] Exiting context manager (Exception: {exc_type})...")
        self.close()
