"""
Hardware Register Definitions & MCU Identification Database.
Contains CoreSight debugging registers, STMicroelectronics DBGMCU maps, 
and Option Bytes base addresses.
"""

# ---------------------------------------------------------
# ARM CoreSight Standard Debug Registers
# ---------------------------------------------------------
DHCSR_ADDR = 0xE000EDF0
DEMCR_ADDR = 0xE000EDFC

DHCSR_BITS = {
    0: ("C_DEBUGEN", "Enable halting debug"),
    1: ("C_HALT", "Halt core"),
    2: ("C_STEP", "Step core"),
    16: ("S_REGRDY", "Register read/write available"),
    17: ("S_HALT", "Core is halted"),
    18: ("S_SLEEP", "Core is sleeping"),
    19: ("S_LOCKUP", "Core is locked up"),
}

DEMCR_BITS = {
    0: ("VC_CORERESET", "Reset Vector Catch"),
    10: ("VC_HARDERR", "Hard Fault Vector Catch"),
    24: ("TRCENA", "Trace enable"),
}

# ---------------------------------------------------------
# Option Bytes & RDP Keys (Restored to fix ImportError)
# ---------------------------------------------------------
STM32F1_OB_BASE = 0x1FFFF800
STM32F1_RDP_KEY_LEVEL_0 = 0x00A5
STM32F1_RDP_KEY_LEVEL_1 = 0x00FF  # Any value other than 0xA5 is Level 1

# ---------------------------------------------------------
# STMicroelectronics Specific Registers (Smart Auto-Detect)
# ---------------------------------------------------------
DBGMCU_IDCODE_ADDR = 0xE0042000

# Comprehensive Mapping of DEV_ID (bits 0..11 of DBGMCU_IDCODE)
# to CMSIS-Pack target names. Covers almost the entire STM32 catalog.
STM32_DEVID_MAP = {
    # STM32 F0 Family
    0x444: "stm32f030r8",  # F030x4/x6/x8 / F051x4/x6/x8
    0x440: "stm32f051r8",  # F05x
    0x445: "stm32f042k6",  # F04x / F070x6
    0x448: "stm32f072r8",  # F07x / F070xB
    0x442: "stm32f091rc",  # F09x / F030xC

    # STM32 F1 Family
    0x412: "stm32f103t6",  # Low density
    0x410: "stm32f103c8",  # Medium density (F103C8/CB)
    0x414: "stm32f103re",  # High density (F103RC/RE/VC/VE/ZC/ZE)
    0x430: "stm32f103xg",  # XL density (F103xF/xG)
    0x418: "stm32f105rc",  # Connectivity line (F105/F107)
    0x420: "stm32f100rb",  # Value line (Medium)
    0x428: "stm32f100ve",  # Value line (High)

    # STM32 F2 Family
    0x411: "stm32f205rg",  # F205/207

    # STM32 F3 Family
    0x422: "stm32f302r8",  # F302x6/8 / F303x6/8
    0x432: "stm32f373cc",  # F373 / F378
    0x438: "stm32f334c8",  # F334 / F303x8
    0x439: "stm32f302vc",  # F302xB/C / F303xB/C
    0x446: "stm32f303ze",  # F303xD/E / F398

    # STM32 F4 Family
    0x413: "stm32f407vg",  # F405/407/415/417
    0x419: "stm32f429zi",  # F427/429/437/439
    0x423: "stm32f401cc",  # F401xB/C
    0x433: "stm32f401re",  # F401xD/E
    0x431: "stm32f411ce",  # F411
    0x441: "stm32f412zg",  # F412
    0x458: "stm32f410rx",  # F410
    0x463: "stm32f413zh",  # F413/423

    # STM32 F7 Family
    0x449: "stm32f746ng",  # F74x/75x
    0x451: "stm32f767zi",  # F76x/77x
    0x452: "stm32f722zet",  # F72x/73x

    # STM32 G0 Family
    0x460: "stm32g071rb",  # G07x/08x
    0x466: "stm32g031k8",  # G03x/04x
    0x467: "stm32g0b1re",  # G0B0/G0B1/G0C1

    # STM32 G4 Family
    0x468: "stm32g431rb",  # G43x/44x
    0x469: "stm32g474re",  # G47x/48x
    0x479: "stm32g491re",  # G49x/4Ax

    # STM32 L0 Family
    0x417: "stm32l053r8",  # L05x/06x (Cat. 3)
    0x425: "stm32l011k4",  # L01x/02x (Cat. 1/2)
    0x447: "stm32l073rz",  # L07x/08x (Cat. 5)
    0x457: "stm32l031k6",  # L03x/04x (Cat. 2)

    # STM32 L1 Family
    0x416: "stm32l152rb",  # L15xxB (Cat. 1)
    0x429: "stm32l152re",  # L15xxE (Cat. 3)
    0x427: "stm32l152rc",  # L15xxC (Cat. 2)
    0x436: "stm32l152rd",  # L15xxD (Cat. 4/5)

    # STM32 L4 / L4+ Family
    0x415: "stm32l476rg",  # L47x/48x
    0x435: "stm32l432kc",  # L43x/44x
    0x462: "stm32l452re",  # L45x/46x
    0x470: "stm32l412kb",  # L41x/42x
    0x471: "stm32l4p5cg",  # L4Px/4Qx (L4+)
    0x472: "stm32l4r9zi",  # L4Rx/4Sx (L4+)

    # STM32 L5 Family
    0x472: "stm32l552ze",  # L55x/56x (Note: Shares DevID with some L4+)

    # STM32 H5 / H7 Family
    0x450: "stm32h743zi",  # H74x/75x
    0x480: "stm32h7b3li",  # H7A3/7B3/7B0
    0x483: "stm32h723zg",  # H72x/73x
    0x484: "stm32h563zi",  # H56x/57x

    # STM32 U5 Family
    0x481: "stm32u575cg",  # U575/585
    0x482: "stm32u599nj",  # U59x/5Ax

    # STM32 C0 Family
    0x443: "stm32c031c6",  # C01x/03x

    # STM32 WB / WL Wireless Families
    0x495: "stm32wb55rg",  # WB55/50
    0x496: "stm32wb35ce",  # WB35/30
    0x497: "stm32wl55jc",  # WL55/54/4x
}
