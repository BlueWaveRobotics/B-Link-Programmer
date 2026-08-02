"""
Hardware register addresses, bit definitions, and Option Bytes constants
for ARM Cortex-M debug cores and STM32 microcontrollers.
"""

# =====================================================================
# ARM Cortex-M Core Debug Register Addresses
# =====================================================================
DHCSR_ADDR = 0xE000EDF0  # Debug Halting Control and Status Register
DEMCR_ADDR = 0xE000EDFC  # Debug Exception and Monitor Control Register

# =====================================================================
# DHCSR Bit Definitions (Bit Position -> (Label, Description))
# =====================================================================
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

# =====================================================================
# DEMCR Bit Definitions (Bit Position -> (Label, Description))
# =====================================================================
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

# =====================================================================
# STM32 Option Bytes & RDP (Readout Protection) Constants
# =====================================================================
STM32F1_OB_BASE = 0x1FFFF800
STM32F1_RDP_KEY_LEVEL_0 = 0xA5  # Readout protection unlocked
STM32F1_RDP_KEY_LEVEL_1 = 0x00  # Any value other than 0xA5 locks flash reading
