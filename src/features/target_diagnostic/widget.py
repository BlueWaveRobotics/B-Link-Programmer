# """
# UI component for Target Diagnostics.
# Displays hardware probe serial, MCU part number, DPIDR, RDP lock state,
# and ARM Cortex-M core debug status flags with fixed vertical layout.
# """

# from typing import Optional, Dict, Any
# from PySide6.QtCore import Qt, QThread, Slot, Signal, QTimer
# from PySide6.QtWidgets import (
#     QWidget,
#     QVBoxLayout,
#     QHBoxLayout,
#     QGroupBox,
#     QPushButton,
#     QLabel,
#     QTextEdit,
#     QScrollArea,
#     QFrame,
#     QComboBox,
#     QMessageBox,
#     QApplication,
# )

# from src.common.logger import get_logger
# from src.features.target_diagnostic.worker import TargetDiagnosticWorker
# from src.features.target_diagnostic.firmware_update_service import ProbeFirmwareUpdateService

# from src.features.target_diagnostic.firmware_update_service import (
#     ProbeFirmwareUpdateService,
#     FirmwareUpdateWorker,
# )

# logger = get_logger("TargetDiagnosticWidget")


# class TargetDiagnosticWidget(QWidget):
#     """
#     Industrial diagnostic panel representing physical SWD/USB connection status,
#     target identification, RDP protection state, and Cortex-M hardware registers.
#     """

#     interface_changed = Signal(str)

#     def __init__(self, parent: Optional[QWidget] = None):
#         super().__init__(parent)

#         self.setMinimumWidth(380)

#         self._probe_thread: Optional[QThread] = None
#         self._probe_worker: Optional[TargetDiagnosticWorker] = None

#         self._watchdog_timer = QTimer(self)
#         self._watchdog_timer.setSingleShot(True)
#         self._watchdog_timer.timeout.connect(self._on_hardware_timeout)

#         self._init_ui()
#         self._apply_styles()

#     def _apply_styles(self) -> None:
#         """Applies unified industrial styles to the right panel."""
#         self.setStyleSheet(
#             """
#             QGroupBox {
#                 background-color: #1E293B;
#                 border: 1px solid #334155;
#                 border-radius: 6px;
#                 margin-top: 14px;
#                 font-size: 12px;
#                 font-weight: bold;
#                 color: #38BDF8;
#             }
#             QGroupBox::title {
#                 subcontrol-origin: margin;
#                 subcontrol-position: top left;
#                 left: 12px;
#                 padding: 0 6px;
#                 background-color: transparent;
#             }
#             QPushButton {
#                 background-color: #0284C7;
#                 color: white;
#                 border: none;
#                 border-radius: 4px;
#                 padding: 8px 12px;
#                 font-weight: bold;
#                 font-size: 11px;
#             }
#             QPushButton:hover {
#                 background-color: #38BDF8;
#             }
#             QPushButton:pressed {
#                 background-color: #0369A1;
#             }
#             QPushButton:disabled {
#                 background-color: #334155;
#                 color: #94A3B8;
#                 border: 1px dashed #64748B;
#             }
#             QLabel {
#                 color: #E2E8F0;
#             }
#             """
#         )

#     def _init_ui(self) -> None:
#         layout = QVBoxLayout(self)
#         layout.setContentsMargins(0, 0, 0, 0)

#         scroll_area = QScrollArea()
#         scroll_area.setWidgetResizable(True)
#         scroll_area.setHorizontalScrollBarPolicy(
#             Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
#         scroll_area.setStyleSheet(
#             "QScrollArea { border: none; background-color: transparent; }")

#         scroll_content = QWidget()
#         scroll_content.setStyleSheet("background-color: transparent;")
#         main_layout = QVBoxLayout(scroll_content)
#         main_layout.setContentsMargins(12, 12, 12, 12)
#         main_layout.setSpacing(14)

#         # -------------------------------------------------------------
#         # 1. Target Connection Group
#         # -------------------------------------------------------------
#         connection_group = QGroupBox("")
#         connection_layout = QVBoxLayout()
#         connection_layout.setSpacing(12)

#         self.lbl_status = QLabel("Status: DISCONNECTED")
#         self.lbl_status.setStyleSheet(
#             "color: #EF4444; font-weight: bold; font-size: 13px;")
#         connection_layout.addWidget(self.lbl_status)

#         iface_layout = QHBoxLayout()
#         lbl_iface = QLabel("Interface:")
#         lbl_iface.setStyleSheet(
#             "color: #94A3B8; font-weight: bold; font-size: 11px;")

#         self.cmb_interface = QComboBox()
#         self.cmb_interface.addItems(["DAPLink (SWD)", "Direct USB (DFU)"])
#         self.cmb_interface.setStyleSheet(
#             """
#             QComboBox {
#                 background-color: #0F172A;
#                 color: #F8FAFC;
#                 border: 1px solid #475569;
#                 border-radius: 4px;
#                 padding: 4px 10px;
#                 font-family: 'Segoe UI';
#                 font-size: 12px;
#                 font-weight: bold;
#             }
#             QComboBox:hover {
#                 border: 1px solid #38BDF8;
#             }
#             QComboBox::drop-down {
#                 border: none;
#                 width: 24px;
#             }
#             QComboBox QAbstractItemView {
#                 background-color: #0F172A;
#                 color: #F8FAFC;
#                 selection-background-color: #0284C7;
#                 border: 1px solid #475569;
#             }
#             """
#         )

#         self.cmb_interface.currentTextChanged.connect(
#             self._on_interface_changed)

#         iface_layout.addWidget(lbl_iface)
#         iface_layout.addWidget(self.cmb_interface, stretch=1)
#         connection_layout.addLayout(iface_layout)

#         # Action Buttons
#         btn_layout = QHBoxLayout()
#         self.btn_refresh = QPushButton("🔄 Refresh Target")
#         self.btn_refresh.setToolTip("Detect MCU via selected interface")
#         self.btn_refresh.clicked.connect(self.on_refresh_clicked)

#         self.btn_inspect = QPushButton("🔍 Inspect Core")
#         self.btn_inspect.setToolTip("Read low-level status bits")
#         self.btn_inspect.clicked.connect(self.on_inspect_clicked)

#         btn_layout.addWidget(self.btn_refresh)
#         btn_layout.addWidget(self.btn_inspect)
#         connection_layout.addLayout(btn_layout)

#         line = QFrame()
#         line.setFrameShape(QFrame.Shape.HLine)
#         line.setFrameShadow(QFrame.Shadow.Sunken)
#         line.setStyleSheet("background-color: #334155;")
#         connection_layout.addWidget(line)

#         meta_layout = QVBoxLayout()
#         meta_layout.setSpacing(6)

#         self.lbl_probe_sn = QLabel("Probe SN: N/A")
#         self.lbl_part_num = QLabel("MCU: Unknown")
#         self.lbl_dpidr = QLabel("DPIDR: N/A")
#         self.lbl_rdp = QLabel("RDP State: N/A")

#         for lbl in [self.lbl_probe_sn, self.lbl_part_num, self.lbl_dpidr, self.lbl_rdp]:
#             lbl.setWordWrap(True)
#             lbl.setStyleSheet(
#                 "font-family: Consolas, monospace; font-size: 11px; color: #CBD5E1;")
#             meta_layout.addWidget(lbl)

#         connection_layout.addLayout(meta_layout)
#         connection_group.setLayout(connection_layout)
#         main_layout.addWidget(connection_group)

#         # -------------------------------------------------------------
#         # 2. Diagnostics Output Display (Matrix Style Terminal)
#         # -------------------------------------------------------------
#         diag_group = QGroupBox("Core Debug Register Status")
#         diag_layout = QVBoxLayout()

#         self.txt_diag_display = QTextEdit()
#         self.txt_diag_display.setReadOnly(True)
#         self.txt_diag_display.setMinimumHeight(180)
#         self.txt_diag_display.setStyleSheet(
#             """
#             QTextEdit {
#                 background-color: #000000;
#                 color: #00FF41;
#                 border: 1px solid #0F172A;
#                 border-radius: 4px;
#                 font-family: 'Consolas', 'Courier New', monospace;
#                 font-size: 12px;
#                 padding: 6px;
#                 selection-background-color: #27AE60;
#                 selection-color: #000000;
#             }
#             """
#         )
#         self.txt_diag_display.setPlaceholderText(
#             "Click 'Inspect Core' to read status bits...")

#         diag_layout.addWidget(self.txt_diag_display)
#         diag_group.setLayout(diag_layout)
#         main_layout.addWidget(diag_group)

#         # -------------------------------------------------------------
#         # 3. B-Link Probe Firmware Update (Cloud OTA)
#         # -------------------------------------------------------------
#         probe_fw_box = QGroupBox("B-Link Probe Firmware Update")
#         probe_fw_layout = QVBoxLayout()
#         probe_fw_layout.setSpacing(10)

#         self.btn_online_update = QPushButton("🌐 ONE-CLICK ONLINE UPDATE")
#         self.btn_online_update.setFixedHeight(42)
#         self.btn_online_update.setStyleSheet(
#             """
#             QPushButton {
#                 background-color: #059669;
#                 color: white;
#                 font-weight: bold;
#                 font-size: 12px;
#                 border-radius: 4px;
#             }
#             QPushButton:hover { background-color: #10B981; }
#             QPushButton:pressed { background-color: #047857; }
#             QPushButton:disabled { background-color: #334155; color: #94A3B8; border: none; }
#             """
#         )
#         self.btn_online_update.clicked.connect(self._start_online_update)

#         probe_fw_layout.addWidget(self.btn_online_update)
#         probe_fw_box.setLayout(probe_fw_layout)

#         main_layout.addWidget(probe_fw_box)
#         main_layout.addStretch()
#         scroll_area.setWidget(scroll_content)
#         layout.addWidget(scroll_area)

#     # -----------------------------------------------------------------
#     # Signal / Slot Execution Logic
#     # -----------------------------------------------------------------
#     def _on_interface_changed(self, new_interface: str) -> None:
#         logger.info(f"Global interface switched to: {new_interface}")
#         self.interface_changed.emit(new_interface)

#     @Slot(bool, str, str)
#     def on_global_probe_status_changed(self, connected: bool, probe_name: str, probe_uid: str) -> None:
#         """
#         Updates panel state based on global probe connection status.
#         Keep 'Refresh Target' button enabled so user can re-try manually.
#         """
#         if connected:
#             self.btn_refresh.setEnabled(True)
#             self.btn_inspect.setEnabled(True)
#             self.cmb_interface.setEnabled(True)

#             current_status = self.lbl_status.text()
#             if "DISCONNECTED" in current_status or "FAULT" in current_status or "LOCKED" in current_status:
#                 self.lbl_status.setText("Status: HARDWARE READY")
#                 self.lbl_status.setStyleSheet(
#                     "color: #10B981; font-weight: bold; font-size: 13px;")
#                 self._append_diag_log(
#                     "\n[INFO] DAPLink probe connected. Click 'Refresh Target' to scan MCU.")
#         else:
#             # ⬅️ دکمه Refresh فعال می‌ماند تا امکان کلیک مجدد وجود داشته باشد
#             self.btn_refresh.setEnabled(True)
#             self.btn_inspect.setEnabled(False)
#             self.cmb_interface.setEnabled(True)

#             self.lbl_status.setText("Status: DISCONNECTED")
#             self.lbl_status.setStyleSheet(
#                 "color: #EF4444; font-weight: bold; font-size: 13px;")

#             self.lbl_probe_sn.setText("Probe/Device: N/A")
#             self.lbl_part_num.setText("Target: Unknown")
#             self.lbl_dpidr.setText("DPIDR/VID: N/A")
#             self.lbl_rdp.setText("RDP State: N/A")
#             self.lbl_rdp.setStyleSheet(
#                 "font-family: Consolas, monospace; font-size: 11px; color: #CBD5E1;")

#     @Slot()
#     def _on_hardware_timeout(self) -> None:
#         """Executed if hardware operation takes too long and hangs."""
#         QApplication.restoreOverrideCursor()
#         self.shutdown_threads()

#         self.btn_refresh.setEnabled(True)
#         self.btn_inspect.setEnabled(True)
#         self.cmb_interface.setEnabled(True)
#         self.btn_refresh.setText("🔄 Refresh Target")
#         self.btn_inspect.setText("🔍 Inspect Core")

#         self.lbl_status.setText("Status: USB BUS HUNG / TIMEOUT")
#         self.lbl_status.setStyleSheet(
#             "color: #EF4444; font-weight: bold; font-size: 13px;")

#         self.txt_diag_display.clear()
#         QMessageBox.critical(
#             self,
#             "Critical Error: USB Timeout",
#             "USB interface stopped responding.\n\n"
#             "SOLUTION: Unplug the USB cable and plug it back in."
#         )

#     @Slot()
#     def on_refresh_clicked(self) -> None:
#         selected_iface = self.cmb_interface.currentText()

#         self.btn_refresh.setEnabled(False)
#         self.btn_inspect.setEnabled(False)
#         self.cmb_interface.setEnabled(False)
#         self.btn_refresh.setText("⏳ PROBING...")

#         QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

#         self.lbl_status.setText(f"Status: PROBING ({selected_iface})...")
#         self.lbl_status.setStyleSheet(
#             "color: #F59E0B; font-weight: bold; font-size: 13px;")

#         self._watchdog_timer.start(6500)

#         self._probe_thread = QThread()
#         self._probe_worker = TargetDiagnosticWorker(
#             interface_type=selected_iface)
#         self._probe_worker.moveToThread(self._probe_thread)

#         self._probe_worker.target_info_signal.connect(
#             self._on_target_info_received)
#         self._probe_worker.log_signal.connect(self._append_diag_log)

#         self._probe_thread.started.connect(self._probe_worker.probe_target)
#         self._probe_worker.target_info_signal.connect(self._probe_thread.quit)
#         self._probe_worker.target_info_signal.connect(
#             self._probe_worker.deleteLater)
#         self._probe_thread.finished.connect(self._probe_thread.deleteLater)

#         self._probe_thread.start()

#     @Slot()
#     def on_inspect_clicked(self) -> None:
#         selected_iface = self.cmb_interface.currentText()

#         self.btn_refresh.setEnabled(False)
#         self.btn_inspect.setEnabled(False)
#         self.cmb_interface.setEnabled(False)
#         self.btn_inspect.setText("⏳ INSPECTING...")

#         QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

#         self.lbl_status.setText("Status: READING CORE REGISTERS...")
#         self.lbl_status.setStyleSheet(
#             "color: #F59E0B; font-weight: bold; font-size: 13px;")
#         self.txt_diag_display.clear()

#         self._watchdog_timer.start(6500)

#         self._probe_thread = QThread()
#         self._probe_worker = TargetDiagnosticWorker(
#             interface_type=selected_iface)
#         self._probe_worker.moveToThread(self._probe_thread)

#         self._probe_worker.core_status_signal.connect(
#             self._on_core_status_received)
#         self._probe_worker.log_signal.connect(self._append_diag_log)

#         self._probe_thread.started.connect(self._probe_worker.inspect_core)
#         self._probe_worker.core_status_signal.connect(self._probe_thread.quit)
#         self._probe_worker.core_status_signal.connect(
#             self._probe_worker.deleteLater)
#         self._probe_thread.finished.connect(self._probe_thread.deleteLater)

#         self._probe_thread.start()

#     @Slot(dict)
#     def _on_target_info_received(self, info: Dict[str, Any]) -> None:
#         self._watchdog_timer.stop()
#         QApplication.restoreOverrideCursor()

#         self.btn_refresh.setEnabled(True)
#         self.btn_inspect.setEnabled(True)
#         self.cmb_interface.setEnabled(True)
#         self.btn_refresh.setText("🔄 Refresh Target")
#         self.btn_inspect.setText("🔍 Inspect Core")

#         if info.get("success"):
#             self.lbl_status.setText("Status: CONNECTED / READY")
#             self.lbl_status.setStyleSheet(
#                 "color: #10B981; font-weight: bold; font-size: 13px;")
#             self.lbl_probe_sn.setText(
#                 f"Probe/Device: {info.get('probe_serial', 'N/A')}")
#             self.lbl_part_num.setText(
#                 f"Target: {info.get('part_number', 'ARM_MCU')}")
#             self.lbl_dpidr.setText(f"DPIDR/VID: {info.get('dpidr', 'N/A')}")

#             rdp_text = info.get("rdp_status", "UNKNOWN")
#             self.lbl_rdp.setText(f"RDP State: {rdp_text}")

#             if "UNLOCKED" in rdp_text or "LEVEL 0" in rdp_text:
#                 self.lbl_rdp.setStyleSheet(
#                     "font-family: Consolas, monospace; font-size: 11px; color: #10B981; font-weight: bold;")
#             else:
#                 self.lbl_rdp.setStyleSheet(
#                     "font-family: Consolas, monospace; font-size: 11px; color: #EF4444; font-weight: bold;")
#         else:
#             self.lbl_status.setText("Status: FAULT / NO TARGET")
#             self.lbl_status.setStyleSheet(
#                 "color: #EF4444; font-weight: bold; font-size: 13px;")

#             self.lbl_probe_sn.setText("Probe/Device: N/A")
#             self.lbl_part_num.setText("Target: Unknown")
#             self.lbl_dpidr.setText("DPIDR/VID: N/A")
#             self.lbl_rdp.setText("RDP State: N/A")
#             self.lbl_rdp.setStyleSheet(
#                 "font-family: Consolas, monospace; font-size: 11px; color: #CBD5E1;")

#             err = info.get("error", "Unknown Error")
#             self.txt_diag_display.clear()
#             QMessageBox.critical(self, "Detection Failed", err)

#     @Slot(dict)
#     def _on_core_status_received(self, status: Dict[str, Any]) -> None:
#         self._watchdog_timer.stop()
#         QApplication.restoreOverrideCursor()

#         self.btn_refresh.setEnabled(True)
#         self.btn_inspect.setEnabled(True)
#         self.cmb_interface.setEnabled(True)
#         self.btn_refresh.setText("🔄 Refresh Target")
#         self.btn_inspect.setText("🔍 Inspect Core")

#         if not status.get("success"):
#             self.lbl_status.setText("Status: DIAGNOSTIC FAILED")
#             self.lbl_status.setStyleSheet(
#                 "color: #EF4444; font-weight: bold; font-size: 13px;")
#             err = status.get("error", "Unknown Diagnostic Error")
#             self.txt_diag_display.clear()
#             QMessageBox.critical(self, "Inspection Failed",
#                                  f"Failed to inspect target:\n\n{err}")
#             return

#         self.lbl_status.setText("Status: INSPECTION COMPLETE")
#         self.lbl_status.setStyleSheet(
#             "color: #10B981; font-weight: bold; font-size: 13px;")

#         dhcsr_flags = status.get("dhcsr", {})
#         demcr_flags = status.get("demcr", {})

#         report_lines = [
#             f"=== Diagnostics ({self.cmb_interface.currentText()}) ==="]
#         if dhcsr_flags:
#             is_halted = dhcsr_flags.get("S_HALT", False)
#             is_lockup = dhcsr_flags.get("S_LOCKUP", False)
#             report_lines.append(
#                 f"Core State: {'HALTED' if is_halted else 'RUNNING'}")
#             if is_lockup:
#                 report_lines.append("CRITICAL: MCU IS IN S_LOCKUP STATE!")

#             set_bits = [k for k, v in dhcsr_flags.items() if v]
#             report_lines.append(f"Active Flags: {', '.join(set_bits)}")

#         if demcr_flags:
#             traps = [k for k, v in demcr_flags.items()
#                      if v and k.startswith("VC_")]
#             report_lines.append(
#                 f"Active Traps: {', '.join(traps) if traps else 'None'}")

#         self.txt_diag_display.setPlainText("\n".join(report_lines))

#     def _append_diag_log(self, message: str) -> None:
#         self.txt_diag_display.append(message)

#     def shutdown_threads(self) -> None:
#         if hasattr(self, '_watchdog_timer') and self._watchdog_timer.isActive():
#             self._watchdog_timer.stop()

#         if self._probe_thread and self._probe_thread.isRunning():
#             self._probe_thread.terminate()
#             self._probe_thread.wait()

#     @Slot()
#     def _start_online_update(self) -> None:
#         """Triggers 1-Click Online Update (runs in background thread)."""
#         reply = QMessageBox.question(
#             self,
#             "Confirm Online Update",
#             "This will download the latest B-Link firmware and install it.\n"
#             "Do NOT unplug the probe during the update.\nProceed?",
#             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
#             QMessageBox.StandardButton.Yes,
#         )
#         if reply != QMessageBox.StandardButton.Yes:
#             return

#         # جلوگیری از اجرای هم‌زمان دوباره
#         if getattr(self, "_fw_worker", None) and self._fw_worker.isRunning():
#             return

#         self.btn_online_update.setEnabled(False)
#         self.btn_online_update.setText("⏳ Starting update...")

#         self._fw_worker = FirmwareUpdateWorker(
#             "https://www.bluewaverobotics.ir/app_config.json",
#             parent=self,
#         )
#         self._fw_worker.progress.connect(self._on_update_progress)
#         self._fw_worker.finished_update.connect(self._on_update_finished)
#         self._fw_worker.start()

#     @Slot(str)
#     def _on_update_progress(self, message: str) -> None:
#         """Shows current step on the button while updating."""
#         self.btn_online_update.setText(f"⏳ {message[:45]}")

#     @Slot(bool, str)
#     def _on_update_finished(self, success: bool, message: str) -> None:
#         """Called automatically when the background update finishes."""
#         self.btn_online_update.setText("🌐 ONE-CLICK ONLINE UPDATE")
#         self.btn_online_update.setEnabled(True)

#         if success:
#             QMessageBox.information(self, "Online Update Successful", message)
#         else:
#             QMessageBox.critical(self, "Online Update Failed", message)

"""
UI component for Target Diagnostics.
Displays hardware probe serial, MCU part number, DPIDR, RDP lock state,
and ARM Cortex-M core debug status flags with fixed vertical layout.
"""

from typing import Optional, Dict, Any
from PySide6.QtCore import Qt, QThread, Slot, Signal, QTimer, QSize
from PySide6.QtGui import QFont, QColor, QIcon
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QPushButton,
    QLabel,
    QTextEdit,
    QFrame,
    QComboBox,
    QMessageBox,
    QApplication,
)

from src.common.logger import get_logger
from src.features.target_diagnostic.worker import TargetDiagnosticWorker
from src.features.target_diagnostic.firmware_update_service import (
    ProbeFirmwareUpdateService,
    FirmwareUpdateWorker,
)

logger = get_logger("TargetDiagnosticWidget")


class TargetDiagnosticWidget(QWidget):
    """
    Industrial diagnostic panel representing physical SWD/USB connection status,
    target identification, RDP protection state, and Cortex-M hardware registers.
    """

    interface_changed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.setMinimumWidth(380)

        self._probe_thread: Optional[QThread] = None
        self._probe_worker: Optional[TargetDiagnosticWorker] = None

        self._watchdog_timer = QTimer(self)
        self._watchdog_timer.setSingleShot(True)
        self._watchdog_timer.timeout.connect(self._on_hardware_timeout)

        self._init_ui()
        self._apply_styles()

    def _apply_styles(self) -> None:
        """Applies unified industrial styles with minimal, strict color palette."""
        self.setStyleSheet(
            """
            QGroupBox {
                background-color: #0C1327; /* هماهنگ با تم اصلی */
                border: 1px solid #1A2642;
                border-radius: 6px;
                margin-top: 14px;
                font-size: 12px;
                font-weight: bold;
                color: #00E5FF; /* سایان اصلی برنامه */
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 0px;
                padding: 0 6px;
                background-color: transparent;
            }
            QPushButton {
                background-color: #121D38; /* دکمه‌های خنثی */
                color: white;
                border: 1px solid #1A2642;
                border-radius: 4px;
                padding: 8px 12px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #00B4D8;
                border: 1px solid #00B4D8;
            }
            QPushButton:pressed {
                background-color: #0077B6;
            }
            QPushButton:disabled {
                background-color: #070B19;
                color: #475569;
                border: 1px dashed #1A2642;
            }
            QLabel {
                color: #E2E8F0;
            }
            """
        )

    def _init_ui(self) -> None:
        # ⬅️ اسکرول کاملا حذف شد و چیدمان مستقیم روی خود ویجت اعمال می‌شود
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(14)

        # -------------------------------------------------------------
        # 1. Target Connection Group
        # -------------------------------------------------------------
        connection_group = QGroupBox("")
        connection_layout = QVBoxLayout()
        connection_layout.setSpacing(12)

        self.lbl_status = QLabel("Status: DISCONNECTED")
        # قرمز برای حالت قطع بودن
        self.lbl_status.setStyleSheet(
            "color: #EF4444; font-weight: bold; font-size: 13px;")
        connection_layout.addWidget(self.lbl_status)

        iface_layout = QHBoxLayout()
        lbl_iface = QLabel("Interface:")
        lbl_iface.setStyleSheet(
            "color: #94A3B8; font-weight: bold; font-size: 11px;")

        self.cmb_interface = QComboBox()
        self.cmb_interface.addItems(["DAPLink (SWD)", "Direct USB (DFU)"])
        # self.cmb_interface.setStyleSheet(
        #     """
        #     QComboBox {
        #         background-color: #070B19;
        #         color: #F8FAFC;
        #         border: 1px solid #1A2642;
        #         border-radius: 4px;
        #         padding: 4px 10px;
        #         font-family: 'Segoe UI';
        #         font-size: 12px;
        #         font-weight: bold;
        #     }
        #     QComboBox:hover {
        #         border: 1px solid #00E5FF;
        #     }
        #     /* ⬅️ استایل جدید برای قسمت دکمه کشویی */
        #     QComboBox::drop-down {
        #         subcontrol-origin: padding;
        #         subcontrol-position: top right;
        #         width: 26px;
        #         border-left: 1px solid #1A2642; /* خط جداکننده */
        #         background-color: #121D38; /* رنگ متمایز برای دکمه فلش */
        #         border-top-right-radius: 3px;
        #         border-bottom-right-radius: 3px;
        #     }
        #     QComboBox::drop-down:hover {
        #         background-color: #1A2642;
        #     }
        #     """
        # )
        self.cmb_interface.setStyleSheet(
            """
            QComboBox {
                background-color: #070B19;
                color: #F8FAFC;
                border: 1px solid #1A2642;
                border-radius: 4px;
                padding: 4px 10px;
                font-family: 'Segoe UI';
                font-size: 12px;
                font-weight: bold;
            }
            QComboBox:hover {
                border: 1px solid #00E5FF;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 26px;
                border-left: 1px solid #1A2642;
                background-color: #121D38; 
                border-top-right-radius: 3px;
                border-bottom-right-radius: 3px;
            }
            QComboBox::drop-down:hover {
                background-color: #1A2642;
            }
            /* ⬅️ این بخش فلش (Arrow) را به دکمه اضافه می‌کند */
            QComboBox::down-arrow {
                image: url(assets/icons/chevron-down-solid-full.svg); /* آدرس آیکون فلش شما */
                width: 12px;
                height: 12px;
            }
            """
        )
        self.cmb_interface.currentTextChanged.connect(
            self._on_interface_changed)

        iface_layout.addWidget(lbl_iface)
        iface_layout.addWidget(self.cmb_interface, stretch=1)
        connection_layout.addLayout(iface_layout)

        # Action Buttons
        btn_layout = QHBoxLayout()

        # ⬅️ اضافه کردن آیکون‌های SVG برای دکمه‌های کنترل
        self.btn_refresh = QPushButton(" Refresh Target")
        self.btn_refresh.setIcon(
            QIcon("assets/icons/arrows-rotate-solid-full.svg"))  # آدرس SVG
        self.btn_refresh.setIconSize(QSize(14, 14))
        self.btn_refresh.clicked.connect(self.on_refresh_clicked)

        self.btn_inspect = QPushButton(" Inspect Core")
        self.btn_inspect.setIcon(
            QIcon("assets/icons/magnifying-glass-solid-full.svg"))  # آدرس SVG
        self.btn_inspect.setIconSize(QSize(14, 14))
        self.btn_inspect.clicked.connect(self.on_inspect_clicked)

        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addWidget(self.btn_inspect)
        connection_layout.addLayout(btn_layout)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: #1A2642;")
        connection_layout.addWidget(line)

        meta_layout = QVBoxLayout()
        meta_layout.setSpacing(6)

        self.lbl_probe_sn = QLabel("Probe SN: N/A")
        self.lbl_part_num = QLabel("MCU: Unknown")
        self.lbl_dpidr = QLabel("DPIDR: N/A")
        self.lbl_rdp = QLabel("RDP State: N/A")

        for lbl in [self.lbl_probe_sn, self.lbl_part_num, self.lbl_dpidr, self.lbl_rdp]:
            lbl.setWordWrap(True)
            lbl.setStyleSheet(
                "font-family: Consolas, monospace; font-size: 11px; color: #94A3B8;")
            meta_layout.addWidget(lbl)

        connection_layout.addLayout(meta_layout)
        connection_group.setLayout(connection_layout)
        main_layout.addWidget(connection_group)

        # -------------------------------------------------------------
        # 2. Diagnostics Output Display (Terminal)
        # -------------------------------------------------------------
        diag_group = QGroupBox("Core Debug Register Status")
        diag_layout = QVBoxLayout()

        self.txt_diag_display = QTextEdit()
        self.txt_diag_display.setReadOnly(True)
        # ⬅️ رنگ سبز ترمینال ملایم‌تر شد تا در چشم نزند
        self.txt_diag_display.setStyleSheet(
            """
            QTextEdit {
                background-color: #03060E;
                color: #00FF66; 
                border: 1px solid #1A2642;
                border-radius: 4px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                padding: 6px;
                selection-background-color: #0077B6;
                selection-color: #FFFFFF;
            }
            """
        )
        self.txt_diag_display.setPlaceholderText(
            "Click 'Inspect Core' to read status bits...")

        diag_layout.addWidget(self.txt_diag_display)
        diag_group.setLayout(diag_layout)

        # ⬅️ Stretch=1 باعث می‌شود این باکس کل فضای خالی باقی‌مانده عمودی را پر کند
        main_layout.addWidget(diag_group, stretch=1)

        # -------------------------------------------------------------
        # 3. B-Link Probe Firmware Update (Cloud OTA)
        # -------------------------------------------------------------
        probe_fw_box = QGroupBox("B-Link Probe Firmware Update")
        probe_fw_layout = QVBoxLayout()
        probe_fw_layout.setSpacing(10)

        # ⬅️ اضافه کردن SVG به دکمه آپدیت
        self.btn_online_update = QPushButton(" ONE-CLICK ONLINE UPDATE")
        self.btn_online_update.setIcon(
            QIcon("assets/icons/cloud-arrow-down-solid-full.svg"))  # آدرس SVG
        self.btn_online_update.setIconSize(QSize(16, 16))
        self.btn_online_update.setFixedHeight(42)

        # ⬅️ این تنها دکمه‌ای است که سبز ثابت می‌ماند (به معنی اقدام مثبت/بروزرسانی)
        # self.btn_online_update.setStyleSheet(
        #     """
        #     QPushButton {
        #         background-color: #10B981;
        #         color: white;
        #         font-weight: bold;
        #         font-size: 12px;
        #         border-radius: 4px;
        #         border: none;
        #     }
        #     QPushButton:hover { background-color: #059669; }
        #     QPushButton:disabled { background-color: #070B19; color: #475569; border: 1px dashed #1A2642; }
        #     """
        # )
        self.btn_online_update.clicked.connect(self._start_online_update)

        probe_fw_layout.addWidget(self.btn_online_update)
        probe_fw_box.setLayout(probe_fw_layout)

        main_layout.addWidget(probe_fw_box)

    # -----------------------------------------------------------------
    # Signal / Slot Execution Logic
    # -----------------------------------------------------------------

    def _on_interface_changed(self, new_interface: str) -> None:
        logger.info(f"Global interface switched to: {new_interface}")
        self.interface_changed.emit(new_interface)

    @Slot(bool, str, str)
    def on_global_probe_status_changed(self, connected: bool, probe_name: str, probe_uid: str) -> None:
        if connected:
            self.btn_refresh.setEnabled(True)
            self.btn_inspect.setEnabled(True)
            self.cmb_interface.setEnabled(True)

            current_status = self.lbl_status.text()
            if "DISCONNECTED" in current_status or "FAULT" in current_status or "LOCKED" in current_status:
                self.lbl_status.setText("Status: HARDWARE READY")
                # ⬅️ رنگ سبز برای موفقیت
                self.lbl_status.setStyleSheet(
                    "color: #10B981; font-weight: bold; font-size: 13px;")
                self._append_diag_log(
                    "\n[INFO] DAPLink probe connected. Click 'Refresh Target' to scan MCU.")
        else:
            self.btn_refresh.setEnabled(True)
            self.btn_inspect.setEnabled(False)
            self.cmb_interface.setEnabled(True)

            self.lbl_status.setText("Status: DISCONNECTED")
            # ⬅️ رنگ قرمز برای خطا/قطع
            self.lbl_status.setStyleSheet(
                "color: #EF4444; font-weight: bold; font-size: 13px;")

            self.lbl_probe_sn.setText("Probe/Device: N/A")
            self.lbl_part_num.setText("Target: Unknown")
            self.lbl_dpidr.setText("DPIDR/VID: N/A")
            self.lbl_rdp.setText("RDP State: N/A")
            self.lbl_rdp.setStyleSheet(
                "font-family: Consolas, monospace; font-size: 11px; color: #94A3B8;")

    @Slot()
    def _on_hardware_timeout(self) -> None:
        QApplication.restoreOverrideCursor()
        self.shutdown_threads()

        self.btn_refresh.setEnabled(True)
        self.btn_inspect.setEnabled(True)
        self.cmb_interface.setEnabled(True)
        self.btn_refresh.setText(" Refresh Target")
        self.btn_inspect.setText(" Inspect Core")
        self.btn_refresh.setIcon(
            QIcon("assets/icons/arrows-rotate-solid-full.svg"))
        self.btn_inspect.setIcon(
            QIcon("assets/icons/magnifying-glass-solid-full.svg"))

        self.lbl_status.setText("Status: USB BUS HUNG / TIMEOUT")
        # ⬅️ قرمز
        self.lbl_status.setStyleSheet(
            "color: #EF4444; font-weight: bold; font-size: 13px;")

        self.txt_diag_display.clear()
        QMessageBox.critical(
            self,
            "Critical Error: USB Timeout",
            "USB interface stopped responding.\n\n"
            "SOLUTION: Unplug the USB cable and plug it back in."
        )

    @Slot()
    def on_refresh_clicked(self) -> None:
        selected_iface = self.cmb_interface.currentText()

        self.btn_refresh.setEnabled(False)
        self.btn_inspect.setEnabled(False)
        self.cmb_interface.setEnabled(False)

        # ⬅️ استفاده از آیکون SVG ساعت شنی به جای ایموجی
        self.btn_refresh.setIcon(
            QIcon("assets/icons/hourglass-half-solid-full.svg"))
        self.btn_refresh.setText(" PROBING...")

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        self.lbl_status.setText(f"Status: PROBING ({selected_iface})...")
        # ⬅️ جایگزینی زرد/نارنجی با رنگ سایان (تم اصلی) برای نمایش وضعیت "در حال انجام کار"
        self.lbl_status.setStyleSheet(
            "color: #00E5FF; font-weight: bold; font-size: 13px;")

        self._watchdog_timer.start(6500)

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

        # ⬅️ استفاده از آیکون SVG ساعت شنی به جای ایموجی
        self.btn_inspect.setIcon(
            QIcon("assets/icons/hourglass-half-solid-full.svg"))
        self.btn_inspect.setText(" INSPECTING...")

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        self.lbl_status.setText("Status: READING CORE REGISTERS...")
        # ⬅️ سایان برای در حال پردازش
        self.lbl_status.setStyleSheet(
            "color: #00E5FF; font-weight: bold; font-size: 13px;")
        self.txt_diag_display.clear()

        self._watchdog_timer.start(6500)

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
        self._watchdog_timer.stop()
        QApplication.restoreOverrideCursor()

        self.btn_refresh.setEnabled(True)
        self.btn_inspect.setEnabled(True)
        self.cmb_interface.setEnabled(True)
        self.btn_refresh.setText(" Refresh Target")
        self.btn_inspect.setText(" Inspect Core")
        # برگرداندن آیکون ها
        self.btn_refresh.setIcon(
            QIcon("assets/icons/arrows-rotate-solid-full.svg"))
        self.btn_inspect.setIcon(
            QIcon("assets/icons/magnifying-glass-solid-full.svg"))

        if info.get("success"):
            self.lbl_status.setText("Status: CONNECTED / READY")
            # سبز
            self.lbl_status.setStyleSheet(
                "color: #10B981; font-weight: bold; font-size: 13px;")
            self.lbl_probe_sn.setText(
                f"Probe/Device: {info.get('probe_serial', 'N/A')}")
            self.lbl_part_num.setText(
                f"Target: {info.get('part_number', 'ARM_MCU')}")
            self.lbl_dpidr.setText(f"DPIDR/VID: {info.get('dpidr', 'N/A')}")

            rdp_text = info.get("rdp_status", "UNKNOWN")
            self.lbl_rdp.setText(f"RDP State: {rdp_text}")

            if "UNLOCKED" in rdp_text or "LEVEL 0" in rdp_text:
                self.lbl_rdp.setStyleSheet(
                    "font-family: Consolas, monospace; font-size: 11px; color: #10B981; font-weight: bold;")
            else:
                self.lbl_rdp.setStyleSheet(
                    "font-family: Consolas, monospace; font-size: 11px; color: #EF4444; font-weight: bold;")
        else:
            self.lbl_status.setText("Status: FAULT / NO TARGET")
            # قرمز
            self.lbl_status.setStyleSheet(
                "color: #EF4444; font-weight: bold; font-size: 13px;")

            self.lbl_probe_sn.setText("Probe/Device: N/A")
            self.lbl_part_num.setText("Target: Unknown")
            self.lbl_dpidr.setText("DPIDR/VID: N/A")
            self.lbl_rdp.setText("RDP State: N/A")
            self.lbl_rdp.setStyleSheet(
                "font-family: Consolas, monospace; font-size: 11px; color: #94A3B8;")

            err = info.get("error", "Unknown Error")
            self.txt_diag_display.clear()
            QMessageBox.critical(self, "Detection Failed", err)

    @Slot(dict)
    def _on_core_status_received(self, status: Dict[str, Any]) -> None:
        self._watchdog_timer.stop()
        QApplication.restoreOverrideCursor()

        self.btn_refresh.setEnabled(True)
        self.btn_inspect.setEnabled(True)
        self.cmb_interface.setEnabled(True)
        self.btn_refresh.setText(" Refresh Target")
        self.btn_inspect.setText(" Inspect Core")
        self.btn_refresh.setIcon(
            QIcon("assets/icons/arrows-rotate-solid-full.svg"))
        self.btn_inspect.setIcon(
            QIcon("assets/icons/magnifying-glass-solid-full.svg"))

        if not status.get("success"):
            self.lbl_status.setText("Status: DIAGNOSTIC FAILED")
            # قرمز
            self.lbl_status.setStyleSheet(
                "color: #EF4444; font-weight: bold; font-size: 13px;")
            err = status.get("error", "Unknown Diagnostic Error")
            self.txt_diag_display.clear()
            QMessageBox.critical(self, "Inspection Failed",
                                 f"Failed to inspect target:\n\n{err}")
            return

        self.lbl_status.setText("Status: INSPECTION COMPLETE")
        # سبز
        self.lbl_status.setStyleSheet(
            "color: #10B981; font-weight: bold; font-size: 13px;")

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
        if hasattr(self, '_watchdog_timer') and self._watchdog_timer.isActive():
            self._watchdog_timer.stop()

        if self._probe_thread and self._probe_thread.isRunning():
            self._probe_thread.terminate()
            self._probe_thread.wait()

    @Slot()
    def _start_online_update(self) -> None:
        """Triggers 1-Click Online Update (runs in background thread)."""
        reply = QMessageBox.question(
            self,
            "Confirm Online Update",
            "This will download the latest B-Link firmware and install it.\n"
            "Do NOT unplug the probe during the update.\nProceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if getattr(self, "_fw_worker", None) and self._fw_worker.isRunning():
            return

        self.btn_online_update.setEnabled(False)
        # ⬅️ استفاده از آیکون SVG ساعت شنی به جای ایموجی
        self.btn_online_update.setIcon(
            QIcon("assets/icons/hourglass-half-solid-full.svg"))
        self.btn_online_update.setText(" Starting update...")

        self._fw_worker = FirmwareUpdateWorker(
            "https://www.bluewaverobotics.ir/app_config.json",
            parent=self,
        )
        self._fw_worker.progress.connect(self._on_update_progress)
        self._fw_worker.finished_update.connect(self._on_update_finished)
        self._fw_worker.start()

    @Slot(str)
    def _on_update_progress(self, message: str) -> None:
        """Shows current step on the button while updating."""
        # ⬅️ فقط متن را آپدیت می‌کنیم، آیکون ساعت شنی حفظ می‌شود
        self.btn_online_update.setText(f" {message[:45]}")

    @Slot(bool, str)
    def _on_update_finished(self, success: bool, message: str) -> None:
        """Called automatically when the background update finishes."""
        self.btn_online_update.setText(" ONE-CLICK ONLINE UPDATE")
        self.btn_online_update.setIcon(
            # برگرداندن آیکون
            QIcon("assets/icons/cloud-arrow-down-solid-full.svg"))
        self.btn_online_update.setEnabled(True)

        if success:
            QMessageBox.information(self, "Online Update Successful", message)
        else:
            QMessageBox.critical(self, "Online Update Failed", message)
