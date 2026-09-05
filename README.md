# B-Link DAPLink Production & Diagnostic Suite

An industrial-grade desktop software suite built for high-throughput firmware flashing, manufacturing automation, hardware testing, and deep-level diagnostics of **ARM Cortex-M** microcontrollers (STM32, NXP LPC, etc.) via **DAPLink / CMSIS-DAP (SWD)** and **USB DFU** interfaces[cite: 1, 2, 6].

Developed with **Python 3.12**, **PySide6 (Qt 6)**, and **pyOCD**, B-Link couples factory-floor flashing capabilities with real-time QA yield analytics, 96-bit hardware UID validation, dynamic CMSIS-Pack management, and end-to-end production traceability[cite: 1, 2, 6].

---

## 🚀 Key Features

### 1. Multi-Interface Hardware Engine
* **DAPLink / CMSIS-DAP (SWD)**: Direct high-speed debugging and programming using pyOCD[cite: 1, 6]. Supports runtime hardware clock frequency adjustments from 100 kHz up to 10 MHz[cite: 1, 6].
* **Native USB DFU Integration**: In-system programming for STM32 targets entering factory bootloader mode, backed by bundled `dfu-util.exe` and `libusb-1.0.dll` runtimes.
* **Non-Intrusive Target Probing**: Real-time identification of Probe Unique ID (SN), DPIDR registers, MCU core family, and device flash layout without halting or resetting running target firmware[cite: 1, 6].
* **Fault-Tolerant Connection Fallback**: Multi-tier connection sequences with automated fallback to generic Cortex-M configurations when encountering locked targets (RDP Level 1) or SWD bus acknowledge drops[cite: 1, 6].
* **Universal CMSIS-Pack Auto-Downloader**: Transparently identifies, resolves, and downloads missing device family packs (`.pack`) from ARM global indexes with automatic CDN failover routing and local cache management[cite: 1, 7].

### 2. High-Throughput Production Programmer
* **Dual Connect Modes**: Configurable connection policies (`under-reset` and `attach`) for secured, blank, or low-power configured hardware targets[cite: 1, 6].
* **Readback Verification**: Automatic post-flash data verification comparing target flash memory against original `.bin` and `.hex` images.
* **Full Chip Erase**: Dedicated low-overhead chip erase routines executing before programming sequences[cite: 1, 6].
* **Pre/Post-Flash Automation Hooks**: Extensible scripting engine running external Python (`.py`), shell (`.sh`), or batch (`.bat`) scripts before and after flash cycles (e.g., relay matrix switching, external sensor validation).

### 3. QA Automation & Traceability
* **Dynamic QA Status Banner**: High-visibility operator feedback banner with instant visual `PASS` / `FAIL` states and color-coded status cues.
* **Live Shift Metrics**: Real-time yield monitoring tracking total cycles, pass counters, fail counters, cycle durations, and live percentage yield.
* **96-bit Hardware UID Reader & Validator**: Automatic readback and integrity screening for factory-programmed STM32 unique chip IDs.
* **Serial Number Provisioning**: Automated serial incrementation and injection into user-defined target flash areas or simulated EEPROM addresses.
* **Traceability Database & CSV Export**: Automated persistent logging of cycle timestamps, chip UIDs, serial numbers, firmware checksums, and QA results into an SQLite database (`production_logs.db`) with one-click CSV report exports.

### 4. Advanced Diagnostics & Tooling
* **Hex / Memory Viewer**: Real-time memory inspection, 8-bit/32-bit block reading, and peripheral register navigation[cite: 1, 2].
* **Option Bytes & Security Management**: Read, configure, and modify MCU Readout Protection (RDP) levels and hardware configuration flags[cite: 1, 2].
* **Parallel Batch Programmer**: Multi-slot probe scanning and coordinated parallel programming engine designed for multi-target factory jigs[cite: 1, 8, 10].
* **CDC Serial Monitor**: Built-in Virtual COM Port (UART) terminal supporting custom baud rates, bidirectional communication, and connection toggling[cite: 1, 6].
* **1-Click Probe Firmware Updater**: Self-updating probe mechanism supporting software-triggered bootloader switching (`START_BL.ACT`), remote JSON configuration polling, and direct binary provisioning via USB mass storage[cite: 4, 8].
* **Silent Application Updater**: Background update daemon detecting newer desktop suite releases with change notification dialogs[cite: 1, 2].

---

## 🏗️ Software Architecture

The software architecture implements a decoupled **Dynamic Worker Pattern** using `QThread` and Qt Signals & Slots to ensure hardware operations (SWD transfers, DFU flashing, USB enumeration) never block the UI rendering pipeline[cite: 1, 2].

```text
B-Link-Programmer/
├── assets/
│   ├── app.ico                    # Application executable icon[cite: 1]
│   ├── master_index.idx           # Cached ARM CMSIS-Pack index database[cite: 1]
│   ├── icons/                     # Vector SVG UI iconography[cite: 1]
│   └── packs/                     # Local offline CMSIS-Pack storage (.pack)[cite: 1]
├── profiles/                      # Manufacturing target & SKU configuration profiles[cite: 1]
├── src/
│   ├── common/
│   │   ├── app_updater.py         # Silent background version checker[cite: 1, 2]
│   │   ├── base_worker.py         # Abstract QThread base worker[cite: 1]
│   │   ├── logger.py              # Centralized rotating file and console logger[cite: 1]
│   │   ├── mcu_profiles.py        # Microcontroller target lookup tables[cite: 1]
│   │   ├── pack_downloader.py     # CMSIS-Pack modal downloader & signal dispatcher[cite: 1, 2]
│   │   ├── paths.py               # Runtime path resolver (sys._MEIPASS aware)[cite: 1, 2]
│   │   ├── profile_manager.py     # SKU JSON profile serialization[cite: 1]
│   │   ├── registers.py           # CoreSight & DBGMCU register address maps[cite: 1]
│   │   ├── resources.py           # Static resource constants & SVG icon paths[cite: 1, 2]
│   │   ├── session_manager.py     # pyOCD / USB DFU low-level session manager[cite: 1]
│   │   ├── status_bar.py          # Real-time hardware status monitor thread[cite: 1, 2]
│   │   └── traceability.py        # SQLite logging & CSV generation service[cite: 1]
│   ├── features/
│   │   ├── batch_programmer/      # Multi-probe parallel flashing engine[cite: 1, 2]
│   │   │   ├── probe_card.py      # Individual target slot widget[cite: 1]
│   │   │   ├── probe_manager.py   # USB probe enumeration and hardware abstraction[cite: 1]
│   │   │   ├── widget.py          # Batch programming UI panel[cite: 1]
│   │   │   └── worker.py          # Multi-threaded batch execution worker[cite: 1, 3]
│   │   ├── memory_viewer/         # Hex memory inspection and register tool[cite: 1, 2]
│   │   ├── option_bytes/          # Option bytes & RDP configuration interface[cite: 1, 2]
│   │   ├── production_programmer/ # Factory flashing, QA banner, and provisioning[cite: 1, 2]
│   │   │   ├── provisioning.py    # Serial auto-incrementing & UID injection[cite: 1]
│   │   │   ├── qa_banner.py       # High-visibility operator status banner[cite: 1]
│   │   │   ├── qa_service.py      # Shift statistics and hardware screening[cite: 1]
│   │   │   ├── verify_service.py  # Image readback verification service[cite: 1]
│   │   │   ├── widget.py          # Production programming view[cite: 1]
│   │   │   └── worker.py          # Flashing, erase, and validation thread[cite: 1]
│   │   ├── script_hooks/          # Pre/Post execution service and config interface[cite: 1]
│   │   ├── serial_monitor/        # CDC UART terminal widget and listener thread[cite: 1, 2]
│   │   └── target_diagnostic/     # Persistent right-side hardware diagnostic panel[cite: 1, 2]
│   └── gui/
│       ├── main_window.py         # 4-pane industrial workspace container[cite: 1, 2]
│       └── sidebar.py             # Collapsible vertical navigation drawer[cite: 1, 2]
├── dfu-util.exe                   # USB DFU flashing runtime engine[cite: 1]
├── libusb-1.0.dll                 # Native dynamic USB communication backend[cite: 1]
├── B-Link-Programmer.spec         # PyInstaller multi-file packaging specification[cite: 1]
├── main.py                        # Application bootstrap entry point[cite: 1, 2]
├── production_logs.db             # Local SQLite traceability audit log database[cite: 1]
└── version.json                   # Application build and release metadata[cite: 1]
---

## ⚙️ Installation & Development Setup

### System Prerequisites
* **Operating System**: Windows 10 / Windows 11 (x64)
* **Python**: Version 3.10 through 3.12[cite: 1]
* **Hardware**: CMSIS-DAP / DAPLink debug probe or direct STM32 USB DFU connection[cite: 1, 2]

### Environment Setup
```bash
# Clone the repository
git clone [https://github.com/your-org/b-link-programmer.git](https://github.com/your-org/b-link-programmer.git)
cd b-link-programmer

# Initialize virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install PySide6 pyocd cmsis-pack-manager libusb-package pyusb hidapi intelhex psutil
Running from Source
python main.py
🛠️ Build & Deployment
1. Build Standalone Portable Directory (PyInstaller)
Compile the source tree into an isolated, relocatable Windows runtime using the project spec file[cite: 1, 11]:
# Clean previous build artifacts
rmdir /s /q build dist

# Compile binaries and assets
pyinstaller B-Link-Programmer.spec --clean
The compiled output will be generated under dist/B-Link-Programmer/.

2. Generate Windows Installer (Setup.exe via Inno Setup)
To package the compiled directory into an installer with desktop shortcuts and uninstallation support:

Open setup_script.iss in Inno Setup Compiler.

Execute Build > Compile (or press F9).

The resulting setup package will be placed in Output/B-Link_Setup_v1.0.exe.
📋 Production Workflow Overview
[Operator Selects Target SKU / Image]
                  │
                  ▼
 [Probe Target & Auto-Detect Architecture] ──(Unknown Part)──► [Generic Cortex-M Fallback]
                  │
                  ▼
 [Execute Pre-Flash Automation Hook Script]
                  │
                  ▼
 [Perform Full Chip Erase & Program Flash]
                  │
                  ▼
 [Run Post-Flash Readback Verification Check]
                  │
                  ▼
 [Read 96-Bit Chip UID & Provision Serial]
                  │
                  ▼
 [Execute Post-Flash Automation Hook Script]
                  │
                  ▼
 [Record Session into SQLite Traceability DB]
                  │
                  ▼
   [Display PASS / FAIL Operator Banner]
📄 License & Maintainers
Proprietary software developed by the BlueWave Embedded Engineering & Robotics Team. All rights reserved.
