"""
Hardware Register Definitions & MCU Identification Database.
Contains CoreSight debugging registers and STMicroelectronics DBGMCU maps.
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
# STMicroelectronics Specific Registers (Smart Auto-Detect)
# ---------------------------------------------------------
DBGMCU_IDCODE_ADDR = 0xE0042000

# Mapping of DEV_ID (bits 0..11 of DBGMCU_IDCODE) to CMSIS-Pack target names
STM32_DEVID_MAP = {
    0x412: "stm32f103rb",  # Low/Medium density (F103C8/RB)
    0x414: "stm32f103re",  # High density (F103RC/RE/ZC/ZE)
    0x430: "stm32f103xg",  # XL density
    0x410: "stm32f105rc",  # Connectivity line (F105/F107)
    0x411: "stm32f205rg",  # F205/207
    0x413: "stm32f407vg",  # F405/407
    0x419: "stm32f429zi",  # F427/429/437/439
    0x423: "stm32f401cc",  # F401xB/C
    0x433: "stm32f401re",  # F401xD/E
    0x431: "stm32f411ce",  # F411
    0x441: "stm32f412zg",  # F412
    0x458: "stm32f410rx",  # F410
    0x449: "stm32f746ng",  # F74x/F75x
    0x451: "stm32f767zi",  # F76x/F77x
    0x444: "stm32f030r8",  # F030
    0x440: "stm32f051r8",  # F051
    0x445: "stm32f042k6",  # F042
    0x448: "stm32f072r8",  # F072
    0x442: "stm32f091rc",  # F091
    0x460: "stm32g071rb",  # G07x/G08x
    0x466: "stm32g031k8",  # G03x/G04x
    0x467: "stm32g0b1re",  # G0B0/G0B1/G0C1
    0x468: "stm32g431rb",  # G431
    0x469: "stm32g474re",  # G474
    0x416: "stm32l152rb",  # L1 Cat. 1
    0x429: "stm32l152re",  # L1 Cat. 2
    0x470: "stm32l432kc",  # L432
    0x415: "stm32l476rg",  # L476
    0x447: "stm32l053r8",  # L053
    0x457: "stm32l073rz",  # L073
    0x483: "stm32h743zi",  # H743
    0x480: "stm32h7b3li",  # H7B3
}
