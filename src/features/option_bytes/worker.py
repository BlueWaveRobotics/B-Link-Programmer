"""
STM32F1 Option Bytes Worker — corrected RDP Level 1 -> Level 0 (unlock) flow.

Fixes vs. the previous version
------------------------------
1. STM32F1 uses the SAME unlock keys for FLASH_OPTKEYR as for FLASH_KEYR
   (0x45670123 / 0xCDEF89AB). The 0x08192A3B / 0x4C5D6E7F pair belongs to
   STM32F2/F4/L1. On F1 those never set OPTWRE, so every option-byte write is
   silently rejected and RDP never changes.
2. OPTWRE (FLASH_CR bit 9 = 0x200) MUST stay set in every FLASH_CR write while
   erasing/programming option bytes. Writing 0x20 / 0x60 / 0x10 clears OPTWRE
   and the controller refuses the operation (WRPRTERR).
3. Poll FLASH_SR.BSY after every erase/program instead of fixed sleeps, and
   check PGERR / WRPRTERR.
4. Force an option-byte RELOAD (hardware reset via a fresh under-reset connect,
   or a physical power-cycle) so the RDP->0xA5 transition triggers the internal
   mass-erase and actually takes effect.

Note: unlocking (RDP L1 -> L0) mass-erases the main flash by design. After a
successful unlock, reads at 0x08000000 will be 0xFF — that is expected.
"""

import time
from typing import Optional, Dict, Any
from PySide6.QtCore import QThread, Signal
from pyocd.core.helpers import ConnectHelper
from pyocd.core.target import Target

from src.common import get_logger

logger = get_logger("OptionBytesWorker")

# --- STM32F1 register map ---
OB_BASE_ADDR = 0x1FFFF800   # {nRDP,RDP} @ +0 ; {nUSER,USER} @ +2
FLASH_KEYR_ADDR = 0x40022004
FLASH_OPTKEYR_ADDR = 0x40022008
FLASH_SR_ADDR = 0x4002200C
FLASH_CR_ADDR = 0x40022010

# STM32F1: OPTKEYR keys == KEYR keys (NOT the F2/F4 values!)
KEY1 = 0x45670123
KEY2 = 0xCDEF89AB
OPTKEY1 = 0x45670123
OPTKEY2 = 0xCDEF89AB

# FLASH_CR bits
CR_OPTPG = 1 << 4   # 0x010
CR_OPTER = 1 << 5   # 0x020
CR_STRT = 1 << 6   # 0x040
CR_LOCK = 1 << 7   # 0x080
CR_OPTWRE = 1 << 9   # 0x200  <-- must be kept set during OB ops

# FLASH_SR bits
SR_BSY = 1 << 0
SR_PGERR = 1 << 2
SR_WRPRTERR = 1 << 4
SR_EOP = 1 << 5

RDP_UNLOCK = 0xA5    # RDP byte value for Level 0


def _get_safe_session(target_override: str = "stm32f103c8",
                      max_retries: int = 3, retry_delay: float = 0.5):
    """Open an SWD session under-reset (works even on a locked chip)."""
    options = {
        "connect_mode": "under-reset",
        "reset_type": "hw",
        "halt_on_connect": True,
        "resume_on_disconnect": False,
        "target_override": target_override,
    }
    for attempt in range(1, max_retries + 1):
        try:
            print(
                f"[DEBUG-CONN] Attempting SWD connection ({attempt}/{max_retries})...")
            session = ConnectHelper.session_with_chosen_probe(
                blocking=True, options=options)
            if session:
                session.open()
                print("[DEBUG-CONN] ✔ SWD session opened.")
                return session
        except Exception as exc:
            print(f"[DEBUG-CONN] ✖ Attempt {attempt} failed: {exc}")
            time.sleep(retry_delay)
    return None


# ----------------------------------------------------------------------------
# Low-level helpers
# ----------------------------------------------------------------------------
def _wait_busy(target: Target, timeout: float = 5.0) -> int:
    """Poll FLASH_SR.BSY until clear. Returns final SR. FLASH_SR is a
    peripheral register and stays readable even under RDP Level 1."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        sr = target.read32(FLASH_SR_ADDR)
        if not (sr & SR_BSY):
            return sr
        time.sleep(0.002)
    raise TimeoutError("FLASH BSY did not clear (timeout).")


def _clear_errors(target: Target) -> None:
    # EOP / PGERR / WRPRTERR are cleared by writing 1.
    target.write32(FLASH_SR_ADDR, SR_EOP | SR_PGERR | SR_WRPRTERR)


def _unlock_fpec_and_ob(target: Target) -> None:
    """Unlock the flash controller and the option-byte write enable (OPTWRE)."""
    _wait_busy(target)
    # 1) unlock FPEC (clears LOCK)
    target.write32(FLASH_KEYR_ADDR, KEY1)
    target.write32(FLASH_KEYR_ADDR, KEY2)
    # 2) unlock option-byte writes (sets OPTWRE in FLASH_CR)
    target.write32(FLASH_OPTKEYR_ADDR, OPTKEY1)
    target.write32(FLASH_OPTKEYR_ADDR, OPTKEY2)

    cr = target.read32(FLASH_CR_ADDR)
    if not (cr & CR_OPTWRE):
        raise RuntimeError(
            f"OPTWRE not set after key sequence (CR=0x{cr:08X}). "
            f"Wrong OPTKEYR keys, or LOCK still active.")
    print(f"[UNLOCK] ✔ FPEC + OPTWRE ok (CR=0x{cr:08X}).")


def _erase_option_bytes(target: Target) -> None:
    """Erase ALL option bytes. On a read-protected chip this arms the
    unprotect/mass-erase that completes at the next OB reload."""
    _wait_busy(target)
    _clear_errors(target)
    target.write32(FLASH_CR_ADDR, CR_OPTER | CR_OPTWRE)              # 0x220
    target.write32(FLASH_CR_ADDR, CR_OPTER | CR_OPTWRE | CR_STRT)    # 0x260
    sr = _wait_busy(target)
    # clear OPTER, keep OPTWRE
    target.write32(FLASH_CR_ADDR, CR_OPTWRE)
    if sr & (SR_PGERR | SR_WRPRTERR):
        raise RuntimeError(f"Option erase failed (SR=0x{sr:08X}).")
    print("[ERASE] ✔ Option bytes erased (all 0xFF).")


def _program_ob_halfword(target: Target, addr: int, value_byte: int) -> None:
    """Program one option half-word: low byte = value, high byte = complement."""
    compl = (~value_byte) & 0xFF
    halfword = (compl << 8) | (value_byte & 0xFF)
    _wait_busy(target)
    _clear_errors(target)
    target.write32(FLASH_CR_ADDR, CR_OPTPG | CR_OPTWRE)              # 0x210
    target.write16(addr, halfword)
    sr = _wait_busy(target)
    # clear OPTPG
    target.write32(FLASH_CR_ADDR, CR_OPTWRE)
    if sr & (SR_PGERR | SR_WRPRTERR):
        raise RuntimeError(
            f"Option program failed @0x{addr:08X} (SR=0x{sr:08X}).")
    print(
        f"[PROG] ✔ 0x{value_byte:02X} -> 0x{addr:08X} (hw=0x{halfword:04X}).")


# ----------------------------------------------------------------------------
# READ worker  (heuristic: a fault at OB base == locked)
# ----------------------------------------------------------------------------
class OptionBytesReadWorker(QThread):
    ob_read_finished = Signal(bool, dict, str)

    def __init__(self, parent: Optional[QThread] = None):
        super().__init__(parent)

    def run(self) -> None:
        print("\n=========== [READ: START] ===========")
        session = _get_safe_session()
        if not session:
            self.ob_read_finished.emit(
                False, {}, "No DAPLink probe connected.")
            return
        try:
            target: Target = session.target
            try:
                ob0 = target.read32(OB_BASE_ADDR)
                ob1 = target.read32(OB_BASE_ADDR + 4)
                rdp_byte = ob0 & 0xFF
                user_byte = (ob0 >> 16) & 0xFF
                ob_data = {
                    "rdp_raw": rdp_byte,
                    "iwdg_sw":   bool(user_byte & (1 << 0)),
                    "nrst_stop": bool(user_byte & (1 << 1)),
                    "nrst_stdby": bool(user_byte & (1 << 2)),
                    "raw_hex": f"{ob0:08X} {ob1:08X}",
                }
                print(f"[READ] RDP=0x{rdp_byte:02X}  ->  "
                      f"{'UNLOCKED (L0)' if rdp_byte == RDP_UNLOCK else 'LOCKED (L1)'}")
                self.ob_read_finished.emit(True, ob_data, "")
            except Exception as read_exc:
                print(f"[READ] 🛑 Locked (fault reading OB): {read_exc}")
                self.ob_read_finished.emit(True, {
                    "rdp_raw": 0xBB, "iwdg_sw": True, "nrst_stop": True,
                    "nrst_stdby": True, "raw_hex": "[ BLOCKED BY RDP LEVEL 1 ]",
                }, "")
        except Exception as exc:
            self.ob_read_finished.emit(False, {}, str(exc))
        finally:
            if session and session.is_open:
                session.close()


# ----------------------------------------------------------------------------
# PROGRAM worker
# ----------------------------------------------------------------------------
class OptionBytesProgramWorker(QThread):
    ob_program_finished = Signal(bool, str)

    def __init__(self, rdp_value: int, user_config_byte: int,
                 parent: Optional[QThread] = None):
        super().__init__(parent)
        self.rdp_value = rdp_value
        self.user_config_byte = user_config_byte

    def run(self) -> None:
        is_unlock = (self.rdp_value == RDP_UNLOCK)
        print("\n=========== [PROGRAM: START] ===========")
        print(f"[PROG] Target RDP = 0x{self.rdp_value:02X} "
              f"({'UNLOCK' if is_unlock else 'LOCK'})")

        # --- Session 1: unlock + erase OBs + program RDP/USER --------------
        session = _get_safe_session(max_retries=5, retry_delay=0.5)
        if not session:
            self.ob_program_finished.emit(False, "No DAPLink probe connected.")
            return
        try:
            target: Target = session.target
            _unlock_fpec_and_ob(target)
            _erase_option_bytes(target)
            # RDP first, then USER byte (both re-programmed after full erase)
            _program_ob_halfword(target, OB_BASE_ADDR,     self.rdp_value)
            _program_ob_halfword(target, OB_BASE_ADDR +
                                 2, self.user_config_byte)
            print("[PROG] ✔ RDP + USER written. Closing to force OB reload...")
        except Exception as exc:
            print(f"[PROG] ✖ {exc}")
            self.ob_program_finished.emit(False, str(exc))
            if session and session.is_open:
                session.close()
            return
        finally:
            if session and session.is_open:
                session.close()

        # --- OB reload: a fresh under-reset connect asserts nRST, which
        #     reloads the option bytes and (for unlock) runs the mass-erase.
        #     If your DAPLink/target wiring can't drive nRST, POWER-CYCLE here.
        time.sleep(0.5)

        # --- Session 2: verify -------------------------------------------
        print("[VERIFY] Re-connecting to reload OB and verify...")
        verify = _get_safe_session(max_retries=5, retry_delay=0.5)
        if not verify:
            self.ob_program_finished.emit(
                False, "Programmed, but could not re-connect to verify "
                       "(try a physical power-cycle).")
            return
        try:
            word = verify.target.read32(OB_BASE_ADDR)
            rdp = word & 0xFF
            print(f"[VERIFY] OB word = 0x{word:08X}  (RDP=0x{rdp:02X})")
            if is_unlock:
                if rdp == RDP_UNLOCK:
                    self.ob_program_finished.emit(
                        True, "Unlocked (RDP Level 0). Main flash was mass-erased.")
                else:
                    self.ob_program_finished.emit(
                        False, f"Still locked (RDP=0x{rdp:02X}). "
                        f"Try a physical power-cycle, then Reload.")
            else:
                self.ob_program_finished.emit(True, "Locked to RDP Level 1.")
        except Exception as post_err:
            # A fault here while unlocking usually means OB didn't reload yet.
            print(f"[VERIFY] read note: {post_err}")
            if is_unlock:
                self.ob_program_finished.emit(
                    False, "Programmed but still faulting — power-cycle the "
                           "board, then press Reload OB.")
            else:
                self.ob_program_finished.emit(True, "Locked to RDP Level 1.")
        finally:
            if verify and verify.is_open:
                verify.close()
