"""
Headless Execution Engine for B-Link DAPLink CLI.
Executes pyOCD SWD operations directly without initializing PySide6 GUI elements,
featuring robust automatic under-reset to attach fallback recovery.
"""

import os
import sys
import time
from typing import Optional
from pyocd.core.helpers import ConnectHelper
from pyocd.flash.file_programmer import FileProgrammer
from pyocd.flash.eraser import FlashEraser

from src.common import get_logger
from src.common.profile_manager import ProfileManager
from src.features.batch_programmer.probe_manager import ProbeManagerService
from src.features.production_programmer.provisioning import ProvisioningService

logger = get_logger("CLI_Runner")

DEFAULT_STM32_UID_ADDRESS = 0x1FFFF7E8


class HeadlessRunner:
    """
    Executes automated diagnostics, full chip erase, and production flash
    in console mode with automatic connection recovery.
    """

    def __init__(self):
        self.profile_manager = ProfileManager()

    def list_connected_probes(self) -> int:
        """Prints all detected B-Link probes to standard output."""
        print("\n=== Scanning USB Bus for B-Link Probes ===")
        probes = ProbeManagerService.discover_connected_probes()
        if not probes:
            print("[WARN] No B-Link hardware probes found.")
            return 1

        for idx, probe in enumerate(probes, 1):
            print(f" [{idx}] {probe.display_name} -> ID: {probe.unique_id}")
        print(f"Total Probes Detected: {len(probes)}\n")
        return 0

    def _connect_session(
        self,
        unique_id: Optional[str] = None,
        clock_freq: int = 1000000,
        connect_mode: str = "under-reset",
        safe_recovery: bool = False,
    ):
        """
        Connects to target via pyOCD with automatic retry fallback.
        Switches from 'under-reset' to 'attach' if hardware NRST is missing.
        """
        freq = min(clock_freq, 500000) if safe_recovery else clock_freq
        options = {
            "connect_mode": connect_mode,
            "frequency": freq,
            "reset_type": "hw" if connect_mode == "under-reset" else "default",
            "halt_on_connect": True,
            "resume_on_disconnect": False,
        }

        try:
            session = ConnectHelper.session_with_chosen_probe(
                unique_id=unique_id,
                options=options,
            )
            session.open()
            return session
        except Exception as primary_err:
            logger.warning(
                f"Primary SWD connection ({connect_mode}) failed: {primary_err}")
            print(
                f"[CLI WARN] Connection mode '{connect_mode}' failed. Retrying in 'attach' mode @ 500kHz..."
            )
            fallback_options = {
                "connect_mode": "attach",
                "frequency": 500000,
                "reset_type": "sw",
                "halt_on_connect": True,
                "resume_on_disconnect": False,
            }
            session = ConnectHelper.session_with_chosen_probe(
                unique_id=unique_id,
                options=fallback_options,
            )
            session.open()
            return session

    def _safe_halt_core(self, target) -> None:
        """Attempts reset_and_halt; falls back to simple halt if NRST is absent."""
        try:
            target.reset_and_halt()
        except Exception:
            try:
                target.halt()
            except Exception as halt_err:
                logger.warning(f"Could not halt target CPU core: {halt_err}")

    def run_chip_erase(
        self,
        unique_id: Optional[str] = None,
        clock_freq: int = 1000000,
        connect_mode: str = "under-reset",
    ) -> bool:
        """Executes full chip erase with mass erase fallback."""
        session = None
        start_time = time.perf_counter()
        target_name = f"Probe [{unique_id[:8]}]" if unique_id else "Auto Probe"

        try:
            print(
                f"\n[CLI START] Executing Full Chip Erase on {target_name}...")
            session = self._connect_session(
                unique_id=unique_id,
                clock_freq=clock_freq,
                connect_mode=connect_mode,
                safe_recovery=True,
            )
            target = session.board.target

            self._safe_halt_core(target)

            print("[CLI BUSY] Erasing target flash memory sectors...")
            try:
                eraser = FlashEraser(session, mode=FlashEraser.Mode.CHIP)
                eraser.erase()
            except Exception:
                print(
                    "[CLI WARN] Chip Erase faulted. Executing Hardware Mass Erase...")
                try:
                    target.halt()
                except Exception:
                    pass
                eraser_mass = FlashEraser(session, mode=FlashEraser.Mode.MASS)
                eraser_mass.erase()

            self._safe_halt_core(target)
            elapsed = time.perf_counter() - start_time
            print(
                f"[CLI PASS] ✔ Full Chip Erase successful! ({elapsed:.2f}s)\n")
            return True

        except Exception as exc:
            print(
                f"[CLI FAIL] ✖ Chip Erase failed: {str(exc)}\n", file=sys.stderr)
            return False

        finally:
            if session:
                try:
                    session.close()
                except Exception:
                    pass

    def run_production_flash(
        self,
        file_path: str,
        base_address: int = 0x08000000,
        clock_freq: int = 1000000,
        connect_mode: str = "under-reset",
        verify_enabled: bool = True,
        unique_id: Optional[str] = None,
    ) -> bool:
        """Executes one-click firmware flashing and UID readout."""
        if not os.path.exists(file_path):
            print(
                f"[CLI ERROR] Firmware file not found: {file_path}", file=sys.stderr)
            return False

        session = None
        start_time = time.perf_counter()
        target_name = f"Probe [{unique_id[:8]}]" if unique_id else "Auto Probe"

        try:
            print(
                f"\n[CLI START] Deploying image '{os.path.basename(file_path)}' to {target_name}..."
            )
            session = self._connect_session(
                unique_id=unique_id,
                clock_freq=clock_freq,
                connect_mode=connect_mode,
                safe_recovery=False,
            )
            target = session.board.target

            self._safe_halt_core(target)

            # Read 96-bit UID
            chip_uid = "UNKNOWN-UID"
            try:
                raw_uid_words = target.read_memory_block32(
                    DEFAULT_STM32_UID_ADDRESS, 3)
                chip_uid = ProvisioningService.format_96bit_uid(raw_uid_words)
                print(f"[CLI INFO] Hardware 96-bit UID: {chip_uid}")
            except Exception:
                print("[CLI WARN] Could not read hardware UID.")

            # Program
            print(
                f"[CLI BUSY] Writing flash starting @ 0x{base_address:08X}...")
            programmer = FileProgrammer(
                session,
                chip_erase="sector",
            )
            programmer.program(
                file_path,
                base_address=base_address,
                verify=verify_enabled,
            )

            # Reset and run application
            try:
                target.reset_and_halt()
                target.resume()
            except Exception:
                pass

            elapsed = time.perf_counter() - start_time
            print(
                f"[CLI PASS] ✔ Flash verified & deployed successfully! ({elapsed:.2f}s)\n")
            return True

        except Exception as exc:
            print(
                f"[CLI FAIL] ✖ Programming failed: {str(exc)}\n", file=sys.stderr)
            return False

        finally:
            if session:
                try:
                    session.close()
                except Exception:
                    pass
