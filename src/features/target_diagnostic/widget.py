"""
UI component for Target Diagnostics.
Displays hardware probe serial, MCU part number, DPIDR, RDP lock state,
and ARM Cortex-M core debug status flags.
"""

from typing import Optional, Dict, Any
from PySide6.QtCore import Qt, QThread, Slot
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QPushButton,
    QLabel,
    QTextEdit,
)

from src.common import get_logger
from src.features.target_diagnostic.worker import TargetDiagnosticWorker

logger = get_logger("TargetDiagnosticWidget")


class TargetDiagnosticWidget(QWidget):
    """
    Industrial diagnostic panel representing physical SWD connection status,
    target identification, RDP protection state, and Cortex-M hardware registers.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._probe_thread: Optional[QThread] = None
        self._probe_worker: Optional[TargetDiagnosticWorker] = None

        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # -------------------------------------------------------------
        # Target SWD Connection Group (CubeProgrammer Style)
        # -------------------------------------------------------------
        connection_group = QGroupBox("Target SWD Connection & Identity")
        connection_layout = QVBoxLayout()

        # Top row: Status Banner and Actions
        action_layout = QHBoxLayout()
        self.lbl_status = QLabel("Status: DISCONNECTED")
        self.lbl_status.setStyleSheet("color: #E74C3C; font-weight: bold;")

        self.btn_refresh = QPushButton("🔄 Refresh Target")
        self.btn_refresh.setToolTip(
            "Detect ARM Core, read IDCODE, and check RDP Lock (No Chip Reset)"
        )
        self.btn_refresh.clicked.connect(self.on_refresh_clicked)

        self.btn_inspect = QPushButton("🔍 Inspect Core Registers")
        self.btn_inspect.setToolTip(
            "Read DHCSR & DEMCR core debug registers"
        )
        self.btn_inspect.clicked.connect(self.on_inspect_clicked)

        action_layout.addWidget(self.lbl_status)
        action_layout.addStretch()
        action_layout.addWidget(self.btn_inspect)
        action_layout.addWidget(self.btn_refresh)
        connection_layout.addLayout(action_layout)

        # Bottom row: Hardware ID Metadata (Enhanced with RDP Status)
        meta_layout = QHBoxLayout()
        self.lbl_probe_sn = QLabel("Probe SN: N/A")
        self.lbl_part_num = QLabel("MCU: Unknown")
        self.lbl_dpidr = QLabel("DPIDR: N/A")
        self.lbl_rdp = QLabel("RDP: N/A")

        meta_layout.addWidget(self.lbl_probe_sn)
        meta_layout.addWidget(QLabel(" | "))
        meta_layout.addWidget(self.lbl_part_num)
        meta_layout.addWidget(QLabel(" | "))
        meta_layout.addWidget(self.lbl_dpidr)
        meta_layout.addWidget(QLabel(" | "))
        meta_layout.addWidget(self.lbl_rdp)
        meta_layout.addStretch()
        connection_layout.addLayout(meta_layout)

        connection_group.setLayout(connection_layout)
        main_layout.addWidget(connection_group)

        # -------------------------------------------------------------
        # Diagnostics Output Display (Core Registers Inspection)
        # -------------------------------------------------------------
        diag_group = QGroupBox("Core Debug Register Status (DHCSR / DEMCR)")
        diag_layout = QVBoxLayout()

        self.txt_diag_display = QTextEdit()
        self.txt_diag_display.setReadOnly(True)
        self.txt_diag_display.setMaximumHeight(120)
        self.txt_diag_display.setStyleSheet(
            "background-color: #1A1A1A; color: #00FF66; "
            "font-family: Consolas, monospace; font-size: 11px;"
        )
        self.txt_diag_display.setPlaceholderText(
            "Click 'Inspect Core Registers' to read low-level ARM status bits..."
        )

        diag_layout.addWidget(self.txt_diag_display)
        diag_group.setLayout(diag_layout)
        main_layout.addWidget(diag_group)

    # -----------------------------------------------------------------
    # Signal / Slot Execution Logic
    # -----------------------------------------------------------------
    @Slot()
    def on_refresh_clicked(self) -> None:
        """Trigger asynchronous non-blocking target probe."""
        self.btn_refresh.setEnabled(False)
        self.btn_inspect.setEnabled(False)
        self.lbl_status.setText("Status: PROBING SWD BUS...")
        self.lbl_status.setStyleSheet("color: #F39C12; font-weight: bold;")

        self._probe_thread = QThread()
        self._probe_worker = TargetDiagnosticWorker()
        self._probe_worker.moveToThread(self._probe_thread)

        self._probe_worker.target_info_signal.connect(
            self._on_target_info_received
        )
        self._probe_worker.log_signal.connect(self._append_diag_log)

        self._probe_thread.started.connect(self._probe_worker.probe_target)
        self._probe_worker.target_info_signal.connect(self._probe_thread.quit)
        self._probe_worker.target_info_signal.connect(
            self._probe_worker.deleteLater
        )
        self._probe_thread.finished.connect(self._probe_thread.deleteLater)

        self._probe_thread.start()

    @Slot()
    def on_inspect_clicked(self) -> None:
        """Trigger low-level Cortex-M core register diagnostics."""
        self.btn_refresh.setEnabled(False)
        self.btn_inspect.setEnabled(False)
        self.lbl_status.setText("Status: READING CORE REGISTERS...")
        self.lbl_status.setStyleSheet("color: #F39C12; font-weight: bold;")
        self.txt_diag_display.clear()

        self._probe_thread = QThread()
        self._probe_worker = TargetDiagnosticWorker()
        self._probe_worker.moveToThread(self._probe_thread)

        self._probe_worker.core_status_signal.connect(
            self._on_core_status_received
        )
        self._probe_worker.log_signal.connect(self._append_diag_log)

        self._probe_thread.started.connect(self._probe_worker.inspect_core)
        self._probe_worker.core_status_signal.connect(self._probe_thread.quit)
        self._probe_worker.core_status_signal.connect(
            self._probe_worker.deleteLater
        )
        self._probe_thread.finished.connect(self._probe_thread.deleteLater)

        self._probe_thread.start()

    @Slot(dict)
    def _on_target_info_received(self, info: Dict[str, Any]) -> None:
        """Update GUI labels with identified MCU information and RDP State."""
        self.btn_refresh.setEnabled(True)
        self.btn_inspect.setEnabled(True)

        if info.get("success"):
            self.lbl_status.setText("Status: CONNECTED / READY")
            self.lbl_status.setStyleSheet("color: #2ECC71; font-weight: bold;")

            self.lbl_probe_sn.setText(
                f"Probe SN: {info.get('probe_serial', 'N/A')}"
            )
            self.lbl_part_num.setText(
                f"MCU: {info.get('part_number', 'ARM_MCU')}"
            )
            self.lbl_dpidr.setText(
                f"DPIDR: {info.get('dpidr', '0x2BA01477')}"
            )
            rdp_text = info.get("rdp_status", "UNKNOWN")
            self.lbl_rdp.setText(f"RDP: {rdp_text}")
            if "UNLOCKED" in rdp_text:
                self.lbl_rdp.setStyleSheet(
                    "color: #2ECC71; font-weight: bold;")
            else:
                self.lbl_rdp.setStyleSheet(
                    "color: #E74C3C; font-weight: bold;")
        else:
            self.lbl_status.setText("Status: CONNECTION FAULT / NO TARGET")
            self.lbl_status.setStyleSheet("color: #E74C3C; font-weight: bold;")
            err = info.get("error", "Unknown Error")
            self._append_diag_log(f"[ERROR] Detection failed: {err}")

    @Slot(dict)
    def _on_core_status_received(self, status: Dict[str, Any]) -> None:
        """Format and display decoded ARM debug registers in the console."""
        self.btn_refresh.setEnabled(True)
        self.btn_inspect.setEnabled(True)

        if not status.get("success"):
            self.lbl_status.setText("Status: DIAGNOSTIC FAILED")
            self.lbl_status.setStyleSheet("color: #E74C3C; font-weight: bold;")
            err = status.get("error", "Unknown Diagnostic Error")
            self.txt_diag_display.setPlainText(
                f"Failed to inspect core: {err}"
            )
            return

        self.lbl_status.setText("Status: CORE INSPECTION COMPLETE")
        self.lbl_status.setStyleSheet("color: #2ECC71; font-weight: bold;")

        dhcsr_flags = status.get("dhcsr", {})
        demcr_flags = status.get("demcr", {})

        report_lines = ["=== Cortex-M Core Register Diagnostics ==="]
        if dhcsr_flags:
            is_halted = dhcsr_flags.get("S_HALT", False)
            is_lockup = dhcsr_flags.get("S_LOCKUP", False)
            report_lines.append(
                f"Core State: {'HALTED' if is_halted else 'RUNNING'}"
            )
            if is_lockup:
                report_lines.append("CRITICAL: MCU IS IN S_LOCKUP STATE!")

            set_bits = [k for k, v in dhcsr_flags.items() if v]
            report_lines.append(f"DHCSR Active Bits: {', '.join(set_bits)}")

        if demcr_flags:
            traps = [k for k, v in demcr_flags.items()
                     if v and k.startswith("VC_")]
            report_lines.append(
                f"DEMCR Active Traps: {', '.join(traps) if traps else 'None'}"
            )

        self.txt_diag_display.setPlainText("\n".join(report_lines))

    def _append_diag_log(self, message: str) -> None:
        """Append operational diagnostic log to the terminal."""
        self.txt_diag_display.append(message)

    def shutdown_threads(self) -> None:
        """Safely terminate active diagnostic threads on exit."""
        if self._probe_thread and self._probe_thread.isRunning():
            self._probe_thread.quit()
            self._probe_thread.wait()
