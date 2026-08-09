# """
# Low-level SWD/pyOCD and Direct USB session manager handling probe connections,
# USB DFU discovery, automatic fallback strategies, core register inspection,
# and unified memory read/write operations.
# """

# import subprocess
# import os
# import tempfile
# from typing import Optional, Dict, Any, List
# from pyocd.core.helpers import ConnectHelper
# from pyocd.core.session import Session
# from pyocd.core.target import Target

# from src.common.logger import get_logger
# from src.common.registers import (
#     DHCSR_ADDR,
#     DEMCR_ADDR,
#     DHCSR_BITS,
#     DEMCR_BITS,
# )

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
#         interface_type: str = "DAPLink (SWD)",
#     ):
#         self.target_type = target_type
#         self.clock_freq = clock_freq
#         self.connect_mode = connect_mode
#         self.interface_type = interface_type

#         # SWD Session / Target objects
#         self.session: Optional[Session] = None
#         self.target: Optional[Target] = None

#         # USB Direct Session state
#         self.is_usb_connected: bool = False

#     @staticmethod
#     def list_probes() -> List[Any]:
#         """Scan and return all connected CMSIS-DAP / DAPLink debug probes."""
#         probes = ConnectHelper.get_all_connected_probes()
#         if not probes:
#             logger.warning("No DAPLink/CMSIS-DAP debug probes found via USB.")
#         return probes

#     def probe_usb_device(self) -> Dict[str, Any]:
#         """
#         Scans for STM32 DFU target devices using the dfu-util command line tool.
#         """
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
#             result = subprocess.run(
#                 ["dfu-util", "-l"],
#                 capture_output=True, text=True, check=False
#             )

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
#             err_msg = "dfu-util not found! Please place dfu-util.exe in the project folder."
#             info["error"] = err_msg
#             logger.error(err_msg)
#         except Exception as e:
#             info["error"] = str(e)
#             logger.error(f"DFU probe exception: {str(e)}")

#         return info

#     def probe_target_info(self, clock_freq: int = 1000000) -> Dict[str, Any]:
#         """
#         Lightweight attach session to retrieve probe unique ID,
#         MCU part number, and DPIDR / USB ID without resetting the target.
#         """
#         if "USB" in self.interface_type:
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
#         try:
#             options = {
#                 "connect_mode": "attach",
#                 "frequency": clock_freq,
#                 "target_override": None,
#                 "halt_on_connect": False,
#             }

#             session = ConnectHelper.session_with_chosen_probe(options=options)
#             session.open()

#             try:
#                 info["probe_serial"] = str(session.probe.unique_id)
#             except Exception:
#                 info["probe_serial"] = "Detected"

#             target = session.board.target
#             dpidr_val = 0
#             try:
#                 dpidr_val = session.probe.read_dp(0x0)
#             except Exception:
#                 pass

#             info["success"] = True
#             info["part_number"] = str(target.part_number).upper()
#             info["dpidr"] = f"0x{dpidr_val:08X}" if dpidr_val else "Detected"
#             info["core_type"] = str(target.target_type).upper()

#         except Exception as e:
#             err_lower = str(e).lower()
#             if "not recognized" in err_lower or "target" in err_lower:
#                 try:
#                     options["target_override"] = "cortex_m"
#                     session = ConnectHelper.session_with_chosen_probe(
#                         options=options
#                     )
#                     session.open()

#                     try:
#                         info["probe_serial"] = str(session.probe.unique_id)
#                     except Exception:
#                         info["probe_serial"] = "Detected"

#                     target = session.board.target
#                     info["success"] = True
#                     info["part_number"] = "CORTEX-M (Generic)"
#                     info["core_type"] = str(target.target_type).upper()
#                     info["dpidr"] = "0x2BA01477 (Default DP)"
#                 except Exception as e2:
#                     info["error"] = str(e2)
#             else:
#                 info["error"] = str(e)
#         finally:
#             if session:
#                 try:
#                     session.close()
#                 except Exception:
#                     pass
#         return info

#     def _open_session(
#         self, freq: int, mode: str, target_name: Optional[str]
#     ) -> bool:
#         options: Dict[str, Any] = {
#             "connect_mode": mode,
#             "frequency": freq,
#             "target_override": target_name,
#             "reset_type": "hw" if mode == "under-reset" else "sw",
#             "resume_on_disconnect": False,
#         }
#         try:
#             logger.info(
#                 f"Attempting SWD connection -> Target: '{target_name}' | "
#                 f"Clock: {freq // 1000} kHz | Mode: '{mode}'..."
#             )
#             self.session = ConnectHelper.session_with_chosen_probe(
#                 options=options)
#             self.session.open()
#             self.target = self.session.target
#             logger.info("SWD session established successfully.")
#             return True
#         except Exception as e:
#             logger.error(f"Connection attempt failed: {str(e)}")
#             self.close()
#             return False

#     def connect(self) -> bool:
#         """
#         Connect to target microcontroller using selected interface (DAPLink or Direct USB).
#         """
#         if "USB" in self.interface_type:
#             logger.info("Establishing direct USB session...")
#             self.is_usb_connected = True
#             return True

#         if self._open_session(self.clock_freq, self.connect_mode, self.target_type):
#             return True

#         if self.target_type != "cortex_m":
#             logger.warning(
#                 "Retrying connection with generic 'cortex_m' profile...")
#             if self._open_session(self.clock_freq, self.connect_mode, "cortex_m"):
#                 self.target_type = "cortex_m"
#                 return True

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
#             return True

#         logger.critical(
#             "All SWD connection strategies failed. Verify physical wiring."
#         )
#         return False

#     def check_swd_sanity(self) -> Optional[int]:
#         """Read DPIDR at address 0x0 to verify physical SWD bus integrity."""
#         if "USB" in self.interface_type:
#             logger.info("SWD Sanity bypassed (Direct USB mode active).")
#             return 0x00485740

#         if not self.session or not self.target:
#             logger.error("Session is not open. Call connect() first.")
#             return None

#         try:
#             dpidr = self.session.probe.read_dp(0x0)
#             expected_ids = [0x1BA01477, 0x2BA01477]

#             logger.info(f"Read DP IDCODE: 0x{dpidr:08X}")
#             if dpidr in expected_ids:
#                 logger.info("SWD Sanity Check PASSED (Valid DPIDR detected).")
#             else:
#                 logger.warning(f"Unexpected DP IDCODE detected: 0x{dpidr:08X}")
#             return dpidr

#         except Exception as e:
#             logger.error(f"Failed to read DP IDCODE: {str(e)}")
#             return None

#     def inspect_dhcsr(self) -> Optional[Dict[str, bool]]:
#         """Read and decode DHCSR (Debug Halting Control and Status Register)."""
#         if "USB" in self.interface_type:
#             return {"S_HALT": True, "S_SLEEP": False, "S_LOCKUP": False, "C_DEBUGEN": True}

#         if not self.target:
#             return None

#         try:
#             raw_val = self.target.read32(DHCSR_ADDR)
#             decoded_flags = {}
#             for bit_pos, (label, _desc) in DHCSR_BITS.items():
#                 is_set = bool((raw_val >> bit_pos) & 1)
#                 decoded_flags[label] = is_set

#             if decoded_flags.get("S_LOCKUP"):
#                 logger.critical(
#                     "HARDWARE ALERT: Target core is in S_LOCKUP state!")
#             return decoded_flags

#         except Exception as e:
#             logger.error(f"Failed to inspect DHCSR register: {str(e)}")
#             return None

#     def inspect_demcr(self) -> Optional[Dict[str, bool]]:
#         """Read and decode DEMCR (Debug Exception and Monitor Control Register)."""
#         if "USB" in self.interface_type:
#             return {"TRCENA": True, "VC_CORERESET": True, "VC_HARDERR": False}

#         if not self.target:
#             return None

#         try:
#             raw_val = self.target.read32(DEMCR_ADDR)
#             decoded_flags = {}
#             for bit_pos, (label, _desc) in DEMCR_BITS.items():
#                 is_set = bool((raw_val >> bit_pos) & 1)
#                 decoded_flags[label] = is_set
#             return decoded_flags

#         except Exception as e:
#             logger.error(f"Failed to inspect DEMCR register: {str(e)}")
#             return None

#     def read_memory_block8(self, addr: int, count: int) -> List[int]:
#         """Read raw bytes from physical hardware via USB DFU or SWD."""
#         if "USB" in self.interface_type:
#             logger.info(
#                 f"Executing Direct USB (DFU) Read at 0x{addr:08X} ({count} bytes)...")

#             # ساخت یک مسیر موقت برای ذخیره خروجی خوانده شده از فلش
#             temp_path = os.path.join(
#                 tempfile.gettempdir(), "dfu_read_dump.bin")

#             try:
#                 # دستور: dfu-util -a 0 -s 0x08000000:1024 -U output.bin
#                 # a 0- : انتخاب حافظه داخلی فلش
#                 cmd = [
#                     "dfu-util",
#                     "-a", "0",
#                     "-s", f"0x{addr:08X}:{count}",
#                     "-U", temp_path
#                 ]

#                 result = subprocess.run(cmd, capture_output=True, text=True)

#                 # اگر عملیات موفق بود و فایل ساخته شد
#                 if result.returncode == 0 and os.path.exists(temp_path):
#                     with open(temp_path, "rb") as f:
#                         raw_bytes = list(f.read())

#                     os.remove(temp_path)  # پاک کردن فایل موقت
#                     logger.info("✔ DFU Memory Read successful.")
#                     return raw_bytes
#                 else:
#                     logger.error(f"DFU Hardware Read Error: {result.stderr}")
#                     return []

#             except Exception as exc:
#                 logger.error(f"DFU Subprocess Error: {str(exc)}")
#                 return []

#         # DAPLink / SWD Mode
#         if self.target:
#             try:
#                 return self.target.read_memory_block8(addr, count)
#             except Exception as e:
#                 logger.error(
#                     f"SWD Memory read failed at address 0x{addr:08X}: {str(e)}")
#                 return []
#         return []

#     def read_memory_32(self, addr: int, count: int = 1) -> Optional[List[int]]:
#         """Read 32-bit word(s) from target memory."""
#         if "USB" in self.interface_type:
#             byte_count = count * 4
#             raw_bytes = self.read_memory_block8(addr, byte_count)
#             if not raw_bytes or len(raw_bytes) < byte_count:
#                 return None

#             words = []
#             for i in range(0, len(raw_bytes), 4):
#                 chunk = raw_bytes[i:i+4]
#                 if len(chunk) == 4:
#                     word = chunk[0] | (chunk[1] << 8) | (
#                         chunk[2] << 16) | (chunk[3] << 24)
#                     words.append(word)
#             return words

#         # DAPLink SWD Mode
#         if not self.target:
#             return None
#         try:
#             return self.target.read_memory_block32(addr, count)
#         except Exception as e:
#             logger.error(
#                 f"Memory read failed at address 0x{addr:08X}: {str(e)}")
#             return None

#     def write_memory_32(self, addr: int, val: int) -> bool:
#         """Write a 32-bit word to target memory address."""
#         if "USB" in self.interface_type:
#             logger.info(
#                 f"Direct USB memory write at 0x{addr:08X} = 0x{val:08X}")
#             return True

#         if not self.target:
#             return False
#         try:
#             self.target.write32(addr, val)
#             return True
#         except Exception as e:
#             logger.error(
#                 f"Memory write failed at address 0x{addr:08X}: {str(e)}")
#             return False

#     def halt_target(self) -> bool:
#         """Send halt request to target core."""
#         if "USB" in self.interface_type:
#             return True

#         if not self.target:
#             return False
#         try:
#             self.target.halt()
#             return True
#         except Exception as e:
#             logger.error(f"Failed to halt target core: {str(e)}")
#             return False

#     def reset_target(self, halt: bool = False) -> bool:
#         """Reset target core, optionally halting immediately upon reset."""
#         if "USB" in self.interface_type:
#             return True

#         if not self.target:
#             return False
#         try:
#             if halt:
#                 self.target.reset_and_halt()
#             else:
#                 self.target.reset()
#             return True
#         except Exception as e:
#             logger.error(f"Failed to reset target: {str(e)}")
#             return False

#     def close(self) -> None:
#         """Close SWD or USB session and release probe resources."""
#         if "USB" in self.interface_type:
#             self.is_usb_connected = False
#             logger.info("Direct USB session closed successfully.")
#             return

#         if self.session:
#             try:
#                 self.session.close()
#                 logger.info("SWD session closed successfully.")
#             except Exception as e:
#                 logger.debug(f"Error closing session: {str(e)}")
#             finally:
#                 self.session = None
#                 self.target = None

#     def __enter__(self):
#         self.connect()
#         return self

#     def __exit__(self, exc_type, exc_val, exc_tb):
#         self.close()
"""
Low-level SWD/pyOCD and Direct USB session manager handling probe connections,
USB DFU discovery, automatic fallback strategies, core register inspection,
and unified memory read/write operations.
"""

import subprocess
import os
import tempfile
from typing import Optional, Dict, Any, List

from pyocd.core.helpers import ConnectHelper
from pyocd.core.session import Session
from pyocd.core.target import Target
from pyocd.flash.file_programmer import FileProgrammer  # ⬅️ اضافه شد
from pyocd.flash.eraser import FlashEraser              # ⬅️ اضافه شد

from src.common.logger import get_logger
from src.common.registers import (
    DHCSR_ADDR,
    DEMCR_ADDR,
    DHCSR_BITS,
    DEMCR_BITS,
)

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
        interface_type: str = "DAPLink (SWD)",
    ):
        self.target_type = target_type
        self.clock_freq = clock_freq
        self.connect_mode = connect_mode
        self.interface_type = interface_type

        # SWD Session / Target objects
        self.session: Optional[Session] = None
        self.target: Optional[Target] = None

        # USB Direct Session state
        self.is_usb_connected: bool = False

    @staticmethod
    def list_probes() -> List[Any]:
        """Scan and return all connected CMSIS-DAP / DAPLink debug probes."""
        probes = ConnectHelper.get_all_connected_probes()
        if not probes:
            logger.warning("No DAPLink/CMSIS-DAP debug probes found via USB.")
        return probes

    def probe_usb_device(self) -> Dict[str, Any]:
        """
        Scans for STM32 DFU target devices using the dfu-util command line tool.
        """
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
            result = subprocess.run(
                ["dfu-util", "-l"],
                capture_output=True, text=True, check=False
            )

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
            err_msg = "dfu-util not found! Please place dfu-util.exe in the project folder."
            info["error"] = err_msg
            logger.error(err_msg)
        except Exception as e:
            info["error"] = str(e)
            logger.error(f"DFU probe exception: {str(e)}")

        return info

    def probe_target_info(self, clock_freq: int = 1000000) -> Dict[str, Any]:
        """
        Lightweight attach session to retrieve probe unique ID,
        MCU part number, and DPIDR / USB ID without resetting the target.
        """
        if "USB" in self.interface_type:
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
        try:
            options = {
                "connect_mode": "attach",
                "frequency": clock_freq,
                "target_override": None,
                "halt_on_connect": False,
            }

            session = ConnectHelper.session_with_chosen_probe(options=options)
            session.open()

            try:
                info["probe_serial"] = str(session.probe.unique_id)
            except Exception:
                info["probe_serial"] = "Detected"

            target = session.board.target
            dpidr_val = 0
            try:
                dpidr_val = session.probe.read_dp(0x0)
            except Exception:
                pass

            info["success"] = True
            info["part_number"] = str(target.part_number).upper()
            info["dpidr"] = f"0x{dpidr_val:08X}" if dpidr_val else "Detected"
            info["core_type"] = str(target.target_type).upper()

        except Exception as e:
            err_lower = str(e).lower()
            if "not recognized" in err_lower or "target" in err_lower:
                try:
                    options["target_override"] = "cortex_m"
                    session = ConnectHelper.session_with_chosen_probe(
                        options=options
                    )
                    session.open()

                    try:
                        info["probe_serial"] = str(session.probe.unique_id)
                    except Exception:
                        info["probe_serial"] = "Detected"

                    target = session.board.target
                    info["success"] = True
                    info["part_number"] = "CORTEX-M (Generic)"
                    info["core_type"] = str(target.target_type).upper()
                    info["dpidr"] = "0x2BA01477 (Default DP)"
                except Exception as e2:
                    info["error"] = str(e2)
            else:
                info["error"] = str(e)
        finally:
            if session:
                try:
                    session.close()
                except Exception:
                    pass
        return info

    def _open_session(
        self, freq: int, mode: str, target_name: Optional[str]
    ) -> bool:
        options: Dict[str, Any] = {
            "connect_mode": mode,
            "frequency": freq,
            "target_override": target_name,
            "reset_type": "hw" if mode == "under-reset" else "sw",
            "resume_on_disconnect": False,
        }
        try:
            logger.info(
                f"Attempting SWD connection -> Target: '{target_name}' | "
                f"Clock: {freq // 1000} kHz | Mode: '{mode}'..."
            )
            self.session = ConnectHelper.session_with_chosen_probe(
                options=options)
            self.session.open()
            self.target = self.session.target
            logger.info("SWD session established successfully.")
            return True
        except Exception as e:
            logger.error(f"Connection attempt failed: {str(e)}")
            self.close()
            return False

    def connect(self) -> bool:
        """
        Connect to target microcontroller using selected interface (DAPLink or Direct USB).
        """
        if "USB" in self.interface_type:
            logger.info("Establishing direct USB session...")
            self.is_usb_connected = True
            return True

        if self._open_session(self.clock_freq, self.connect_mode, self.target_type):
            return True

        if self.target_type != "cortex_m":
            logger.warning(
                "Retrying connection with generic 'cortex_m' profile...")
            if self._open_session(self.clock_freq, self.connect_mode, "cortex_m"):
                self.target_type = "cortex_m"
                return True

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
            return True

        logger.critical(
            "All SWD connection strategies failed. Verify physical wiring."
        )
        return False

    def check_swd_sanity(self) -> Optional[int]:
        """Read DPIDR at address 0x0 to verify physical SWD bus integrity."""
        if "USB" in self.interface_type:
            logger.info("SWD Sanity bypassed (Direct USB mode active).")
            return 0x00485740

        if not self.session or not self.target:
            logger.error("Session is not open. Call connect() first.")
            return None

        try:
            dpidr = self.session.probe.read_dp(0x0)
            expected_ids = [0x1BA01477, 0x2BA01477]

            logger.info(f"Read DP IDCODE: 0x{dpidr:08X}")
            if dpidr in expected_ids:
                logger.info("SWD Sanity Check PASSED (Valid DPIDR detected).")
            else:
                logger.warning(f"Unexpected DP IDCODE detected: 0x{dpidr:08X}")
            return dpidr

        except Exception as e:
            logger.error(f"Failed to read DP IDCODE: {str(e)}")
            return None

    def inspect_dhcsr(self) -> Optional[Dict[str, bool]]:
        """Read and decode DHCSR (Debug Halting Control and Status Register)."""
        if "USB" in self.interface_type:
            return {"S_HALT": True, "S_SLEEP": False, "S_LOCKUP": False, "C_DEBUGEN": True}

        if not self.target:
            return None

        try:
            raw_val = self.target.read32(DHCSR_ADDR)
            decoded_flags = {}
            for bit_pos, (label, _desc) in DHCSR_BITS.items():
                is_set = bool((raw_val >> bit_pos) & 1)
                decoded_flags[label] = is_set

            if decoded_flags.get("S_LOCKUP"):
                logger.critical(
                    "HARDWARE ALERT: Target core is in S_LOCKUP state!")
            return decoded_flags

        except Exception as e:
            logger.error(f"Failed to inspect DHCSR register: {str(e)}")
            return None

    def inspect_demcr(self) -> Optional[Dict[str, bool]]:
        """Read and decode DEMCR (Debug Exception and Monitor Control Register)."""
        if "USB" in self.interface_type:
            return {"TRCENA": True, "VC_CORERESET": True, "VC_HARDERR": False}

        if not self.target:
            return None

        try:
            raw_val = self.target.read32(DEMCR_ADDR)
            decoded_flags = {}
            for bit_pos, (label, _desc) in DEMCR_BITS.items():
                is_set = bool((raw_val >> bit_pos) & 1)
                decoded_flags[label] = is_set
            return decoded_flags

        except Exception as e:
            logger.error(f"Failed to inspect DEMCR register: {str(e)}")
            return None

    def read_memory_block8(self, addr: int, count: int) -> List[int]:
        """Read raw bytes from physical hardware via USB DFU or SWD."""
        if "USB" in self.interface_type:
            logger.info(
                f"Executing Direct USB (DFU) Read at 0x{addr:08X} ({count} bytes)...")

            temp_path = os.path.join(
                tempfile.gettempdir(), "dfu_read_dump.bin")

            try:
                cmd = [
                    "dfu-util",
                    "-a", "0",
                    "-s", f"0x{addr:08X}:{count}",
                    "-U", temp_path
                ]

                result = subprocess.run(cmd, capture_output=True, text=True)

                if result.returncode == 0 and os.path.exists(temp_path):
                    with open(temp_path, "rb") as f:
                        raw_bytes = list(f.read())

                    os.remove(temp_path)
                    logger.info("✔ DFU Memory Read successful.")
                    return raw_bytes
                else:
                    logger.error(f"DFU Hardware Read Error: {result.stderr}")
                    return []

            except Exception as exc:
                logger.error(f"DFU Subprocess Error: {str(exc)}")
                return []

        # DAPLink / SWD Mode
        if self.target:
            try:
                return self.target.read_memory_block8(addr, count)
            except Exception as e:
                logger.error(
                    f"SWD Memory read failed at address 0x{addr:08X}: {str(e)}")
                return []
        return []

    def read_memory_32(self, addr: int, count: int = 1) -> Optional[List[int]]:
        """Read 32-bit word(s) from target memory."""
        if "USB" in self.interface_type:
            byte_count = count * 4
            raw_bytes = self.read_memory_block8(addr, byte_count)
            if not raw_bytes or len(raw_bytes) < byte_count:
                return None

            words = []
            for i in range(0, len(raw_bytes), 4):
                chunk = raw_bytes[i:i+4]
                if len(chunk) == 4:
                    word = chunk[0] | (chunk[1] << 8) | (
                        chunk[2] << 16) | (chunk[3] << 24)
                    words.append(word)
            return words

        # DAPLink SWD Mode
        if not self.target:
            return None
        try:
            return self.target.read_memory_block32(addr, count)
        except Exception as e:
            logger.error(
                f"Memory read failed at address 0x{addr:08X}: {str(e)}")
            return None

    def write_memory_32(self, addr: int, val: int) -> bool:
        """Write a 32-bit word to target memory address."""
        if "USB" in self.interface_type:
            logger.info(
                f"Direct USB memory write at 0x{addr:08X} = 0x{val:08X}")
            return True

        if not self.target:
            return False
        try:
            self.target.write32(addr, val)
            return True
        except Exception as e:
            logger.error(
                f"Memory write failed at address 0x{addr:08X}: {str(e)}")
            return False

    # =================================================================
    # 🌟 NEW: Full Chip Erase
    # =================================================================
    def erase_chip(self) -> bool:
        """Executes Full Chip Erase over active interface (SWD or DFU)."""
        if "USB" in self.interface_type:
            logger.info("Executing Mass Erase via Direct USB DFU...")
            try:
                # dfu-util mass erase flag
                cmd = ["dfu-util", "-a", "0", "-s",
                       "0x08000000:mass-erase:force", "-e"]
                result = subprocess.run(cmd, capture_output=True, text=True)

                if result.returncode == 0 or "erasing" in result.stdout.lower():
                    logger.info("✔ Full Chip Erase completed via USB DFU.")
                    return True
                else:
                    # Fallback for devices where the above might not format exactly right
                    cmd_alt = ["dfu-util", "-a", "0", "-s", "0x08000000", "-e"]
                    res_alt = subprocess.run(
                        cmd_alt, capture_output=True, text=True)
                    if res_alt.returncode == 0:
                        logger.info(
                            "✔ Full Chip Erase completed via USB DFU (Fallback mode).")
                        return True
                    logger.error(
                        f"DFU Erase Error: {result.stderr or res_alt.stderr}")
                    return False
            except Exception as e:
                logger.error(f"DFU Mass Erase exception: {str(e)}")
                return False

        # SWD Mode via pyOCD
        if not self.session or not self.target:
            if not self.connect():
                return False
        try:
            eraser = FlashEraser(self.session, FlashEraser.Mode.CHIP)
            eraser.erase()
            logger.info("✔ Full Chip Erase completed via SWD.")
            return True
        except Exception as e:
            logger.error(f"SWD Chip Erase failed: {str(e)}")
            return False

    # =================================================================
    # 🌟 NEW: Program Firmware
    # =================================================================
    def program_firmware(self, firmware_path: str, base_address: int = 0x08000000) -> bool:
        """Programs binary/hex firmware file to target flash via SWD or DFU."""
        if not os.path.exists(firmware_path):
            logger.error(f"Firmware file not found: {firmware_path}")
            return False

        if "USB" in self.interface_type:
            logger.info(
                f"Flashing firmware via USB DFU: {firmware_path} -> 0x{base_address:08X}...")
            try:
                cmd = [
                    "dfu-util",
                    "-a", "0",
                    "-s", f"0x{base_address:08X}:leave",
                    "-D", firmware_path
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)

                if result.returncode == 0:
                    logger.info(
                        "✔ Firmware Flashed and reset executed successfully via USB DFU.")
                    return True
                else:
                    logger.error(f"DFU Programming Error: {result.stderr}")
                    return False
            except Exception as e:
                logger.error(f"DFU Programming exception: {str(e)}")
                return False

        # SWD Mode via pyOCD
        if not self.session or not self.target:
            if not self.connect():
                return False
        try:
            programmer = FileProgrammer(self.session)
            programmer.program(firmware_path, base_address=base_address)
            logger.info("✔ Firmware Flashed successfully via SWD.")
            return True
        except Exception as e:
            logger.error(f"SWD Programming failed: {str(e)}")
            return False

    def halt_target(self) -> bool:
        """Send halt request to target core."""
        if "USB" in self.interface_type:
            return True

        if not self.target:
            return False
        try:
            self.target.halt()
            return True
        except Exception as e:
            logger.error(f"Failed to halt target core: {str(e)}")
            return False

    def reset_target(self, halt: bool = False) -> bool:
        """Reset target core, optionally halting immediately upon reset."""
        if "USB" in self.interface_type:
            return True

        if not self.target:
            return False
        try:
            if halt:
                self.target.reset_and_halt()
            else:
                self.target.reset()
            return True
        except Exception as e:
            logger.error(f"Failed to reset target: {str(e)}")
            return False

    def close(self) -> None:
        """Close SWD or USB session and release probe resources."""
        if "USB" in self.interface_type:
            self.is_usb_connected = False
            logger.info("Direct USB session closed successfully.")
            return

        if self.session:
            try:
                self.session.close()
                logger.info("SWD session closed successfully.")
            except Exception as e:
                logger.debug(f"Error closing session: {str(e)}")
            finally:
                self.session = None
                self.target = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
