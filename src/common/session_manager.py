"""
Low-level SWD/pyOCD session manager handling probe connections,
automatic fallback strategies, core register inspection, and memory operations.
"""

from typing import Optional, Dict, Any, List
from pyocd.core.helpers import ConnectHelper
from pyocd.core.session import Session
from pyocd.core.target import Target

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
    Manages physical SWD debug probe sessions with ARM Cortex-M microcontrollers.
    Supports dynamic clock speed adjustment, under-reset vs. attach modes,
    and fallback recovery for locked or unresponsive cores.
    """

    def __init__(
        self,
        target_type: Optional[str] = None,
        clock_freq: int = 100000,
        connect_mode: str = "under-reset",
    ):
        self.target_type = target_type
        self.clock_freq = clock_freq
        self.connect_mode = connect_mode
        self.session: Optional[Session] = None
        self.target: Optional[Target] = None

    @staticmethod
    def list_probes() -> List[Any]:
        """Scan and return all connected CMSIS-DAP / DAPLink debug probes."""
        probes = ConnectHelper.get_all_connected_probes()
        if not probes:
            logger.warning("No DAPLink/CMSIS-DAP debug probes found via USB.")
        return probes

    def probe_target_info(self, clock_freq: int = 1000000) -> Dict[str, Any]:
        """
        Lightweight attach session to retrieve probe unique ID,
        MCU part number, and DPIDR without resetting the target.
        """
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
        Connect to target microcontroller using automated fallback strategies:
        1. Configured user parameters.
        2. Generic 'cortex_m' fallback.
        3. Diagnostic 50 kHz 'attach' mode fallback.
        """
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

    def read_memory_32(self, addr: int, count: int = 1) -> Optional[List[int]]:
        """Read 32-bit word(s) from target memory (Flash, RAM, or Peripherals)."""
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
        if not self.target:
            return False
        try:
            self.target.write32(addr, val)
            return True
        except Exception as e:
            logger.error(
                f"Memory write failed at address 0x{addr:08X}: {str(e)}")
            return False

    def halt_target(self) -> bool:
        """Send halt request to target core."""
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
        """Close SWD session and release probe resources."""
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
