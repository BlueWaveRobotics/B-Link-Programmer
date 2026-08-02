import logging
from typing import Optional, Dict, Any, List

# pyOCD Low-level libraries
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
    Includes hardware registers inspection, core register dumping, and memory R/W.
    """

    # Cortex-M3 Debug Register Addresses
    DHCSR_ADDR = 0xE000EDF0
    DEMCR_ADDR = 0xE000EDFC

    DHCSR_BITS = {
        0:  ("C_DEBUGEN",   "Halting debug enabled"),
        1:  ("C_HALT",      "Halt request"),
        2:  ("C_STEP",      "Step request"),
        16: ("S_REGRDY",    "Register Read/Write on Debug Core Register interface available"),
        17: ("S_HALT",      "The core is in halted state"),
        18: ("S_SLEEP",     "The core is sleeping"),
        19: ("S_LOCKUP",    "CRITICAL: The core is in LOCKUP state!"),
        24: ("S_RETIRE_ST", "An instruction has completed execution"),
        25: ("S_RESET_ST",  "The core has been reset since the last read"),
    }

    DEMCR_BITS = {
        0:  ("VC_CORERESET", "Reset Vector Catch: Halt on Core Reset"),
        4:  ("VC_MMERR",     "Debug trap on Memory Management faults"),
        5:  ("VC_NOCPERR",   "Debug trap on Usage Fault (No Coprocessor)"),
        6:  ("VC_CHKERR",    "Debug trap on Usage Fault (Checking Error)"),
        7:  ("VC_STATERR",   "Debug trap on Usage Fault (State Error)"),
        8:  ("VC_BUSERR",    "Debug trap on Bus Fault"),
        9:  ("VC_INTERR",    "Debug trap on Interrupt/Exception service errors"),
        10: ("VC_HARDERR",   "Debug trap on Hard Fault"),
        24: ("TRCENA",       "Global enable for DWT and ITM tracing units"),
    }

    def __init__(
        self,
        target_type: Optional[str] = None,
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
        """Connect to target with automatic fallback strategies."""
        if self._open_session(self.clock_freq, self.connect_mode, self.target_type):
            return True

        if self.target_type != "cortex_m":
            logger.warning(
                "Retrying with generic 'cortex_m' target profile...")
            if self._open_session(self.clock_freq, self.connect_mode, "cortex_m"):
                self.target_type = "cortex_m"
                return True

        logger.warning(
            "SWD connection error detected. "
            "Switching to Diagnostics Fallback: 50 kHz clock & 'attach' mode..."
        )
        fallback_target = "cortex_m" if self.target_type == "cortex_m" else self.target_type
        if self._open_session(50000, "attach", fallback_target):
            self.clock_freq = 50000
            self.connect_mode = "attach"
            self.target_type = fallback_target
            return True

        logger.critical(
            "ALL connection strategies failed. Please check physical SWD wiring.")
        return False

    def check_swd_sanity(self) -> Optional[int]:
        """Read DPIDR at address 0x0 to verify physical SWD integrity."""
        if not self.session or not self.target:
            logger.error("Session not open. Call connect() first.")
            return None

        try:
            # Fixed syntax for pyOCD newer releases (no 'addr_index' keyword argument)
            dpidr = self.session.probe.read_dp(0x0)
            expected_ids = [0x1BA01477, 0x2BA01477]

            logger.info(f"Read DP IDCODE: 0x{dpidr:08X}")
            if dpidr in expected_ids:
                logger.info(
                    "✔ SWD Sanity Check PASSED (Valid Cortex-M3 DPIDR detected).")
            else:
                logger.warning(f"⚠ Unexpected DP IDCODE (0x{dpidr:08X}).")
            return dpidr

        except Exception as e:
            logger.error(f"Failed to read DP IDCODE: {str(e)}")
            return None

    def inspect_dhcsr(self) -> Optional[Dict[str, bool]]:
        """Read and decode DHCSR (Debug Halting Control and Status Register)."""
        if not self.target:
            return None

        try:
            raw_val = self.target.read32(self.DHCSR_ADDR)
            decoded_flags = {}
            print("\n" + "="*70)
            print(f"  DHCSR Inspection (Raw: 0x{raw_val:08X})")
            print("="*70)

            for bit_pos, (label, desc) in self.DHCSR_BITS.items():
                is_set = bool((raw_val >> bit_pos) & 1)
                decoded_flags[label] = is_set
                status_icon = "[X] SET    " if is_set else "[ ] UNSET  "
                print(
                    f"  BIT {bit_pos:02d} | {label:<12} : {status_icon} -> {desc}")
            print("-" * 70)

            if decoded_flags.get("S_LOCKUP"):
                logger.critical("HARDWARE ALERT: Core is in S_LOCKUP state!")
            return decoded_flags

        except Exception as e:
            logger.error(f"Failed to inspect DHCSR register: {str(e)}")
            return None

    def inspect_demcr(self) -> Optional[Dict[str, bool]]:
        """
        Read and decode DEMCR (Debug Exception and Monitor Control Register).
        Shows which exception traps (e.g. HardFault, Core Reset) will halt the core.
        """
        if not self.target:
            return None

        try:
            raw_val = self.target.read32(self.DEMCR_ADDR)
            decoded_flags = {}
            print("\n" + "="*70)
            print(f"  DEMCR Inspection (Raw: 0x{raw_val:08X})")
            print("="*70)

            for bit_pos, (label, desc) in self.DEMCR_BITS.items():
                is_set = bool((raw_val >> bit_pos) & 1)
                decoded_flags[label] = is_set
                status_icon = "[X] TRAP ON " if is_set else "[ ] TRAP OFF"
                print(
                    f"  BIT {bit_pos:02d} | {label:<14} : {status_icon} -> {desc}")
            print("-" * 70)
            return decoded_flags

        except Exception as e:
            logger.error(f"Failed to inspect DEMCR register: {str(e)}")
            return None

    def dump_core_registers(self) -> Optional[Dict[str, int]]:
        """
        Dump standard ARM Cortex-M3 core registers (R0-R12, SP, LR, PC, xPSR).
        Requires target core to be HALTED first.
        """
        if not self.target or not self.target.is_halted():
            logger.warning(
                "Cannot read core registers: Target core must be halted first!")
            return None

        reg_names = [
            "r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7",
            "r8", "r9", "r10", "r11", "r12", "sp", "lr", "pc", "xpsr"
        ]

        try:
            logger.info("Reading ARM Cortex-M3 Core Registers...")
            regs = self.target.read_core_registers_raw(reg_names)
            reg_dict = dict(zip(reg_names, regs))

            print("\n" + "="*70)
            print("  ARM Cortex-M3 Core Register Dump (Halted State)")
            print("="*70)
            for i in range(0, len(reg_names) - 1, 4):
                row_items = []
                for r in reg_names[i:i+4]:
                    row_items.append(f"{r.upper():<4}: 0x{reg_dict[r]:08X}")
                print("  " + "   |   ".join(row_items))
            print(
                f"  {reg_names[-1].upper():<4}: 0x{reg_dict[reg_names[-1]]:08X}")
            print("-" * 70)
            return reg_dict

        except Exception as e:
            logger.error(f"Failed to dump core registers: {str(e)}")
            return None

    def read_memory_32(self, addr: int, count: int = 1) -> Optional[List[int]]:
        """Read 32-bit word(s) from target memory address (Flash, RAM, or Peripherals)."""
        if not self.target:
            return None
        try:
            values = self.target.read_memory_block32(addr, count)
            for idx, val in enumerate(values):
                logger.info(
                    f"Memory Read [0x{(addr + idx*4):08X}] -> 0x{val:08X}")
            return values
        except Exception as e:
            logger.error(
                f"Memory Read failed at address 0x{addr:08X}: {str(e)}")
            return None

    def write_memory_32(self, addr: int, val: int) -> bool:
        """Write a 32-bit word to target memory address."""
        if not self.target:
            return False
        try:
            self.target.write32(addr, val)
            logger.info(f"Memory Write [0x{addr:08X}] <- 0x{val:08X}")
            return True
        except Exception as e:
            logger.error(
                f"Memory Write failed at address 0x{addr:08X}: {str(e)}")
            return False

    def halt(self) -> bool:
        """Send halt request to target MCU."""
        try:
            logger.info("Sending halt request to target core...")
            self.target.halt()
            logger.info("✔ Target core halted successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to halt target core: {str(e)}")
            return False

    def disconnect(self) -> None:
        """Close SWD session and release probe resources."""
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


# =====================================================================
# CLI Prototype Execution - Phase 2: Diagnostic Suite & Register Dump
# =====================================================================
if __name__ == "__main__":
    print("=== DAPLink Controller Prototype Test (Phase 2) ===\n")

    debugger = DAPLinkController(
        target_type="stm32f103c8",
        clock_freq=100000,
        connect_mode="under-reset"
    )

    if debugger.connect():
        try:
            # 1. Physical SWD sanity check
            debugger.check_swd_sanity()

            # 2. Inspect exception traps (DEMCR)
            debugger.inspect_demcr()

            # 3. Halt the target to allow core register reads
            if debugger.halt():
                # 4. Dump R0-R12, SP, LR, PC, xPSR
                debugger.dump_core_registers()

                # 5. Read STM32 Flash start address (0x08000000 - Initial SP & Reset Vector)
                logger.info("Reading Vector Table from Flash Memory:")
                debugger.read_memory_32(0x08000000, count=2)

        finally:
            debugger.disconnect()
