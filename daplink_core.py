import sys
import logging
from typing import Optional, Dict, Any
from pyocd.core.helpers import ConnectHelper
from pyocd.core.session import Session
from pyocd.core.target import Target

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("DAPLinkCore")


class DAPLinkController:
    """
    DAPLink hardware controller for STM32 targets and SWD low-level diagnostics.
    Includes automated fallback strategies for Bit-Banged DAPLink hardware.
    """

    DHCSR_ADDR = 0xE000EDF0

    DHCSR_BITS = {
        0:  ("C_DEBUGEN",   "Halting debug enabled"),
        1:  ("C_HALT",      "Halt request"),
        2:  ("C_STEP",      "Step request"),
        16: ("S_REGRDY",    "Register Read/Write on the Debug Core Register interface is available"),
        17: ("S_HALT",      "The core is in halted state"),
        18: ("S_SLEEP",     "The core is sleeping"),
        19: ("S_LOCKUP",    "CRITICAL: The core is in LOCKUP state!"),
        24: ("S_RETIRE_ST", "An instruction has completed execution"),
        25: ("S_RESET_ST",  "The core has been reset since the last read"),
    }

    def __init__(
        self,
        target_type: str = "stm32f103c8",
        clock_freq: int = 100000,
        connect_mode: str = "under-reset"
    ):
        self.target_type = target_type
        self.clock_freq = clock_freq
        self.connect_mode = connect_mode
        self.session: Optional[Session] = None
        self.target: Optional[Target] = None

    @staticmethod
    def list_probes() -> None:
        """Scan and log all connected CMSIS-DAP / DAPLink debug probes."""
        probes = ConnectHelper.get_all_connected_probes()
        if not probes:
            logger.warning("No DAPLink/CMSIS-DAP debug probes found via USB.")
            return

        logger.info(f"Found {len(probes)} connected probe(s):")
        for idx, probe in enumerate(probes):
            logger.info(
                f"  [{idx+1}] Description: {probe.description} | "
                f"Unique ID: {probe.unique_id}"
            )

    def _open_session(self, freq: int, mode: str, target_name: str) -> bool:
        """Internal helper to attempt session opening with specific parameters."""
        options: Dict[str, Any] = {
            'connect_mode': mode,
            'frequency': freq,
            'target_override': target_name,
            'reset_type': 'hw' if mode == 'under-reset' else 'sw',
            'resume_on_disconnect': False
        }
        try:
            logger.info(
                f"Attempting connection -> Target: '{target_name}' | "
                f"Clock: {freq//1000} kHz | Mode: '{mode}'..."
            )
            self.session = ConnectHelper.session_with_chosen_probe(
                options=options)
            self.session.open()
            self.target = self.session.target
            logger.info("✔ SWD session established successfully!")
            return True
        except Exception as e:
            logger.error(f"Connection attempt failed: {str(e)}")
            if self.session:
                try:
                    self.session.close()
                except Exception:
                    pass
                self.session = None
                self.target = None
            return False

    def connect(self) -> bool:
        """
        Connect to target with automatic fallback for MCU target packs and SWD timing/reset issues.
        """
        # Attempt 1: Primary requested configuration
        if self._open_session(self.clock_freq, self.connect_mode, self.target_type):
            return True

        # Attempt 2: Switch to generic 'cortex_m' if STM32 pack failed
        if self.target_type != "cortex_m":
            logger.warning(
                "Retrying with generic 'cortex_m' target profile...")
            if self._open_session(self.clock_freq, self.connect_mode, "cortex_m"):
                self.target_type = "cortex_m"
                return True

        # Attempt 3: Diagnostics Fallback -> Lower speed (50 kHz) + 'attach' mode (ignore nRESET pin)
        logger.warning(
            "SWD 'No ACK' or Reset failure detected. "
            "Switching to Diagnostics Fallback: 50 kHz clock & 'attach' mode..."
        )
        fallback_target = "cortex_m" if self.target_type == "cortex_m" else self.target_type
        if self._open_session(50000, "attach", fallback_target):
            self.clock_freq = 50000
            self.connect_mode = "attach"
            self.target_type = fallback_target
            return True

        logger.critical(
            "ALL connection strategies failed. Please check:\n"
            "  1. SWDIO and SWCLK wiring/continuity to target MCU.\n"
            "  2. Target MCU power supply (3.3V) and shared GND.\n"
            "  3. nRESET line physical connection if using 'under-reset'."
        )
        return False

    def check_swd_sanity(self) -> Optional[int]:
        """Read DPIDR at address 0x0 to verify physical SWD integrity."""
        if not self.session or not self.target:
            logger.error("Session not open. Call connect() first.")
            return None

        try:
            dpidr = self.session.probe.read_dp(0x0, addr_index=0)
            expected_ids = [0x1BA01477, 0x2BA01477]

            logger.info(f"Read DP IDCODE: 0x{dpidr:08X}")
            if dpidr in expected_ids:
                logger.info(
                    "✔ SWD Sanity Check PASSED (Valid Cortex-M3 DPIDR detected).")
            else:
                logger.warning(
                    f"⚠ Unexpected DP IDCODE (0x{dpidr:08X}). "
                    "Expected standard STM32F103 value (0x1BA01477 or 0x2BA01477)."
                )
            return dpidr

        except Exception as e:
            logger.error(f"Failed to read DP IDCODE: {str(e)}")
            return None

    def inspect_dhcsr(self) -> Optional[Dict[str, bool]]:
        """Read and decode the DHCSR register to diagnose Halt/Reset failures."""
        if not self.target:
            logger.error("Target not available.")
            return None

        try:
            raw_val = self.target.read32(self.DHCSR_ADDR)
            logger.info(f"Raw DHCSR Value: 0x{raw_val:08X}")

            decoded_flags = {}
            print("\n" + "="*70)
            print("  DHCSR (Debug Halting Control and Status Register) Inspection")
            print("="*70)

            for bit_pos, (label, desc) in self.DHCSR_BITS.items():
                is_set = bool((raw_val >> bit_pos) & 1)
                decoded_flags[label] = is_set
                status_icon = "[X] SET    " if is_set else "[ ] UNSET  "
                print(
                    f"  BIT {bit_pos:02d} | {label:<12} : {status_icon} -> {desc}")
            print("-" * 70)

            if decoded_flags.get("S_LOCKUP"):
                logger.critical(
                    "HARDWARE ALERT: Core is in S_LOCKUP state! "
                    "Check for hard faults during startup, unstable power, or noisy nRESET line."
                )
            elif not decoded_flags.get("S_HALT"):
                logger.warning(
                    "NOTE: Core is currently NOT HALTED (executing code).")

            return decoded_flags

        except Exception as e:
            logger.error(f"Failed to inspect DHCSR register: {str(e)}")
            return None

    def halt(self) -> bool:
        """Send halt request to the target MCU."""
        try:
            logger.info("Sending halt request to target core...")
            self.target.halt()
            logger.info("✔ Target core halted successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to halt target core: {str(e)}")
            return False

    def disconnect(self) -> None:
        """Close SWD session and release USB probe resources."""
        if self.session:
            try:
                self.session.close()
                logger.info("SWD session closed successfully.")
            except Exception as e:
                logger.debug(f"Error while closing session: {str(e)}")
            finally:
                self.session = None
                self.target = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()


if __name__ == "__main__":
    print("=== DAPLink Controller Prototype Test (Phase 1) ===\n")

    DAPLinkController.list_probes()
    print()

    debugger = DAPLinkController(
        target_type="stm32f103c8",
        clock_freq=100000,
        connect_mode="under-reset"
    )

    if debugger.connect():
        try:
            debugger.check_swd_sanity()
            debugger.inspect_dhcsr()
            debugger.halt()
            debugger.inspect_dhcsr()
        finally:
            debugger.disconnect()
