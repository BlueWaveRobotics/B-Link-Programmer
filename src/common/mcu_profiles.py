"""
Centralized MCU Hardware Memory Database.
Provides memory map presets (Flash, SRAM, Option Bytes, UIDs) based on MCU part number.
"""


def get_memory_presets(target_name: str) -> list:
    """Returns a list of (Label, HexAddress) for the requested MCU target."""
    target = str(target_name or "auto").lower().strip()
    presets = []

    # Cortex-M System Control Block (Common across all ARM Cortex-M)
    scb_register = ("0xE000ED00 - Cortex-M SCB Registers", "0xE000ED00")

    # 1. STM32F1 & GD32F1 Families
    if "stm32f1" in target or "gd32f1" in target or "apm32f1" in target:
        presets = [
            ("0x08000000 - Main Flash Memory", "0x08000000"),
            ("0x20000000 - SRAM (System RAM)", "0x20000000"),
            ("0x1FFFF000 - System Memory (Bootloader)", "0x1FFFF000"),
            ("0x1FFFF800 - Option Bytes", "0x1FFFF800"),
            ("0x1FFF7A10 - Unique Device ID (UID)", "0x1FFF7A10"),
        ]

    # 2. STM32F4, STM32F2, STM32F7, GD32F4 Families
    elif "stm32f4" in target or "stm32f2" in target or "stm32f7" in target or "gd32f4" in target:
        presets = [
            ("0x08000000 - Main Flash Memory", "0x08000000"),
            ("0x20000000 - SRAM1 (System RAM)", "0x20000000"),
            ("0x1FFF0000 - System Memory (Bootloader)", "0x1FFF0000"),
            ("0x1FFFC000 - Option Bytes", "0x1FFFC000"),
            ("0x1FFF7A10 - Unique Device ID (UID)", "0x1FFF7A10"),
        ]

    # 3. STM32G0 & STM32G4 Families
    elif "stm32g0" in target or "stm32g4" in target:
        presets = [
            ("0x08000000 - Main Flash Memory", "0x08000000"),
            ("0x20000000 - SRAM", "0x20000000"),
            ("0x1FFF0000 - System Memory (Bootloader)", "0x1FFF0000"),
            ("0x1FFF7800 - Option Bytes", "0x1FFF7800"),
            ("0x1FFF7590 - Unique Device ID (UID)", "0x1FFF7590"),
        ]

    # 4. NXP LPC17xx Families
    elif "lpc17" in target:
        presets = [
            ("0x00000000 - Main Flash Memory", "0x00000000"),
            ("0x10000000 - Local SRAM", "0x10000000"),
            ("0x2007C000 - AHB SRAM (Peripheral)", "0x2007C000"),
            ("0x1FFF0000 - Boot ROM", "0x1FFF0000"),
        ]

    # 5. Nordic nRF52 Families
    elif "nrf52" in target:
        presets = [
            ("0x00000000 - Main Flash Memory", "0x00000000"),
            ("0x20000000 - SRAM", "0x20000000"),
            ("0x10001000 - UICR (User Information)", "0x10001000"),
            ("0x10000000 - FICR (Factory Info/UID)", "0x10000000"),
        ]

    # 6. Raspberry Pi RP2040
    elif "rp2040" in target:
        presets = [
            ("0x10000000 - XIP Flash (External)", "0x10000000"),
            ("0x20000000 - Main SRAM", "0x20000000"),
            ("0x00000000 - Internal ROM", "0x00000000"),
        ]

    # Default Fallback (Generic ARM Cortex-M)
    else:
        presets = [
            ("0x08000000 - Main Flash Memory (Default)", "0x08000000"),
            ("0x20000000 - SRAM (Default)", "0x20000000"),
        ]

    presets.append(scb_register)
    return presets
