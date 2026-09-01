# """
# Option Bytes Worker — dynamically adjusts OB Base Address based on MCU profile.
# Includes safety locks to prevent STM32-specific OB unlock sequences from
# executing and crashing non-ST microcontrollers (like NXP or Nordic).
# """

# import time
# from typing import Optional, Dict, Any
# from PySide6.QtCore import QThread, Signal
# from pyocd.core.helpers import ConnectHelper
# from pyocd.core.target import Target

# from src.common import get_logger
# from src.common.mcu_profiles import get_memory_presets  # 🌟 فراخوانی دیتابیس حافظه

# logger = get_logger("OptionBytesWorker")

# # --- STM32F1 / Generic ST Register Map ---
# FLASH_KEYR_ADDR = 0x40022004
# FLASH_OPTKEYR_ADDR = 0x40022008
# FLASH_SR_ADDR = 0x4002200C
# FLASH_CR_ADDR = 0x40022010

# KEY1 = 0x45670123
# KEY2 = 0xCDEF89AB
# OPTKEY1 = 0x45670123
# OPTKEY2 = 0xCDEF89AB

# CR_OPTPG = 1 << 4
# CR_OPTER = 1 << 5
# CR_STRT = 1 << 6
# CR_LOCK = 1 << 7
# CR_OPTWRE = 1 << 9

# SR_BSY = 1 << 0
# SR_PGERR = 1 << 2
# SR_WRPRTERR = 1 << 4
# SR_EOP = 1 << 5

# RDP_UNLOCK = 0xA5


# def _get_ob_base(target_type: str) -> int:
#     """استخراج آدرس دقیق آپشن بایت از دیتابیس مرکزی"""
#     presets = get_memory_presets(target_type)
#     for lbl, addr in presets:
#         if "Option" in lbl or "UICR" in lbl:
#             return int(addr, 16)
#     return 0x1FFFF800  # پیش‌فرض STM32F1


# def _get_safe_session(target_override: str, max_retries: int = 3, retry_delay: float = 0.5):
#     """Open an SWD session under-reset (works even on a locked chip)."""
#     options = {
#         "connect_mode": "under-reset",
#         "reset_type": "hw",
#         "halt_on_connect": True,
#         "resume_on_disconnect": False,
#         "target_override": target_override,
#     }
#     for attempt in range(1, max_retries + 1):
#         try:
#             print(
#                 f"[DEBUG-CONN] Attempting SWD connection ({attempt}/{max_retries})...")
#             session = ConnectHelper.session_with_chosen_probe(
#                 blocking=True, options=options)
#             if session:
#                 session.open()
#                 print("[DEBUG-CONN] ✔ SWD session opened.")
#                 return session
#         except Exception as exc:
#             print(f"[DEBUG-CONN] ✖ Attempt {attempt} failed: {exc}")
#             time.sleep(retry_delay)
#     return None

# # --- توابع سطح پایین رایت (فقط برای ST) ---


# def _wait_busy(target: Target, timeout: float = 5.0) -> int:
#     t0 = time.time()
#     while time.time() - t0 < timeout:
#         sr = target.read32(FLASH_SR_ADDR)
#         if not (sr & SR_BSY):
#             return sr
#         time.sleep(0.002)
#     raise TimeoutError("FLASH BSY did not clear (timeout).")


# def _clear_errors(target: Target) -> None:
#     target.write32(FLASH_SR_ADDR, SR_EOP | SR_PGERR | SR_WRPRTERR)


# def _unlock_fpec_and_ob(target: Target) -> None:
#     _wait_busy(target)
#     target.write32(FLASH_KEYR_ADDR, KEY1)
#     target.write32(FLASH_KEYR_ADDR, KEY2)
#     target.write32(FLASH_OPTKEYR_ADDR, OPTKEY1)
#     target.write32(FLASH_OPTKEYR_ADDR, OPTKEY2)
#     cr = target.read32(FLASH_CR_ADDR)
#     if not (cr & CR_OPTWRE):
#         raise RuntimeError(
#             f"OPTWRE not set (CR=0x{cr:08X}). Wrong OPTKEYR or LOCK active.")


# def _erase_option_bytes(target: Target) -> None:
#     _wait_busy(target)
#     _clear_errors(target)
#     target.write32(FLASH_CR_ADDR, CR_OPTER | CR_OPTWRE)
#     target.write32(FLASH_CR_ADDR, CR_OPTER | CR_OPTWRE | CR_STRT)
#     sr = _wait_busy(target)
#     target.write32(FLASH_CR_ADDR, CR_OPTWRE)
#     if sr & (SR_PGERR | SR_WRPRTERR):
#         raise RuntimeError(f"Option erase failed (SR=0x{sr:08X}).")


# def _program_ob_halfword(target: Target, addr: int, value_byte: int) -> None:
#     compl = (~value_byte) & 0xFF
#     halfword = (compl << 8) | (value_byte & 0xFF)
#     _wait_busy(target)
#     _clear_errors(target)
#     target.write32(FLASH_CR_ADDR, CR_OPTPG | CR_OPTWRE)
#     target.write16(addr, halfword)
#     sr = _wait_busy(target)
#     target.write32(FLASH_CR_ADDR, CR_OPTWRE)
#     if sr & (SR_PGERR | SR_WRPRTERR):
#         raise RuntimeError(
#             f"Option program failed @0x{addr:08X} (SR=0x{sr:08X}).")

# # ----------------------------------------------------------------------------
# # READ worker
# # ----------------------------------------------------------------------------


# class OptionBytesReadWorker(QThread):
#     ob_read_finished = Signal(bool, dict, str)

#     def __init__(self, target_type: str, parent: Optional[QThread] = None):
#         super().__init__(parent)
#         self.target_type = target_type

#     def run(self) -> None:
#         print("\n=========== [READ: START] ===========")
#         session = _get_safe_session(self.target_type)
#         if not session:
#             self.ob_read_finished.emit(False, {}, "No B-Link probe connected.")
#             return

#         ob_base_address = _get_ob_base(self.target_type)
#         print(
#             f"[READ] Reading Option Bytes from base: 0x{ob_base_address:08X}")

#         try:
#             target: Target = session.target
#             try:
#                 ob0 = target.read32(ob_base_address)
#                 ob1 = target.read32(ob_base_address + 4)

#                 # برای بردهای ST، بایت‌ها را پارس می‌کنیم
#                 rdp_byte = ob0 & 0xFF
#                 user_byte = (ob0 >> 16) & 0xFF

#                 ob_data = {
#                     "rdp_raw": rdp_byte,
#                     "iwdg_sw":   bool(user_byte & (1 << 0)),
#                     "nrst_stop": bool(user_byte & (1 << 1)),
#                     "nrst_stdby": bool(user_byte & (1 << 2)),
#                     "raw_hex": f"{ob0:08X} {ob1:08X}",
#                 }

#                 # اگر برد ST نبود، وضعیت RDP را کاذب برمی‌گردانیم تا UI هشدار دهد
#                 if "f1" not in self.target_type.lower() and self.target_type not in ["auto", "cortex_m"]:
#                     ob_data["rdp_raw"] = 0xFF  # وضعیت نامشخص برای غیر ST

#                 self.ob_read_finished.emit(True, ob_data, "")
#             except Exception as read_exc:
#                 print(f"[READ] 🛑 Locked (fault reading OB): {read_exc}")
#                 self.ob_read_finished.emit(True, {
#                     "rdp_raw": 0xBB, "iwdg_sw": True, "nrst_stop": True,
#                     "nrst_stdby": True, "raw_hex": "[ BLOCKED BY RDP OR UNKNOWN MEMORY ]",
#                 }, "")
#         except Exception as exc:
#             self.ob_read_finished.emit(False, {}, str(exc))
#         finally:
#             if session and session.is_open:
#                 session.close()

# # ----------------------------------------------------------------------------
# # PROGRAM worker
# # ----------------------------------------------------------------------------


# class OptionBytesProgramWorker(QThread):
#     ob_program_finished = Signal(bool, str)

#     def __init__(self, rdp_value: int, user_config_byte: int, target_type: str, parent: Optional[QThread] = None):
#         super().__init__(parent)
#         self.rdp_value = rdp_value
#         self.user_config_byte = user_config_byte
#         self.target_type = target_type

#     def run(self) -> None:
#         # 🛡️ سپر امنیتی: جلوگیری از رایت تنظیمات اختصاصی ST روی بردهای NXP/Nordic/Raspberry
#         if "lpc" in self.target_type.lower() or "nrf" in self.target_type.lower() or "rp2040" in self.target_type.lower():
#             self.ob_program_finished.emit(
#                 False, f"Option Bytes programming via this UI is currently restricted to STM32 families. Your target '{self.target_type}' is protected from incorrect register writes.")
#             return

#         is_unlock = (self.rdp_value == RDP_UNLOCK)
#         ob_base_address = _get_ob_base(self.target_type)

#         print("\n=========== [PROGRAM: START] ===========")
#         session = _get_safe_session(
#             self.target_type, max_retries=5, retry_delay=0.5)
#         if not session:
#             self.ob_program_finished.emit(False, "No B-Link probe connected.")
#             return

#         try:
#             target: Target = session.target
#             _unlock_fpec_and_ob(target)
#             _erase_option_bytes(target)
#             _program_ob_halfword(target, ob_base_address,     self.rdp_value)
#             _program_ob_halfword(target, ob_base_address +
#                                  2, self.user_config_byte)
#             print("[PROG] ✔ RDP + USER written. Closing to force OB reload...")
#         except Exception as exc:
#             self.ob_program_finished.emit(False, str(exc))
#             if session and session.is_open:
#                 session.close()
#             return
#         finally:
#             if session and session.is_open:
#                 session.close()

#         time.sleep(0.5)

#         verify = _get_safe_session(
#             self.target_type, max_retries=5, retry_delay=0.5)
#         if not verify:
#             self.ob_program_finished.emit(
#                 False, "Programmed, but could not re-connect to verify.")
#             return
#         try:
#             word = verify.target.read32(ob_base_address)
#             rdp = word & 0xFF
#             if is_unlock:
#                 if rdp == RDP_UNLOCK:
#                     self.ob_program_finished.emit(
#                         True, "Unlocked (RDP Level 0). Main flash was mass-erased.")
#                 else:
#                     self.ob_program_finished.emit(
#                         False, f"Still locked (RDP=0x{rdp:02X}). Power-cycle and Reload.")
#             else:
#                 self.ob_program_finished.emit(True, "Locked to RDP Level 1.")
#         except Exception as post_err:
#             if is_unlock:
#                 self.ob_program_finished.emit(
#                     False, "Programmed but still faulting — power-cycle the board.")
#             else:
#                 self.ob_program_finished.emit(True, "Locked to RDP Level 1.")
#         finally:
#             if verify and verify.is_open:
#                 verify.close()

"""
Option Bytes Worker — dynamically adjusts OB Base Address based on MCU profile.
Includes safety locks to prevent STM32-specific OB unlock sequences from
executing and crashing non-ST microcontrollers (like NXP, Nordic, TI, etc.).
"""

import time
from typing import Optional, Dict, Any
from PySide6.QtCore import QThread, Signal
from pyocd.core.helpers import ConnectHelper
from pyocd.core.target import Target

from src.common import get_logger
from src.common.mcu_profiles import get_memory_presets  # 🌟 فراخوانی دیتابیس حافظه

logger = get_logger("OptionBytesWorker")

# --- STM32F1 / Generic ST Register Map ---
FLASH_KEYR_ADDR = 0x40022004
FLASH_OPTKEYR_ADDR = 0x40022008
FLASH_SR_ADDR = 0x4002200C
FLASH_CR_ADDR = 0x40022010

KEY1 = 0x45670123
KEY2 = 0xCDEF89AB
OPTKEY1 = 0x45670123
OPTKEY2 = 0xCDEF89AB

CR_OPTPG = 1 << 4
CR_OPTER = 1 << 5
CR_STRT = 1 << 6
CR_LOCK = 1 << 7
CR_OPTWRE = 1 << 9

SR_BSY = 1 << 0
SR_PGERR = 1 << 2
SR_WRPRTERR = 1 << 4
SR_EOP = 1 << 5

RDP_UNLOCK = 0xA5

# لیست سفید میکروهای سازگار با رجیسترهای آپشن بایت ST
ST_COMPATIBLE_PREFIXES = ["stm32", "gd32", "apm32",
                          "at32", "cks32", "ch32", "hk32", "auto", "cortex_m"]


def _get_ob_base(target_type: str) -> int:
    """استخراج آدرس دقیق آپشن بایت از دیتابیس مرکزی"""
    presets = get_memory_presets(target_type)
    for lbl, addr in presets:
        if "Option" in lbl or "UICR" in lbl:
            return int(addr, 16)
    return 0x1FFFF800  # پیش‌فرض STM32F1


def _get_safe_session(target_override: str, max_retries: int = 3, retry_delay: float = 0.5):
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


# --- توابع سطح پایین رایت (فقط برای ST) ---
def _wait_busy(target: Target, timeout: float = 5.0) -> int:
    t0 = time.time()
    while time.time() - t0 < timeout:
        sr = target.read32(FLASH_SR_ADDR)
        if not (sr & SR_BSY):
            return sr
        time.sleep(0.002)
    raise TimeoutError("FLASH BSY did not clear (timeout).")


def _clear_errors(target: Target) -> None:
    target.write32(FLASH_SR_ADDR, SR_EOP | SR_PGERR | SR_WRPRTERR)


def _unlock_fpec_and_ob(target: Target) -> None:
    _wait_busy(target)
    target.write32(FLASH_KEYR_ADDR, KEY1)
    target.write32(FLASH_KEYR_ADDR, KEY2)
    target.write32(FLASH_OPTKEYR_ADDR, OPTKEY1)
    target.write32(FLASH_OPTKEYR_ADDR, OPTKEY2)
    cr = target.read32(FLASH_CR_ADDR)
    if not (cr & CR_OPTWRE):
        raise RuntimeError(
            f"OPTWRE not set (CR=0x{cr:08X}). Wrong OPTKEYR or LOCK active.")


def _erase_option_bytes(target: Target) -> None:
    _wait_busy(target)
    _clear_errors(target)
    target.write32(FLASH_CR_ADDR, CR_OPTER | CR_OPTWRE)
    target.write32(FLASH_CR_ADDR, CR_OPTER | CR_OPTWRE | CR_STRT)
    sr = _wait_busy(target)
    target.write32(FLASH_CR_ADDR, CR_OPTWRE)
    if sr & (SR_PGERR | SR_WRPRTERR):
        raise RuntimeError(f"Option erase failed (SR=0x{sr:08X}).")


def _program_ob_halfword(target: Target, addr: int, value_byte: int) -> None:
    compl = (~value_byte) & 0xFF
    halfword = (compl << 8) | (value_byte & 0xFF)
    _wait_busy(target)
    _clear_errors(target)
    target.write32(FLASH_CR_ADDR, CR_OPTPG | CR_OPTWRE)
    target.write16(addr, halfword)
    sr = _wait_busy(target)
    target.write32(FLASH_CR_ADDR, CR_OPTWRE)
    if sr & (SR_PGERR | SR_WRPRTERR):
        raise RuntimeError(
            f"Option program failed @0x{addr:08X} (SR=0x{sr:08X}).")

# ----------------------------------------------------------------------------
# READ worker
# ----------------------------------------------------------------------------


class OptionBytesReadWorker(QThread):
    ob_read_finished = Signal(bool, dict, str)

    def __init__(self, target_type: str, parent: Optional[QThread] = None):
        super().__init__(parent)
        self.target_type = target_type

    def run(self) -> None:
        print("\n=========== [READ: START] ===========")
        session = _get_safe_session(self.target_type)
        if not session:
            self.ob_read_finished.emit(False, {}, "No B-Link probe connected.")
            return

        ob_base_address = _get_ob_base(self.target_type)
        print(
            f"[READ] Reading Option Bytes from base: 0x{ob_base_address:08X}")

        try:
            target: Target = session.target
            try:
                ob0 = target.read32(ob_base_address)
                ob1 = target.read32(ob_base_address + 4)

                # پارس کردن بایت‌ها با فرض ST
                rdp_byte = ob0 & 0xFF
                user_byte = (ob0 >> 16) & 0xFF

                ob_data = {
                    "rdp_raw": rdp_byte,
                    "iwdg_sw":   bool(user_byte & (1 << 0)),
                    "nrst_stop": bool(user_byte & (1 << 1)),
                    "nrst_stdby": bool(user_byte & (1 << 2)),
                    "raw_hex": f"{ob0:08X} {ob1:08X}",
                }

                # 🌟 بررسی لیست سفید: اگر برد ST نبود، وضعیت RDP را کاذب برمی‌گردانیم تا UI هشدار دهد
                is_st_compatible = any(prefix in self.target_type.lower()
                                       for prefix in ST_COMPATIBLE_PREFIXES)
                if not is_st_compatible:
                    ob_data["rdp_raw"] = 0xFF  # وضعیت نامشخص برای غیر ST

                self.ob_read_finished.emit(True, ob_data, "")
            except Exception as read_exc:
                print(f"[READ] 🛑 Locked (fault reading OB): {read_exc}")
                self.ob_read_finished.emit(True, {
                    "rdp_raw": 0xBB, "iwdg_sw": True, "nrst_stop": True,
                    "nrst_stdby": True, "raw_hex": "[ BLOCKED BY RDP OR UNKNOWN MEMORY ]",
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

    def __init__(self, rdp_value: int, user_config_byte: int, target_type: str, parent: Optional[QThread] = None):
        super().__init__(parent)
        self.rdp_value = rdp_value
        self.user_config_byte = user_config_byte
        self.target_type = target_type

    def run(self) -> None:
        # 🛡️ سپر امنیتی و لیست سفید: فقط به خانواده STM32 و کلون‌های سازگار اجازه دسترسی داده شود
        is_st_compatible = any(prefix in self.target_type.lower()
                               for prefix in ST_COMPATIBLE_PREFIXES)
        if not is_st_compatible:
            self.ob_program_finished.emit(
                False,
                f"Option Bytes programming via this UI is currently restricted to ST-compatible families. Your target '{self.target_type}' is protected from incorrect register writes."
            )
            return

        is_unlock = (self.rdp_value == RDP_UNLOCK)
        ob_base_address = _get_ob_base(self.target_type)

        print("\n=========== [PROGRAM: START] ===========")
        session = _get_safe_session(
            self.target_type, max_retries=5, retry_delay=0.5)
        if not session:
            self.ob_program_finished.emit(False, "No B-Link probe connected.")
            return

        try:
            target: Target = session.target
            _unlock_fpec_and_ob(target)
            _erase_option_bytes(target)
            _program_ob_halfword(target, ob_base_address,     self.rdp_value)
            _program_ob_halfword(target, ob_base_address +
                                 2, self.user_config_byte)
            print("[PROG] ✔ RDP + USER written. Closing to force OB reload...")
        except Exception as exc:
            self.ob_program_finished.emit(False, str(exc))
            if session and session.is_open:
                session.close()
            return
        finally:
            if session and session.is_open:
                session.close()

        time.sleep(0.5)

        verify = _get_safe_session(
            self.target_type, max_retries=5, retry_delay=0.5)
        if not verify:
            self.ob_program_finished.emit(
                False, "Programmed, but could not re-connect to verify.")
            return
        try:
            word = verify.target.read32(ob_base_address)
            rdp = word & 0xFF
            if is_unlock:
                if rdp == RDP_UNLOCK:
                    self.ob_program_finished.emit(
                        True, "Unlocked (RDP Level 0). Main flash was mass-erased.")
                else:
                    self.ob_program_finished.emit(
                        False, f"Still locked (RDP=0x{rdp:02X}). Power-cycle and Reload.")
            else:
                self.ob_program_finished.emit(True, "Locked to RDP Level 1.")
        except Exception as post_err:
            if is_unlock:
                self.ob_program_finished.emit(
                    False, "Programmed but still faulting — power-cycle the board.")
            else:
                self.ob_program_finished.emit(True, "Locked to RDP Level 1.")
        finally:
            if verify and verify.is_open:
                verify.close()
