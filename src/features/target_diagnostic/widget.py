"""
UI component for Target Diagnostics.
Displays hardware probe serial, MCU part number, DPIDR, RDP lock state,
and ARM Cortex-M core debug status flags with fixed vertical layout.
"""

from typing import Optional, Dict, Any
from PySide6.QtCore import Qt, QThread, Slot, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QPushButton,
    QLabel,
    QTextEdit,
    QScrollArea,
    QFrame,
    QComboBox,
)

from src.common.logger import get_logger
from src.features.target_diagnostic.worker import TargetDiagnosticWorker
from PySide6.QtWidgets import QFileDialog, QMessageBox, QGroupBox, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel
from src.features.target_diagnostic.firmware_update_service import ProbeFirmwareUpdateService

logger = get_logger("TargetDiagnosticWidget")


class TargetDiagnosticWidget(QWidget):
    """
    Industrial diagnostic panel representing physical SWD/USB connection status,
    target identification, RDP protection state, and Cortex-M hardware registers.
    """

    # 🌟 سیگنال در جای درست (سطح کلاس) تعریف شد
    interface_changed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._probe_thread: Optional[QThread] = None
        self._probe_worker: Optional[TargetDiagnosticWorker] = None

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet(
            "QScrollArea { border: none; background-color: transparent; }")

        scroll_content = QWidget()
        main_layout = QVBoxLayout(scroll_content)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(10)

        # -------------------------------------------------------------
        # 1. Target Connection Group
        # -------------------------------------------------------------
        connection_group = QGroupBox("Target Connection & Identity")
        connection_layout = QVBoxLayout()
        connection_layout.setSpacing(10)

        # Status Banner
        self.lbl_status = QLabel("Status: DISCONNECTED")
        self.lbl_status.setStyleSheet(
            "color: #E74C3C; font-weight: bold; font-size: 12px;")
        connection_layout.addWidget(self.lbl_status)

        # =============================================================
        # بخش منوی کشویی برای انتخاب نوع رابط
        # =============================================================
        iface_layout = QHBoxLayout()
        lbl_iface = QLabel("Interface:")
        lbl_iface.setStyleSheet(
            "color: #CCCCCC; font-weight: bold; font-size: 11px;")

        self.cmb_interface = QComboBox()
        self.cmb_interface.addItems(["DAPLink (SWD)", "Direct USB (DFU)"])
        self.cmb_interface.setStyleSheet(
            """
            QComboBox {
                background-color: #2D2D30;
                color: #FFFFFF;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 4px 8px;
                font-family: 'Segoe UI';
                font-size: 11px;
            }
            QComboBox:hover {
                border: 1px solid #007ACC;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #1E1E1E;
                color: #FFFFFF;
                selection-background-color: #007ACC;
            }
            """
        )

        # 🌟 اتصال درست: اول QComboBox ساخته شد، حالا متصلش می‌کنیم
        self.cmb_interface.currentTextChanged.connect(
            self._on_interface_changed)

        iface_layout.addWidget(lbl_iface)
        iface_layout.addWidget(self.cmb_interface, stretch=1)
        connection_layout.addLayout(iface_layout)
        # =============================================================

        # Action Buttons
        btn_layout = QHBoxLayout()
        self.btn_refresh = QPushButton("🔄 Refresh Target")
        self.btn_refresh.setToolTip("Detect MCU via selected interface")
        self.btn_refresh.clicked.connect(self.on_refresh_clicked)

        self.btn_inspect = QPushButton("🔍 Inspect Core")
        self.btn_inspect.setToolTip("Read low-level status bits")
        self.btn_inspect.clicked.connect(self.on_inspect_clicked)

        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addWidget(self.btn_inspect)
        connection_layout.addLayout(btn_layout)

        # Separator Line
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: #333333;")
        connection_layout.addWidget(line)

        # Bottom Metadata Display
        meta_layout = QVBoxLayout()
        meta_layout.setSpacing(6)

        self.lbl_probe_sn = QLabel("Probe SN: N/A")
        self.lbl_part_num = QLabel("MCU: Unknown")
        self.lbl_dpidr = QLabel("DPIDR: N/A")
        self.lbl_rdp = QLabel("RDP State: N/A")

        for lbl in [self.lbl_probe_sn, self.lbl_part_num, self.lbl_dpidr, self.lbl_rdp]:
            lbl.setWordWrap(True)
            lbl.setStyleSheet(
                "font-family: Consolas, monospace; font-size: 11px; color: #D4D4D4;")
            meta_layout.addWidget(lbl)

        connection_layout.addLayout(meta_layout)
        connection_group.setLayout(connection_layout)
        main_layout.addWidget(connection_group)

        # -------------------------------------------------------------
        # 2. Diagnostics Output Display
        # -------------------------------------------------------------
        diag_group = QGroupBox("Core Debug Register Status")
        diag_layout = QVBoxLayout()

        self.txt_diag_display = QTextEdit()
        self.txt_diag_display.setReadOnly(True)
        self.txt_diag_display.setMinimumHeight(160)
        self.txt_diag_display.setStyleSheet(
            "background-color: #1A1A1A; color: #00FF66; "
            "font-family: Consolas, monospace; font-size: 11px;"
        )
        self.txt_diag_display.setPlaceholderText(
            "Click 'Inspect Core' to read status bits...")

        diag_layout.addWidget(self.txt_diag_display)
        diag_group.setLayout(diag_layout)
        main_layout.addWidget(diag_group)

        # -------------------------------------------------------------
        # 3. B-Link Probe Firmware Update Section
        # -------------------------------------------------------------
        probe_fw_box = QGroupBox("B-Link Probe Firmware Update")
        probe_fw_layout = QVBoxLayout()
        probe_fw_layout.setSpacing(10)

        # 1. مسیر فایل و دکمه Browse
        path_layout = QHBoxLayout()
        self.txt_probe_fw_path = QLineEdit()
        self.txt_probe_fw_path.setPlaceholderText(
            "Select firmware binary (.bin)...")
        self.txt_probe_fw_path.setReadOnly(True)
        self.txt_probe_fw_path.setStyleSheet(
            "background-color: #2D2D30; color: #FFFFFF; border: 1px solid #444444; border-radius: 4px; padding: 4px;"
        )

        self.btn_browse_probe_fw = QPushButton("Browse...")
        self.btn_browse_probe_fw.clicked.connect(self._browse_probe_firmware)

        path_layout.addWidget(self.txt_probe_fw_path)
        path_layout.addWidget(self.btn_browse_probe_fw)
        probe_fw_layout.addLayout(path_layout)

        # 2. دکمه شروع آپدیت
        self.btn_update_probe_fw = QPushButton("🔄 UPDATE PROBE FIRMWARE")
        self.btn_update_probe_fw.setFixedHeight(35)
        self.btn_update_probe_fw.setStyleSheet(
            "background-color: #8E44AD; color: white; font-weight: bold; font-size: 11px; border-radius: 4px;"
        )
        self.btn_update_probe_fw.clicked.connect(
            self._start_probe_firmware_update)

        probe_fw_layout.addWidget(self.btn_update_probe_fw)

        probe_fw_box.setLayout(probe_fw_layout)
        main_layout.addWidget(probe_fw_box)

        main_layout.addStretch()
        scroll_area.setWidget(scroll_content)
        layout.addWidget(scroll_area)

    # -----------------------------------------------------------------
    # Signal / Slot Execution Logic
    # -----------------------------------------------------------------
    def _on_interface_changed(self, new_interface: str) -> None:
        """وقتی منوی کشویی تغییر کرد، سیگنال پخش می‌شود."""
        logger.info(f"Global interface switched to: {new_interface}")
        self.interface_changed.emit(new_interface)

    @Slot()
    def on_refresh_clicked(self) -> None:
        selected_iface = self.cmb_interface.currentText()
        self.btn_refresh.setEnabled(False)
        self.btn_inspect.setEnabled(False)
        self.cmb_interface.setEnabled(False)
        self.lbl_status.setText(f"Status: PROBING ({selected_iface})...")
        self.lbl_status.setStyleSheet("color: #F39C12; font-weight: bold;")

        self._probe_thread = QThread()
        self._probe_worker = TargetDiagnosticWorker(
            interface_type=selected_iface)
        self._probe_worker.moveToThread(self._probe_thread)

        self._probe_worker.target_info_signal.connect(
            self._on_target_info_received)
        self._probe_worker.log_signal.connect(self._append_diag_log)

        self._probe_thread.started.connect(self._probe_worker.probe_target)
        self._probe_worker.target_info_signal.connect(self._probe_thread.quit)
        self._probe_worker.target_info_signal.connect(
            self._probe_worker.deleteLater)
        self._probe_thread.finished.connect(self._probe_thread.deleteLater)

        self._probe_thread.start()

    @Slot()
    def on_inspect_clicked(self) -> None:
        selected_iface = self.cmb_interface.currentText()
        self.btn_refresh.setEnabled(False)
        self.btn_inspect.setEnabled(False)
        self.cmb_interface.setEnabled(False)
        self.lbl_status.setText("Status: READING CORE REGISTERS...")
        self.lbl_status.setStyleSheet("color: #F39C12; font-weight: bold;")
        self.txt_diag_display.clear()

        self._probe_thread = QThread()
        self._probe_worker = TargetDiagnosticWorker(
            interface_type=selected_iface)
        self._probe_worker.moveToThread(self._probe_thread)

        self._probe_worker.core_status_signal.connect(
            self._on_core_status_received)
        self._probe_worker.log_signal.connect(self._append_diag_log)

        self._probe_thread.started.connect(self._probe_worker.inspect_core)
        self._probe_worker.core_status_signal.connect(self._probe_thread.quit)
        self._probe_worker.core_status_signal.connect(
            self._probe_worker.deleteLater)
        self._probe_thread.finished.connect(self._probe_thread.deleteLater)

        self._probe_thread.start()

    @Slot(dict)
    def _on_target_info_received(self, info: Dict[str, Any]) -> None:
        self.btn_refresh.setEnabled(True)
        self.btn_inspect.setEnabled(True)
        self.cmb_interface.setEnabled(True)

        if info.get("success"):
            self.lbl_status.setText("Status: CONNECTED / READY")
            self.lbl_status.setStyleSheet("color: #2ECC71; font-weight: bold;")
            self.lbl_probe_sn.setText(
                f"Probe/Device: {info.get('probe_serial', 'N/A')}")
            self.lbl_part_num.setText(
                f"Target: {info.get('part_number', 'ARM_MCU')}")
            self.lbl_dpidr.setText(f"DPIDR/VID: {info.get('dpidr', 'N/A')}")

            rdp_text = info.get("rdp_status", "UNKNOWN")
            self.lbl_rdp.setText(f"RDP State: {rdp_text}")

            if "UNLOCKED" in rdp_text or "LEVEL 0" in rdp_text:
                self.lbl_rdp.setStyleSheet(
                    "font-family: Consolas; font-size: 11px; color: #2ECC71; font-weight: bold;")
            else:
                self.lbl_rdp.setStyleSheet(
                    "font-family: Consolas; font-size: 11px; color: #E74C3C; font-weight: bold;")
        else:
            self.lbl_status.setText("Status: FAULT / NO TARGET")
            self.lbl_status.setStyleSheet("color: #E74C3C; font-weight: bold;")
            err = info.get("error", "Unknown Error")
            self._append_diag_log(f"[ERROR] Detection failed: {err}")

    @Slot(dict)
    def _on_core_status_received(self, status: Dict[str, Any]) -> None:
        self.btn_refresh.setEnabled(True)
        self.btn_inspect.setEnabled(True)
        self.cmb_interface.setEnabled(True)

        if not status.get("success"):
            self.lbl_status.setText("Status: DIAGNOSTIC FAILED")
            self.lbl_status.setStyleSheet("color: #E74C3C; font-weight: bold;")
            err = status.get("error", "Unknown Diagnostic Error")
            self.txt_diag_display.setPlainText(
                f"Failed to inspect target: {err}")
            return

        self.lbl_status.setText("Status: INSPECTION COMPLETE")
        self.lbl_status.setStyleSheet("color: #2ECC71; font-weight: bold;")

        dhcsr_flags = status.get("dhcsr", {})
        demcr_flags = status.get("demcr", {})

        report_lines = [
            f"=== Diagnostics ({self.cmb_interface.currentText()}) ==="]
        if dhcsr_flags:
            is_halted = dhcsr_flags.get("S_HALT", False)
            is_lockup = dhcsr_flags.get("S_LOCKUP", False)
            report_lines.append(
                f"Core State: {'HALTED' if is_halted else 'RUNNING'}")
            if is_lockup:
                report_lines.append("CRITICAL: MCU IS IN S_LOCKUP STATE!")

            set_bits = [k for k, v in dhcsr_flags.items() if v]
            report_lines.append(f"Active Flags: {', '.join(set_bits)}")

        if demcr_flags:
            traps = [k for k, v in demcr_flags.items()
                     if v and k.startswith("VC_")]
            report_lines.append(
                f"Active Traps: {', '.join(traps) if traps else 'None'}")

        self.txt_diag_display.setPlainText("\n".join(report_lines))

    def _append_diag_log(self, message: str) -> None:
        self.txt_diag_display.append(message)

    def shutdown_threads(self) -> None:
        if self._probe_thread and self._probe_thread.isRunning():
            self._probe_thread.quit()
            self._probe_thread.wait()

    # -----------------------------------------------------------------
    # Firmware Update Logic
    # -----------------------------------------------------------------

    def _browse_probe_firmware(self) -> None:
        """Opens file dialog to select B-Link probe firmware binary."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select B-Link Probe Firmware Binary",
            "",
            "Binary Files (*.bin);;Hex Files (*.hex);;All Files (*.*)",
        )
        if file_path:
            self.txt_probe_fw_path.setText(file_path)

    def _start_probe_firmware_update(self) -> None:
        """Executes B-Link probe firmware update routine."""
        fw_path = self.txt_probe_fw_path.text().strip()

        if not fw_path:
            QMessageBox.warning(
                self, "File Warning", "Please select a firmware binary file (.bin) first."
            )
            return

        # پیام راهنما به کاربر برای رفتن به حالت بوت لودر
        reply = QMessageBox.question(
            self,
            "Confirm Probe Update",
            "To update B-Link Probe firmware:\n\n"
            "1. Hold the RESET button on your B-Link Probe.\n"
            "2. Connect it to USB (Drive named 'MAINTENANCE' should appear).\n"
            "3. Click 'Yes' to proceed.\n\n"
            "Are you ready to update?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )

        if reply == QMessageBox.StandardButton.Yes:
            # فراخوانی سرویسی که در گام قبل ساختیم
            success, message = ProbeFirmwareUpdateService.update_firmware(
                fw_path)

            if success:
                QMessageBox.information(self, "Update Successful", message)
                self.txt_probe_fw_path.clear()
            else:
                QMessageBox.critical(self, "Update Failed", message)
