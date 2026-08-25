
# """
# Low-level SWD/pyOCD and Direct USB session manager handling probe connections,
# USB DFU discovery, automatic fallback strategies, core register inspection,
# and unified memory read/write operations.
# (Features Universal ARM Global Pack Auto-Downloader)
# """

# import subprocess
# import os
# import tempfile
# import glob
# import re  # ⬅️ برای استخراج هوشمند نام میکرو از متن خطا
# import sys  # ⬅️ برای مدیریت دستورات دانلود
# from typing import Optional, Dict, Any, List

# from pyocd.core.helpers import ConnectHelper
# from pyocd.core.session import Session
# from pyocd.core.target import Target
# from pyocd.flash.file_programmer import FileProgrammer
# from pyocd.flash.eraser import FlashEraser

# from src.common.logger import get_logger
# from src.common.registers import (
#     DHCSR_ADDR,
#     DEMCR_ADDR,
#     DHCSR_BITS,
#     DEMCR_BITS,
# )
# from src.common.resources import EXE_DFU
# from src.common.paths import get_path

# logger = get_logger("SessionManager")


# class SessionManager:
#     """
#     Manages physical SWD debug probe sessions (via pyOCD) as well as
#     Direct USB (DFU/CDC) hardware interfaces with ARM Cortex-M microcontrollers.
#     """

#     def __init__(
#         self,
#         target_type: Optional[str] = None,
#         clock_freq: int = 100000,
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

#         # Load Local Offline Packs (If any exist)
#         self.available_packs = []
#         try:
#             packs_dir = get_path("assets/packs")
#             if os.path.exists(packs_dir):
#                 self.available_packs = glob.glob(
#                     os.path.join(packs_dir, "*.pack"))
#                 print(
#                     f"[DEBUG-SESSION INIT] Found {len(self.available_packs)} offline CMSIS-Pack(s).")
#             else:
#                 print(
#                     "[DEBUG-SESSION INIT] No 'assets/packs' directory found. Running dynamically.")
#         except Exception as e:
#             print(f"[DEBUG-SESSION INIT] Error loading offline packs: {e}")

#         print(f"\n[DEBUG-SESSION INIT] SessionManager created.")
#         print(f"  -> Interface Type: {self.interface_type}")
#         print(f"  -> Target Type: {self.target_type}")
#         print(f"  -> Clock Frequency: {self.clock_freq} Hz")
#         print(f"  -> Connect Mode: {self.connect_mode}")
#         print(
#             f"  -> Target Probe UID: {self.unique_id or 'Auto-Detect (First Available)'}\n")

#     # =================================================================
#     # ⬅️ هسته دانلودر جهانی (Online Global Pack Downloader)
#     # =================================================================
#     def _download_missing_pack(self, target_name: str) -> bool:
#         """Connects to the global ARM index to download missing MCU drivers."""
#         print(f"\n[DEBUG-SESSION] ===============================================")
#         print(f"[DEBUG-SESSION] 🌍 ONLINE CMSIS-PACK DOWNLOADER TRIGGERED")
#         print(
#             f"[DEBUG-SESSION] Fetching hardware definitions for: {target_name.upper()}")
#         print(f"[DEBUG-SESSION] ===============================================\n")
#         logger.warning(
#             f"Downloading required CMSIS-Pack for {target_name.upper()} from ARM global index... Please wait.")

#         old_argv = sys.argv
#         # شبیه‌سازی اجرای دستور pyocd pack install در خط فرمان
#         sys.argv = ["pyocd", "pack", "install", target_name]
#         try:
#             # فراخوانی امن نقطه ورود اصلی pyOCD برای دانلود
#             from pyocd.__main__ import main as pyocd_main
#             pyocd_main()
#             logger.info(
#                 f"✔ Pack for {target_name.upper()} downloaded and cached successfully!")
#             return True
#         except SystemExit as se:
#             # pyOCD بعد از پایان عملیات موفق کد صفر برمی‌گرداند
#             if se.code == 0:
#                 logger.info(
#                     f"✔ Pack for {target_name.upper()} downloaded and cached successfully!")
#                 return True
#             else:
#                 logger.error(
#                     f"Failed to download pack for {target_name.upper()} (Exit code {se.code}). Check internet connection.")
#                 return False
#         except Exception as e:
#             print(f"[DEBUG-SESSION] Pack downloader exception: {e}")
#             logger.error(f"Error communicating with ARM index: {str(e)}")
#             return False
#         finally:
#             sys.argv = old_argv  # بازگرداندن وضعیت سیستم به حالت عادی

#     @staticmethod
#     def list_probes() -> List[Any]:
#         """Scan and return all connected CMSIS-DAP / B-Link debug probes."""
#         print("[DEBUG-SESSION list_probes] Scanning for connected debug probes...")
#         probes = ConnectHelper.get_all_connected_probes()
#         print(
#             f"[DEBUG-SESSION list_probes] Found {len(probes) if probes else 0} probe(s).")
#         if not probes:
#             logger.warning("No B-Link debug probes found via USB.")
#         return probes

#     def probe_usb_device(self) -> Dict[str, Any]:
#         """
#         Scans for STM32 DFU target devices using the dfu-util command line tool.
#         """
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
#                 [EXE_DFU, "-l"],
#                 capture_output=True, text=True, check=False
#             )

#             output = result.stdout.lower()
#             print(
#                 f"[DEBUG-SESSION USB_PROBE] dfu-util stdout:\n{result.stdout}")
#             if result.stderr:
#                 print(
#                     f"[DEBUG-SESSION USB_PROBE] dfu-util stderr:\n{result.stderr}")

#             if "found dfu" in output and "0483:df11" in output:
#                 info["success"] = True
#                 info["dpidr"] = "0483:DF11 (VID:PID)"
#                 info["probe_serial"] = "USB_DFU_Link"
#                 info["rdp_status"] = "LEVEL 0 (ASSUMED)"
#                 print(
#                     "[DEBUG-SESSION USB_PROBE] Match found! STM32 DFU device detected.")
#                 logger.info(
#                     "✔ STM32 DFU Device detected successfully via dfu-util.")
#             else:
#                 info["error"] = "No STM32 DFU device found. Make sure BOOT0=1 and device is plugged in."
#                 print(
#                     "[DEBUG-SESSION USB_PROBE] No matching 0483:df11 DFU device found in output.")
#                 logger.warning("✖ No Direct USB (DFU) device detected.")

#         except FileNotFoundError:
#             err_msg = f"dfu-util not found at {EXE_DFU}! Please ensure it is bundled correctly."
#             info["error"] = err_msg
#             print(f"[DEBUG-SESSION USB_PROBE CRITICAL] {err_msg}")
#             logger.error(err_msg)
#         except Exception as e:
#             info["error"] = str(e)
#             print(f"[DEBUG-SESSION USB_PROBE EXCEPTION] {str(e)}")
#             logger.error(f"DFU probe exception: {str(e)}")

#         print(f"[DEBUG-SESSION USB_PROBE] Result summary: {info}\n")
#         return info

#     def probe_target_info(self, clock_freq: int = 1000000, _auto_downloaded: bool = False) -> Dict[str, Any]:
#         """
#         Lightweight attach session to retrieve probe unique ID,
#         MCU part number, and DPIDR / USB ID without resetting the target.
#         """
#         print(
#             f"\n[DEBUG-SESSION PROBE_INFO] Starting probe_target_info with clock={clock_freq}Hz")
#         if "USB" in self.interface_type:
#             print("[DEBUG-SESSION PROBE_INFO] Routing to USB probe handler.")
#             return self.probe_usb_device()

#         session = None
#         info = {
#             "success": False,
#             "probe_serial": "Unknown",
#             "part_number": "Unknown",
#             "dpidr": "N/A",
#             "core_type": "Unknown",
#             "error": "",
#         }

#         def _safe_close(sess):
#             if sess:
#                 try:
#                     print(
#                         "[DEBUG-SESSION PROBE_INFO] Closing previous session before retry...")
#                     sess.close()
#                 except Exception as close_exc:
#                     print(
#                         f"[DEBUG-SESSION PROBE_INFO] Error while closing session: {close_exc}")

#         def _read_core_type(tgt) -> str:
#             try:
#                 core = tgt.cores[0]
#                 code = core.core_type
#                 try:
#                     from pyocd.coresight.core_ids import CORE_TYPE_NAME
#                     return str(CORE_TYPE_NAME.get(code, code)).upper()
#                 except ImportError:
#                     return str(code).upper()
#             except Exception as core_exc:
#                 print(
#                     f"[DEBUG-SESSION PROBE_INFO] Could not read core_type: {core_exc}")
#                 return "UNKNOWN"

#         try:
#             options = {
#                 "connect_mode": "attach",
#                 "frequency": clock_freq,
#                 "target_override": None,
#                 "halt_on_connect": False,
#             }

#             if self.available_packs:
#                 options["pack"] = self.available_packs

#             print(f"[DEBUG-SESSION PROBE_INFO] Connecting options: {options}")

#             session = ConnectHelper.session_with_chosen_probe(
#                 blocking=False,
#                 options=options,
#                 unique_id=self.unique_id
#             )

#             if session is None:
#                 raise Exception("No B-Link/SWD probe detected on USB.")

#             print("[DEBUG-SESSION PROBE_INFO] Probe found. Opening session...")
#             session.open()

#             try:
#                 info["probe_serial"] = str(session.probe.unique_id)
#                 print(
#                     f"[DEBUG-SESSION PROBE_INFO] Probe Unique ID: {info['probe_serial']}")
#             except Exception as serial_exc:
#                 print(
#                     f"[DEBUG-SESSION PROBE_INFO] Could not read unique ID: {serial_exc}")
#                 info["probe_serial"] = "Detected"

#             target = session.board.target
#             dpidr_val = 0
#             try:
#                 dpidr_val = session.probe.read_dp(0x0)
#                 print(
#                     f"[DEBUG-SESSION PROBE_INFO] Read DPIDR register: 0x{dpidr_val:08X}")
#             except Exception as dp_exc:
#                 print(
#                     f"[DEBUG-SESSION PROBE_INFO] Failed to read DP 0x0: {dp_exc}")
#                 pass

#             info["success"] = True
#             info["part_number"] = str(target.part_number).upper()
#             info["dpidr"] = f"0x{dpidr_val:08X}" if dpidr_val else "Detected"
#             info["core_type"] = _read_core_type(target)
#             print(
#                 f"[DEBUG-SESSION PROBE_INFO] Success! Target Part: {info['part_number']}, Core: {info['core_type']}")

#         except Exception as e:
#             err_lower = str(e).lower()
#             print(
#                 f"[DEBUG-SESSION PROBE_INFO EXCEPTION] Primary attempt failed: {e}")

#             _safe_close(session)
#             session = None

#             # ⬅️ تشخیص هوشمند میکروی ناشناس و دانلود اتوماتیک
#             match = re.search(r"target type (\w+) not recognized", err_lower)
#             if match and not _auto_downloaded:
#                 missing_mcu = match.group(1)
#                 if self._download_missing_pack(missing_mcu):
#                     print(
#                         "[DEBUG-SESSION PROBE_INFO] Pack downloaded. Retrying probe automatically...")
#                     # تلاش مجدد با پارامتر _auto_downloaded=True برای جلوگیری از لوپ بی‌نهایت
#                     return self.probe_target_info(clock_freq, _auto_downloaded=True)

#             if "no daplink" in err_lower or "probe detected" in err_lower:
#                 info["error"] = str(e)
#                 print(
#                     "[DEBUG-SESSION PROBE_INFO] No hardware probe available. Aborting fallback.")
#                 return info

#             if "not recognized" in err_lower or "target" in err_lower:
#                 print(
#                     "[DEBUG-SESSION PROBE_INFO] Target not recognized even after download attempt. Fallback to 'cortex_m'...")
#                 try:
#                     options["target_override"] = "cortex_m"
#                     session = ConnectHelper.session_with_chosen_probe(
#                         blocking=False,
#                         options=options,
#                         unique_id=self.unique_id
#                     )

#                     if session is None:
#                         raise Exception(
#                             "No DAPLink/SWD probe detected on USB.")

#                     session.open()

#                     try:
#                         info["probe_serial"] = str(session.probe.unique_id)
#                     except Exception:
#                         info["probe_serial"] = "Detected"

#                     target = session.board.target
#                     info["success"] = True
#                     info["part_number"] = "CORTEX-M (Generic)"
#                     info["core_type"] = _read_core_type(target)
#                     info["dpidr"] = "0x2BA01477 (Default DP)"
#                     print(
#                         "[DEBUG-SESSION PROBE_INFO] Fallback to generic cortex_m successful.")
#                 except Exception as e2:
#                     print(
#                         f"[DEBUG-SESSION PROBE_INFO FALLBACK EXCEPTION] {e2}")
#                     info["error"] = str(e2)
#             else:
#                 info["error"] = str(e)
#         finally:
#             _safe_close(session)

#         print(f"[DEBUG-SESSION PROBE_INFO] Final result: {info}\n")
#         return info

#     def _open_session(
#         self, freq: int, mode: str, target_name: Optional[str], _auto_downloaded: bool = False
#     ) -> bool:
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
#                 f"Attempting SWD connection -> Target: '{target_name}' | "
#                 f"Clock: {freq // 1000} kHz | Mode: '{mode}'..."
#             )
#             self.session = ConnectHelper.session_with_chosen_probe(
#                 options=options,
#                 unique_id=self.unique_id
#             )

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

#             # ⬅️ تشخیص هوشمند میکروی ناشناس و دانلود اتوماتیک در زمان اتصال
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
#         """
#         Connect to target microcontroller using selected interface (DAPLink or Direct USB).
#         """
#         print(
#             f"\n[DEBUG-SESSION CONNECT] Starting connect() procedure. Interface: {self.interface_type}")
#         if "USB" in self.interface_type:
#             print(
#                 "[DEBUG-SESSION CONNECT] USB mode active. Bypassing SWD connection sequence.")
#             logger.info("Establishing direct USB session...")
#             self.is_usb_connected = True
#             return True

#         # Level 1: Primary attempt
#         print(
#             f"[DEBUG-SESSION CONNECT] Level 1 attempt -> Clock: {self.clock_freq}, Mode: {self.connect_mode}, Target: {self.target_type}")
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
#             "SWD connection error. Switching to Diagnostics Fallback: "
#             "50 kHz clock & 'attach' mode..."
#         )
#         fallback_target = (
#             "cortex_m" if self.target_type == "cortex_m" else self.target_type
#         )
#         if self._open_session(50000, "attach", fallback_target):
#             self.clock_freq = 50000
#             self.connect_mode = "attach"
#             self.target_type = fallback_target
#             print("[DEBUG-SESSION CONNECT] Diagnostics Fallback successful!")
#             return True

#         print(
#             "[DEBUG-SESSION CONNECT CRITICAL] All SWD connection strategies failed completely.")
#         logger.critical(
#             "All SWD connection strategies failed. Verify physical wiring."
#         )
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
#                     EXE_DFU,
#                     "-a", "0",
#                     "-s", f"0x{addr:08X}:{count}",
#                     "-U", temp_path
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
#             print("[DEBUG-SESSION ERASE SWD] Triggering FlashEraser with CHIP mode...")
#             eraser = FlashEraser(self.session, FlashEraser.Mode.CHIP)
#             eraser.erase()
#             print(
#                 "[DEBUG-SESSION ERASE SWD] Chip erase completed successfully via SWD.")
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
#                     EXE_DFU,
#                     "-a", "0",
#                     "-s", f"0x{base_address:08X}:leave",
#                     "-D", firmware_path
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
#             print("[DEBUG-SESSION PROGRAM SWD] Initializing FileProgrammer...")
#             programmer = FileProgrammer(self.session)
#             programmer.program(firmware_path, base_address=base_address)
#             print(
#                 "[DEBUG-SESSION PROGRAM SWD] Firmware successfully programmed via SWD.")
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
USB DFU discovery, automatic fallback strategies, core register inspection,
and unified memory read/write operations. 
(Features Universal ARM Global Pack Auto-Downloader with Callbacks for UI Lock)
"""

import subprocess
import os
import tempfile
import glob
import re  # برای استخراج هوشمند نام میکرو از متن خطا
import sys  # برای مدیریت دستورات دانلود
from typing import Optional, Dict, Any, List, Callable

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
)
from src.common.resources import EXE_DFU
from src.common.paths import get_path

logger = get_logger("SessionManager")


class SessionManager:
    """
    Manages physical SWD debug probe sessions (via pyOCD) as well as
    Direct USB (DFU/CDC) hardware interfaces with ARM Cortex-M microcontrollers.
    """

    def __init__(
        self,
        target_type: Optional[str] = None,
        clock_freq: int = 100000,
        connect_mode: str = "under-reset",
        interface_type: str = "B-Link (SWD)",
        unique_id: Optional[str] = None,
        # ⬅️ اضافه شدن کالبک‌ها برای اطلاع دادن به لایه گرافیکی (UI)
        download_start_callback: Optional[Callable[[str], None]] = None,
        download_finish_callback: Optional[Callable[[bool, str], None]] = None,
    ):
        self.target_type = target_type
        self.clock_freq = clock_freq
        self.connect_mode = connect_mode
        self.interface_type = interface_type
        self.unique_id = unique_id

        self.download_start_callback = download_start_callback
        self.download_finish_callback = download_finish_callback

        # SWD Session / Target objects
        self.session: Optional[Session] = None
        self.target: Optional[Target] = None

        # USB Direct Session state
        self.is_usb_connected: bool = False

        self.available_packs = []
        try:
            packs_dir = get_path("assets/packs")
            if os.path.exists(packs_dir):
                self.available_packs = glob.glob(
                    os.path.join(packs_dir, "*.pack"))
                print(
                    f"[DEBUG-SESSION INIT] Found {len(self.available_packs)} offline CMSIS-Pack(s).")
            else:
                print(
                    "[DEBUG-SESSION INIT] No 'assets/packs' directory found. Running without offline packs.")
        except Exception as e:
            print(f"[DEBUG-SESSION INIT] Error loading offline packs: {e}")

        print(f"\n[DEBUG-SESSION INIT] SessionManager created.")
        print(f"  -> Interface Type: {self.interface_type}")
        print(f"  -> Target Type: {self.target_type}")
        print(f"  -> Clock Frequency: {self.clock_freq} Hz")
        print(f"  -> Connect Mode: {self.connect_mode}")
        print(
            f"  -> Target Probe UID: {self.unique_id or 'Auto-Detect (First Available)'}\n")

    # =================================================================
    # ⬅️ هسته دانلودر جهانی (Online Global Pack Downloader)
    # =================================================================
    def _download_missing_pack(self, target_name: str) -> bool:
        """Connects to the global ARM index to download missing MCU drivers."""
        print(f"\n[DEBUG-SESSION] ===============================================")
        print(f"[DEBUG-SESSION] 🌍 ONLINE CMSIS-PACK DOWNLOADER TRIGGERED")
        print(
            f"[DEBUG-SESSION] Fetching hardware definitions for: {target_name.upper()}")
        print(f"[DEBUG-SESSION] ===============================================\n")
        logger.warning(
            f"Downloading required CMSIS-Pack for {target_name.upper()} from ARM global index... Please wait.")

        # ⬅️ به UI خبر می‌دهیم که صفحه را قفل کند و پیام لودینگ نشان دهد
        if self.download_start_callback:
            self.download_start_callback(target_name.upper())

        old_argv = sys.argv
        sys.argv = ["pyocd", "pack", "install", target_name]
        try:
            from pyocd.__main__ import main as pyocd_main
            pyocd_main()
            pack_target.PackTargets.clear_cache()

            msg = f"✔ Pack for {target_name.upper()} downloaded and cached successfully!"
            logger.info(msg)

            # ⬅️ به UI خبر می‌دهیم که دانلود موفقیت‌آمیز بود و صفحه را باز کند
            if self.download_finish_callback:
                self.download_finish_callback(True, msg)
            return True

        except SystemExit as se:
            if se.code == 0:
                pack_target.PackTargets.clear_cache()
                msg = f"✔ Pack for {target_name.upper()} downloaded and cached successfully!"
                logger.info(msg)

                # ⬅️ اطلاع موفقیت به UI
                if self.download_finish_callback:
                    self.download_finish_callback(True, msg)
                return True
            else:
                msg = f"Failed to download pack for {target_name.upper()} (Exit code {se.code}). Check internet connection."
                logger.error(msg)

                # ⬅️ اطلاع شکست به UI
                if self.download_finish_callback:
                    self.download_finish_callback(False, msg)
                return False

        except Exception as e:
            msg = f"Error communicating with ARM index: {str(e)}"
            print(f"[DEBUG-SESSION] Pack downloader exception: {e}")
            logger.error(msg)
            if self.download_finish_callback:
                self.download_finish_callback(False, msg)
            return False

        finally:
            sys.argv = old_argv

    @staticmethod
    def list_probes() -> List[Any]:
        """Scan and return all connected CMSIS-DAP / B-Link debug probes."""
        print("[DEBUG-SESSION list_probes] Scanning for connected debug probes...")
        probes = ConnectHelper.get_all_connected_probes()
        print(
            f"[DEBUG-SESSION list_probes] Found {len(probes) if probes else 0} probe(s).")
        if not probes:
            logger.warning("No B-Link debug probes found via USB.")
        return probes

    def probe_usb_device(self) -> Dict[str, Any]:
        """
        Scans for STM32 DFU target devices using the dfu-util command line tool.
        """
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
                [EXE_DFU, "-l"],
                capture_output=True, text=True, check=False
            )

            output = result.stdout.lower()
            print(
                f"[DEBUG-SESSION USB_PROBE] dfu-util stdout:\n{result.stdout}")
            if result.stderr:
                print(
                    f"[DEBUG-SESSION USB_PROBE] dfu-util stderr:\n{result.stderr}")

            if "found dfu" in output and "0483:df11" in output:
                info["success"] = True
                info["dpidr"] = "0483:DF11 (VID:PID)"
                info["probe_serial"] = "USB_DFU_Link"
                info["rdp_status"] = "LEVEL 0 (ASSUMED)"
                print(
                    "[DEBUG-SESSION USB_PROBE] Match found! STM32 DFU device detected.")
                logger.info(
                    "✔ STM32 DFU Device detected successfully via dfu-util.")
            else:
                info["error"] = "No STM32 DFU device found. Make sure BOOT0=1 and device is plugged in."
                print(
                    "[DEBUG-SESSION USB_PROBE] No matching 0483:df11 DFU device found in output.")
                logger.warning("✖ No Direct USB (DFU) device detected.")

        except FileNotFoundError:
            err_msg = f"dfu-util not found at {EXE_DFU}! Please ensure it is bundled correctly."
            info["error"] = err_msg
            print(f"[DEBUG-SESSION USB_PROBE CRITICAL] {err_msg}")
            logger.error(err_msg)
        except Exception as e:
            info["error"] = str(e)
            print(f"[DEBUG-SESSION USB_PROBE EXCEPTION] {str(e)}")
            logger.error(f"DFU probe exception: {str(e)}")

        print(f"[DEBUG-SESSION USB_PROBE] Result summary: {info}\n")
        return info

    def probe_target_info(self, clock_freq: int = 1000000, _auto_downloaded: bool = False) -> Dict[str, Any]:
        """
        Lightweight attach session to retrieve probe unique ID,
        MCU part number, and DPIDR / USB ID without resetting the target.
        """
        print(
            f"\n[DEBUG-SESSION PROBE_INFO] Starting probe_target_info with clock={clock_freq}Hz")
        if "USB" in self.interface_type:
            print("[DEBUG-SESSION PROBE_INFO] Routing to USB probe handler.")
            return self.probe_usb_device()

        session = None
        info = {
            "success": False,
            "probe_serial": "Unknown",
            "part_number": "Unknown",
            "dpidr": "N/A",
            "core_type": "Unknown",
            "error": "",
        }

        def _safe_close(sess):
            if sess:
                try:
                    print(
                        "[DEBUG-SESSION PROBE_INFO] Closing previous session before retry...")
                    sess.close()
                except Exception as close_exc:
                    print(
                        f"[DEBUG-SESSION PROBE_INFO] Error while closing session: {close_exc}")

        def _read_core_type(tgt) -> str:
            try:
                core = tgt.cores[0]
                code = core.core_type
                try:
                    from pyocd.coresight.core_ids import CORE_TYPE_NAME
                    return str(CORE_TYPE_NAME.get(code, code)).upper()
                except ImportError:
                    return str(code).upper()
            except Exception as core_exc:
                print(
                    f"[DEBUG-SESSION PROBE_INFO] Could not read core_type: {core_exc}")
                return "UNKNOWN"

        try:
            options = {
                "connect_mode": "attach",
                "frequency": clock_freq,
                "target_override": None,
                "halt_on_connect": False,
            }
            if self.available_packs:
                options["pack"] = self.available_packs

            print(f"[DEBUG-SESSION PROBE_INFO] Connecting options: {options}")

            session = ConnectHelper.session_with_chosen_probe(
                blocking=False,
                options=options,
                unique_id=self.unique_id
            )

            if session is None:
                raise Exception("No B-Link/SWD probe detected on USB.")

            print("[DEBUG-SESSION PROBE_INFO] Probe found. Opening session...")
            session.open()

            try:
                info["probe_serial"] = str(session.probe.unique_id)
                print(
                    f"[DEBUG-SESSION PROBE_INFO] Probe Unique ID: {info['probe_serial']}")
            except Exception as serial_exc:
                print(
                    f"[DEBUG-SESSION PROBE_INFO] Could not read unique ID: {serial_exc}")
                info["probe_serial"] = "Detected"

            target = session.board.target
            dpidr_val = 0
            try:
                dpidr_val = session.probe.read_dp(0x0)
                print(
                    f"[DEBUG-SESSION PROBE_INFO] Read DPIDR register: 0x{dpidr_val:08X}")
            except Exception as dp_exc:
                print(
                    f"[DEBUG-SESSION PROBE_INFO] Failed to read DP 0x0: {dp_exc}")
                pass

            info["success"] = True
            info["part_number"] = str(target.part_number).upper()
            info["dpidr"] = f"0x{dpidr_val:08X}" if dpidr_val else "Detected"
            info["core_type"] = _read_core_type(target)
            print(
                f"[DEBUG-SESSION PROBE_INFO] Success! Target Part: {info['part_number']}, Core: {info['core_type']}")

        except Exception as e:
            err_lower = str(e).lower()
            print(
                f"[DEBUG-SESSION PROBE_INFO EXCEPTION] Primary attempt failed: {e}")

            _safe_close(session)
            session = None

            # تشخیص هوشمند میکروی ناشناس و دانلود اتوماتیک
            match = re.search(r"target type (\w+) not recognized", err_lower)
            if match and not _auto_downloaded:
                missing_mcu = match.group(1)
                if self._download_missing_pack(missing_mcu):
                    print(
                        "[DEBUG-SESSION PROBE_INFO] Pack downloaded. Retrying probe automatically...")
                    return self.probe_target_info(clock_freq, _auto_downloaded=True)

            if "no daplink" in err_lower or "probe detected" in err_lower:
                info["error"] = str(e)
                print(
                    "[DEBUG-SESSION PROBE_INFO] No hardware probe available. Aborting fallback.")
                return info

            if "not recognized" in err_lower or "target" in err_lower:
                print(
                    "[DEBUG-SESSION PROBE_INFO] Target not recognized even after download attempt. Fallback to 'cortex_m'...")
                try:
                    options["target_override"] = "cortex_m"
                    session = ConnectHelper.session_with_chosen_probe(
                        blocking=False,
                        options=options,
                        unique_id=self.unique_id
                    )

                    if session is None:
                        raise Exception(
                            "No DAPLink/SWD probe detected on USB.")

                    session.open()

                    try:
                        info["probe_serial"] = str(session.probe.unique_id)
                    except Exception:
                        info["probe_serial"] = "Detected"

                    target = session.board.target
                    info["success"] = True
                    info["part_number"] = "CORTEX-M (Generic)"
                    info["core_type"] = _read_core_type(target)
                    info["dpidr"] = "0x2BA01477 (Default DP)"
                    print(
                        "[DEBUG-SESSION PROBE_INFO] Fallback to generic cortex_m successful.")
                except Exception as e2:
                    print(
                        f"[DEBUG-SESSION PROBE_INFO FALLBACK EXCEPTION] {e2}")
                    info["error"] = str(e2)
            else:
                info["error"] = str(e)
        finally:
            _safe_close(session)

        print(f"[DEBUG-SESSION PROBE_INFO] Final result: {info}\n")
        return info

    def _open_session(
        self, freq: int, mode: str, target_name: Optional[str], _auto_downloaded: bool = False
    ) -> bool:
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
                f"Attempting SWD connection -> Target: '{target_name}' | "
                f"Clock: {freq // 1000} kHz | Mode: '{mode}'..."
            )
            self.session = ConnectHelper.session_with_chosen_probe(
                options=options,
                unique_id=self.unique_id
            )

            if self.session is None:
                print(
                    "[DEBUG-SESSION _open_session] session_with_chosen_probe returned None.")
                return False

            print("[DEBUG-SESSION _open_session] Opening session...")
            self.session.open()
            self.target = self.session.target
            print("[DEBUG-SESSION _open_session] SWD session successfully established!")
            logger.info("SWD session established successfully.")
            return True

        except Exception as e:
            err_str = str(e)

            # تشخیص هوشمند میکروی ناشناس و دانلود اتوماتیک در زمان اتصال
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
        """
        Connect to target microcontroller using selected interface (DAPLink or Direct USB).
        """
        print(
            f"\n[DEBUG-SESSION CONNECT] Starting connect() procedure. Interface: {self.interface_type}")
        if "USB" in self.interface_type:
            print(
                "[DEBUG-SESSION CONNECT] USB mode active. Bypassing SWD connection sequence.")
            logger.info("Establishing direct USB session...")
            self.is_usb_connected = True
            return True

        # Level 1: Primary attempt
        print(
            f"[DEBUG-SESSION CONNECT] Level 1 attempt -> Clock: {self.clock_freq}, Mode: {self.connect_mode}, Target: {self.target_type}")
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
            "SWD connection error. Switching to Diagnostics Fallback: "
            "50 kHz clock & 'attach' mode..."
        )
        fallback_target = (
            "cortex_m" if self.target_type == "cortex_m" else self.target_type
        )
        if self._open_session(50000, "attach", fallback_target):
            self.clock_freq = 50000
            self.connect_mode = "attach"
            self.target_type = fallback_target
            print("[DEBUG-SESSION CONNECT] Diagnostics Fallback successful!")
            return True

        print(
            "[DEBUG-SESSION CONNECT CRITICAL] All SWD connection strategies failed completely.")
        logger.critical(
            "All SWD connection strategies failed. Verify physical wiring."
        )
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
                    EXE_DFU,
                    "-a", "0",
                    "-s", f"0x{addr:08X}:{count}",
                    "-U", temp_path
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
            print("[DEBUG-SESSION ERASE SWD] Triggering FlashEraser with CHIP mode...")
            eraser = FlashEraser(self.session, FlashEraser.Mode.CHIP)
            eraser.erase()
            print(
                "[DEBUG-SESSION ERASE SWD] Chip erase completed successfully via SWD.")
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
                    EXE_DFU,
                    "-a", "0",
                    "-s", f"0x{base_address:08X}:leave",
                    "-D", firmware_path
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
            print("[DEBUG-SESSION PROGRAM SWD] Initializing FileProgrammer...")
            programmer = FileProgrammer(self.session)
            programmer.program(firmware_path, base_address=base_address)
            print(
                "[DEBUG-SESSION PROGRAM SWD] Firmware successfully programmed via SWD.")
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
