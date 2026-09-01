# """
# Centralized MCU Hardware Memory Database.
# Provides memory map presets (Flash, SRAM, Option Bytes, UIDs) based on MCU part number.
# """


# def get_memory_presets(target_name: str) -> list:
#     """Returns a list of (Label, HexAddress) for the requested MCU target."""
#     target = str(target_name or "auto").lower().strip()
#     presets = []

#     # Cortex-M System Control Block (Common across all ARM Cortex-M)
#     scb_register = ("0xE000ED00 - Cortex-M SCB Registers", "0xE000ED00")

#     # 1. STM32F1 & GD32F1 Families
#     if "stm32f1" in target or "gd32f1" in target or "apm32f1" in target:
#         presets = [
#             ("0x08000000 - Main Flash Memory", "0x08000000"),
#             ("0x20000000 - SRAM (System RAM)", "0x20000000"),
#             ("0x1FFFF000 - System Memory (Bootloader)", "0x1FFFF000"),
#             ("0x1FFFF800 - Option Bytes", "0x1FFFF800"),
#             ("0x1FFF7A10 - Unique Device ID (UID)", "0x1FFF7A10"),
#         ]

#     # 2. STM32F4, STM32F2, STM32F7, GD32F4 Families
#     elif "stm32f4" in target or "stm32f2" in target or "stm32f7" in target or "gd32f4" in target:
#         presets = [
#             ("0x08000000 - Main Flash Memory", "0x08000000"),
#             ("0x20000000 - SRAM1 (System RAM)", "0x20000000"),
#             ("0x1FFF0000 - System Memory (Bootloader)", "0x1FFF0000"),
#             ("0x1FFFC000 - Option Bytes", "0x1FFFC000"),
#             ("0x1FFF7A10 - Unique Device ID (UID)", "0x1FFF7A10"),
#         ]

#     # 3. STM32G0 & STM32G4 Families
#     elif "stm32g0" in target or "stm32g4" in target:
#         presets = [
#             ("0x08000000 - Main Flash Memory", "0x08000000"),
#             ("0x20000000 - SRAM", "0x20000000"),
#             ("0x1FFF0000 - System Memory (Bootloader)", "0x1FFF0000"),
#             ("0x1FFF7800 - Option Bytes", "0x1FFF7800"),
#             ("0x1FFF7590 - Unique Device ID (UID)", "0x1FFF7590"),
#         ]

#     # 4. NXP LPC17xx Families
#     elif "lpc17" in target:
#         presets = [
#             ("0x00000000 - Main Flash Memory", "0x00000000"),
#             ("0x10000000 - Local SRAM", "0x10000000"),
#             ("0x2007C000 - AHB SRAM (Peripheral)", "0x2007C000"),
#             ("0x1FFF0000 - Boot ROM", "0x1FFF0000"),
#         ]

#     # 5. Nordic nRF52 Families
#     elif "nrf52" in target:
#         presets = [
#             ("0x00000000 - Main Flash Memory", "0x00000000"),
#             ("0x20000000 - SRAM", "0x20000000"),
#             ("0x10001000 - UICR (User Information)", "0x10001000"),
#             ("0x10000000 - FICR (Factory Info/UID)", "0x10000000"),
#         ]

#     # 6. Raspberry Pi RP2040
#     elif "rp2040" in target:
#         presets = [
#             ("0x10000000 - XIP Flash (External)", "0x10000000"),
#             ("0x20000000 - Main SRAM", "0x20000000"),
#             ("0x00000000 - Internal ROM", "0x00000000"),
#         ]

#     # Default Fallback (Generic ARM Cortex-M)
#     else:
#         presets = [
#             ("0x08000000 - Main Flash Memory (Default)", "0x08000000"),
#             ("0x20000000 - SRAM (Default)", "0x20000000"),
#         ]

#     presets.append(scb_register)
#     return presets
"""
Centralized MCU Hardware Memory Database.
Provides memory map presets (Flash, SRAM, Option Bytes, UIDs) based on MCU part number.
Expanded to support generic vendor matching for 1000+ pyOCD targets.
"""


def get_memory_presets(target_name: str) -> list:
    """Returns a list of (Label, HexAddress) for the requested MCU target."""
    target = str(target_name or "auto").lower().strip()
    presets = []

    # Cortex-M System Control Block (Common across all ARM Cortex-M)
    scb_register = ("0xE000ED00 - Cortex-M SCB Registers", "0xE000ED00")

    # 1. STM32 & Compatible Families (GigaDevice, APM32, Artery, CH32, CKS32)
    if any(prefix in target for prefix in ["stm32", "gd32", "apm32", "at32", "cks32", "ch32", "hk32"]):
        presets = [
            ("0x08000000 - Main Flash Memory", "0x08000000"),
            ("0x20000000 - SRAM (System RAM)", "0x20000000"),
            ("0x1FFFF000 - System Memory (Bootloader)", "0x1FFFF000"),
            ("0x1FFFF800 - Option Bytes", "0x1FFFF800"),
            ("0x1FFF7A10 - Unique Device ID (UID)", "0x1FFF7A10"),
        ]

    # 2. NXP Families (LPC, Kinetis MKE/MKL), Nordic (nRF), Silicon Labs (EFM32), Nuvoton
    elif any(prefix in target for prefix in ["lpc", "mke", "mkl", "nrf", "efm32", "nuvoton", "nuc"]):
        presets = [
            ("0x00000000 - Main Flash Memory", "0x00000000"),
            ("0x10000000 - Local SRAM", "0x10000000"),
            ("0x20000000 - AHB SRAM (System)", "0x20000000"),
            ("0x10001000 - UICR / Option / Factory Info", "0x10001000"),
        ]

    # 3. Raspberry Pi (RP2040, RP2350)
    elif "rp20" in target or "rp23" in target:
        presets = [
            ("0x10000000 - XIP Flash (External)", "0x10000000"),
            ("0x20000000 - Main SRAM", "0x20000000"),
            ("0x00000000 - Internal ROM", "0x00000000"),
        ]

    # 4. Texas Instruments (CC13xx, CC26xx, MSP432)
    elif any(prefix in target for prefix in ["cc13", "cc26", "msp432"]):
        presets = [
            ("0x00000000 - Main Flash Memory", "0x00000000"),
            ("0x20000000 - SRAM", "0x20000000"),
        ]

    # 5. Microchip / Atmel (SAMD, SAME, SAMG)
    elif "atsam" in target or "samd" in target:
        presets = [
            ("0x00000000 - Main Flash Memory", "0x00000000"),
            ("0x20000000 - SRAM", "0x20000000"),
            ("0x00804000 - User Row / Fuses", "0x00804000"),
        ]

    # 6. Default Fallback for ANY unknown or newly added Cortex-M targets
    else:
        presets = [
            ("0x08000000 - Main Flash Memory (ST Standard)", "0x08000000"),
            ("0x00000000 - Main Flash Memory (ARM Standard)", "0x00000000"),
            ("0x20000000 - SRAM (Default)", "0x20000000"),
        ]

    presets.append(scb_register)
    return presets
