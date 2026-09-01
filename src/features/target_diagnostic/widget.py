
# """
# UI component for Target Diagnostics.
# Displays hardware probe serial, MCU part number, DPIDR, RDP lock state,
# and ARM Cortex-M core debug status flags with fixed vertical layout.
# Supports ST Auto-Detect and Searchable Custom Target selection.
# """
# from src.common.resources import QSS_CHEVRON_DOWN, ICON_ARROWS_ROTATE, ICON_CLOUD_ARROW_DOWN, ICON_MAGNIFYING_GLASS, ICON_HOURGLASS
# from typing import Optional, Dict, Any
# from PySide6.QtCore import Qt, QThread, Slot, Signal, QTimer, QSize
# from PySide6.QtGui import QFont, QColor, QIcon
# from PySide6.QtWidgets import (
#     QWidget,
#     QVBoxLayout,
#     QHBoxLayout,
#     QGroupBox,
#     QPushButton,
#     QLabel,
#     QTextEdit,
#     QFrame,
#     QComboBox,
#     QMessageBox,
#     QApplication,
#     QCompleter,
# )

# from src.common.logger import get_logger
# from src.features.target_diagnostic.worker import TargetDiagnosticWorker
# from src.features.target_diagnostic.firmware_update_service import (
#     ProbeFirmwareUpdateService,
#     FirmwareUpdateWorker,
# )
# from src.common.pack_downloader import DownloadSignalBus
# from src.common.resources import QSS_CHEVRON_DOWN, ICON_ARROWS_ROTATE, ICON_CLOUD_ARROW_DOWN, ICON_MAGNIFYING_GLASS, ICON_HOURGLASS, ICON_CHEVRON_DOWN
# from pyocd.target import TARGET
# logger = get_logger("TargetDiagnosticWidget")

# # فهرست پرکاربردترین میکروهای غیر ST جهت جستجوی سریع در ComboBox
# POPULAR_NON_ST_TARGETS = [
#     "cortex_m (Generic Cortex-M)",
#     "gd32f103c8 (GigaDevice)",
#     "gd32f303cg (GigaDevice)",
#     "gd32f450zk (GigaDevice)",
#     "nrf52840 (Nordic)",
#     "nrf52832 (Nordic)",
#     "nrf5340 (Nordic)",
#     "lpc1768 (NXP)",
#     "lpc55s69 (NXP)",
#     "atsamd21g18a (Microchip/Atmel)",
#     "atsame54p20 (Microchip/Atmel)",
#     "rp2040 (Raspberry Pi)",
#     "ch32f103c8 (WCH)",
#     "ch32v307 (WCH)",
#     "efm32g890f128 (Silicon Labs)",
#     "msp432p401r (Texas Instruments)",
# ]


# class TargetDiagnosticWidget(QWidget):
#     """
#     Industrial diagnostic panel representing physical SWD/USB connection status,
#     target identification, RDP protection state, and Cortex-M hardware registers.
#     """

#     interface_changed = Signal(str)
#     # سیگنال اعلام تغییر میکروی هدف به سایر بخش‌ها
#     target_changed = Signal(str)

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

#         bus = DownloadSignalBus.instance()
#         bus.download_preparing.connect(self._on_pack_download_started)
#         bus.download_started.connect(self._on_pack_download_started)
#         bus.download_finished.connect(self._on_pack_download_finished)

#     def _apply_styles(self) -> None:
#         """Applies unified industrial styles with minimal, strict color palette."""
#         chevron_path = ICON_CHEVRON_DOWN.replace("\\", "/")
#         self.setStyleSheet(
#             """
#         QGroupBox {
#             background-color: #0C1327;
#             border: 1px solid #1A2642;
#             border-radius: 6px;
#             margin-top: 14px;
#             font-size: 12px;
#             font-weight: bold;
#             color: #00E5FF;
#         }
#         QGroupBox::title {
#             subcontrol-origin: margin;
#             subcontrol-position: top left;
#             left: 0px;
#             padding: 0 6px;
#             background-color: transparent;
#         }
#         QPushButton {
#             background-color: #121D38;
#             color: white;
#             border: 1px solid #1A2642;
#             border-radius: 4px;
#             padding: 8px 12px;
#             font-weight: bold;
#             font-size: 11px;
#         }
#         QPushButton:hover {
#             background-color: #00B4D8;
#             border: 1px solid #00B4D8;
#         }
#         QPushButton:pressed {
#             background-color: #0077B6;
#         }
#         QPushButton:disabled {
#             background-color: #070B19;
#             color: #475569;
#             border: 1px dashed #1A2642;
#         }
#         QLabel {
#             color: #E2E8F0;
#             background-color: transparent;
#         }
#         QComboBox {
#             background-color: #0C1327;
#             color: #F8FAFC;
#             border: 1px solid #1A2642;
#             border-radius: 4px;
#             padding: 4px 10px;
#             font-family: 'Segoe UI';
#             font-size: 12px;
#             font-weight: bold;
#         }
#         QComboBox:hover {
#             border: 1px solid #00E5FF;
#         }
#         QComboBox::drop-down {
#             subcontrol-origin: padding;
#             subcontrol-position: top right;
#             width: 22px;
#             border-left: 1px solid #1A2642;
#         }
#         QComboBox::down-arrow {
#             image: url(%s);
#             width: 10px;
#             height: 10px;
#         }
#         QComboBox QAbstractItemView {
#             background-color: #0C1327;
#             color: #F8FAFC;
#             border: 1px solid #1A2642;
#             selection-background-color: #00E5FF;
#             selection-color: #070B19;
#         }
#         """ % chevron_path
#         )

#     def _init_ui(self) -> None:
#         main_layout = QVBoxLayout(self)
#         main_layout.setContentsMargins(12, 12, 12, 12)
#         main_layout.setSpacing(14)

#         # -------------------------------------------------------------
#         # 1. Target Connection Group
#         # -------------------------------------------------------------
#         connection_group = QGroupBox("Target & Interface Control")
#         connection_layout = QVBoxLayout()
#         connection_layout.setSpacing(10)

#         self.lbl_status = QLabel("Status: DISCONNECTED")
#         self.lbl_status.setStyleSheet(
#             "background-color: transparent; color: #EF4444; font-weight: bold; font-size: 13px;")
#         connection_layout.addWidget(self.lbl_status)

#         # انتخاب Interface
#         iface_layout = QHBoxLayout()
#         lbl_iface = QLabel("Interface:")
#         lbl_iface.setStyleSheet(
#             "background-color: transparent; color: #94A3B8; font-weight: bold; font-size: 11px;")
#         self.cmb_interface = QComboBox()
#         self.cmb_interface.addItems(["B-Link (SWD)", "Direct USB (DFU)"])
#         self.cmb_interface.currentTextChanged.connect(
#             self._on_interface_changed)
#         iface_layout.addWidget(lbl_iface)
#         iface_layout.addWidget(self.cmb_interface, stretch=1)
#         connection_layout.addLayout(iface_layout)

#         # 🌟 انتخاب Vendor / Family Mode (ST Auto یا Manual Search)
#         vendor_layout = QHBoxLayout()
#         lbl_vendor = QLabel("MCU Mode:")
#         lbl_vendor.setStyleSheet(
#             "background-color: transparent; color: #94A3B8; font-weight: bold; font-size: 11px;")
#         self.cmb_vendor_mode = QComboBox()
#         self.cmb_vendor_mode.addItems([
#             "STMicroelectronics (Smart Auto-Detect)",
#             "Other Vendors (Searchable / Manual)"
#         ])
#         self.cmb_vendor_mode.currentIndexChanged.connect(
#             self._on_vendor_mode_changed)
#         vendor_layout.addWidget(lbl_vendor)
#         vendor_layout.addWidget(self.cmb_vendor_mode, stretch=1)
#         connection_layout.addLayout(vendor_layout)

#         # 🌟 ComboBox قابل سرچ برای انتخاب دستی بردهای غیر ST
#         self.target_search_layout = QHBoxLayout()
#         lbl_target_select = QLabel("Target MCU:")
#         lbl_target_select.setStyleSheet(
#             "background-color: transparent; color: #94A3B8; font-weight: bold; font-size: 11px;")

#         self.cmb_target_search = QComboBox()
#         self.cmb_target_search.setEditable(True)
#         self.cmb_target_search.setInsertPolicy(QComboBox.NoInsert)
#         self.cmb_target_search.addItems(POPULAR_NON_ST_TARGETS)

#         # فعال‌سازی جستجوی لحظه‌ای (Filter Substring Search)
#         completer = QCompleter(POPULAR_NON_ST_TARGETS, self.cmb_target_search)
#         completer.setFilterMode(Qt.MatchContains)
#         completer.setCaseSensitivity(Qt.CaseInsensitive)
#         self.cmb_target_search.setCompleter(completer)
#         self.cmb_target_search.currentTextChanged.connect(
#             self._on_target_selection_changed)

#         self.target_search_layout.addWidget(lbl_target_select)
#         self.target_search_layout.addWidget(self.cmb_target_search, stretch=1)

#         # ساخت فریم نگهدارنده بخش جستجو برای نمایش/مخفی‌سازی آسان
#         self.target_search_container = QWidget()
#         self.target_search_container.setLayout(self.target_search_layout)
#         # به صورت پیش‌فرض در حالت ST مخفی است
#         self.target_search_container.setVisible(False)
#         connection_layout.addWidget(self.target_search_container)

#         # Action Buttons
#         btn_layout = QHBoxLayout()
#         self.btn_refresh = QPushButton(" Refresh Target")
#         self.btn_refresh.setIcon(QIcon(ICON_ARROWS_ROTATE))
#         self.btn_refresh.setIconSize(QSize(14, 14))
#         self.btn_refresh.clicked.connect(self.on_refresh_clicked)

#         self.btn_inspect = QPushButton(" Inspect Core")
#         self.btn_inspect.setIcon(QIcon(ICON_MAGNIFYING_GLASS))
#         self.btn_inspect.setIconSize(QSize(14, 14))
#         self.btn_inspect.clicked.connect(self.on_inspect_clicked)

#         btn_layout.addWidget(self.btn_refresh)
#         btn_layout.addWidget(self.btn_inspect)
#         connection_layout.addLayout(btn_layout)

#         line = QFrame()
#         line.setFrameShape(QFrame.Shape.HLine)
#         line.setStyleSheet("background-color: #1A2642;")
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
#                 "font-family: Consolas, monospace; font-size: 11px; color: #94A3B8;")
#             meta_layout.addWidget(lbl)

#         connection_layout.addLayout(meta_layout)
#         connection_group.setLayout(connection_layout)
#         main_layout.addWidget(connection_group)

#         # -------------------------------------------------------------
#         # 2. Diagnostics Output Display (Terminal)
#         # -------------------------------------------------------------
#         diag_group = QGroupBox("Core Debug Register Status")
#         diag_layout = QVBoxLayout()

#         self.txt_diag_display = QTextEdit()
#         self.txt_diag_display.setReadOnly(True)
#         self.txt_diag_display.setStyleSheet(
#             """
#             QTextEdit {
#                 background-color: #03060E;
#                 color: #00FF66;
#                 border: 1px solid #1A2642;
#                 border-radius: 4px;
#                 font-family: 'Consolas', 'Courier New', monospace;
#                 font-size: 12px;
#                 padding: 6px;
#             }
#             """
#         )
#         self.txt_diag_display.setPlaceholderText(
#             "Click 'Inspect Core' to read status bits...")
#         diag_layout.addWidget(self.txt_diag_display)
#         diag_group.setLayout(diag_layout)

#         main_layout.addWidget(diag_group, stretch=1)

#         # -------------------------------------------------------------
#         # 3. B-Link Probe Firmware Update (Cloud OTA)
#         # -------------------------------------------------------------
#         probe_fw_box = QGroupBox("B-Link Probe Firmware Update")
#         probe_fw_layout = QVBoxLayout()
#         probe_fw_layout.setSpacing(10)

#         self.btn_online_update = QPushButton(" ONE-CLICK ONLINE UPDATE")
#         self.btn_online_update.setIcon(QIcon(ICON_CLOUD_ARROW_DOWN))
#         self.btn_online_update.setIconSize(QSize(16, 16))
#         self.btn_online_update.setFixedHeight(42)
#         self.btn_online_update.clicked.connect(self._start_online_update)

#         probe_fw_layout.addWidget(self.btn_online_update)
#         probe_fw_box.setLayout(probe_fw_layout)

#         main_layout.addWidget(probe_fw_box)

#     # -----------------------------------------------------------------
#     # Signal / Slot Execution Logic
#     # -----------------------------------------------------------------

#     def _on_vendor_mode_changed(self, index: int) -> None:
#         """سویچ بین حالت Auto-Detect برای ST و انتخاب دستی سایر بردها."""
#         is_manual = (index == 1)
#         self.target_search_container.setVisible(is_manual)

#         target_name = self.get_selected_mcu_target()
#         logger.info(
#             f"MCU Selection Mode changed: index={index}, target='{target_name}'")
#         self.target_changed.emit(target_name)

#     def _on_target_selection_changed(self, text: str) -> None:
#         target_name = self.get_selected_mcu_target()
#         self.target_changed.emit(target_name)

#     def get_selected_mcu_target(self) -> str:
#         if self.cmb_vendor_mode.currentIndex() == 0:
#             return "auto"
#         else:
#             raw_text = self.cmb_target_search.currentText().strip()
#             # جدا کردن نام اصلی از توضیحات داخل پرانتز (مثلا "gd32f103c8 (GigaDevice)" -> "gd32f103c8")
#             clean_target = raw_text.split(
#             )[0].lower() if raw_text else "cortex_m"
#             return clean_target

#     def _on_interface_changed(self, new_interface: str) -> None:
#         logger.info(f"Global interface switched to: {new_interface}")
#         self.interface_changed.emit(new_interface)

#     @Slot(bool, str, str)
#     def on_global_probe_status_changed(self, connected: bool, probe_name: str, probe_uid: str) -> None:
#         if connected:
#             self.btn_refresh.setEnabled(True)
#             self.btn_inspect.setEnabled(True)
#             self.cmb_interface.setEnabled(True)

#             current_status = self.lbl_status.text()
#             if "DISCONNECTED" in current_status or "FAULT" in current_status or "LOCKED" in current_status:
#                 self.lbl_status.setText("Status: HARDWARE READY")
#                 self.lbl_status.setStyleSheet(
#                     "background-color: transparent; color: #10B981; font-weight: bold; font-size: 13px;")
#                 self._append_diag_log(
#                     "\n[INFO] B-Link probe connected. Click 'Refresh Target' to scan MCU.")
#         else:
#             self.btn_refresh.setEnabled(True)
#             self.btn_inspect.setEnabled(False)
#             self.cmb_interface.setEnabled(True)

#             self.lbl_status.setText("Status: DISCONNECTED")
#             self.lbl_status.setStyleSheet(
#                 "background-color: transparent; color: #EF4444; font-weight: bold; font-size: 13px;")

#             self.lbl_probe_sn.setText("Probe/Device: N/A")
#             self.lbl_part_num.setText("Target: Unknown")
#             self.lbl_dpidr.setText("DPIDR/VID: N/A")
#             self.lbl_rdp.setText("RDP State: N/A")

#     @Slot()
#     def _on_hardware_timeout(self) -> None:
#         QApplication.restoreOverrideCursor()
#         self.shutdown_threads()

#         self.btn_refresh.setEnabled(True)
#         self.btn_inspect.setEnabled(True)
#         self.cmb_interface.setEnabled(True)
#         self.btn_refresh.setText(" Refresh Target")
#         self.btn_inspect.setText(" Inspect Core")

#         self.lbl_status.setText("Status: USB BUS HUNG / TIMEOUT")
#         self.lbl_status.setStyleSheet(
#             "background-color: transparent; color: #EF4444; font-weight: bold; font-size: 13px;")

#         self.txt_diag_display.clear()
#         QMessageBox.critical(
#             self,
#             "Critical Error: USB Timeout",
#             "USB interface stopped responding.\n\nSOLUTION: Unplug the USB cable and plug it back in."
#         )

#     @Slot()
#     def on_refresh_clicked(self) -> None:
#         selected_iface = self.cmb_interface.currentText()
#         selected_target = self.get_selected_mcu_target()

#         self.btn_refresh.setEnabled(False)
#         self.btn_inspect.setEnabled(False)
#         self.cmb_interface.setEnabled(False)

#         self.btn_refresh.setIcon(QIcon(ICON_HOURGLASS))
#         self.btn_refresh.setText(" PROBING...")

#         QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

#         self.lbl_status.setText(f"Status: PROBING ({selected_iface})...")
#         self.lbl_status.setStyleSheet(
#             "background-color: transparent; color: #00E5FF; font-weight: bold; font-size: 13px;")

#         self._watchdog_timer.start(6500)

#         self._probe_thread = QThread()
#         self._probe_worker = TargetDiagnosticWorker(
#             interface_type=selected_iface,
#             target_type=selected_target
#         )
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
#         selected_target = self.get_selected_mcu_target()

#         self.btn_refresh.setEnabled(False)
#         self.btn_inspect.setEnabled(False)
#         self.cmb_interface.setEnabled(False)

#         self.btn_inspect.setIcon(QIcon(ICON_HOURGLASS))
#         self.btn_inspect.setText(" INSPECTING...")

#         QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

#         self.lbl_status.setText("Status: READING CORE REGISTERS...")
#         self.lbl_status.setStyleSheet(
#             "background-color: transparent; color: #00E5FF; font-weight: bold; font-size: 13px;")
#         self.txt_diag_display.clear()

#         self._watchdog_timer.start(6500)

#         self._probe_thread = QThread()
#         self._probe_worker = TargetDiagnosticWorker(
#             interface_type=selected_iface,
#             target_type=selected_target
#         )
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
#         self.btn_refresh.setText(" Refresh Target")
#         self.btn_inspect.setText(" Inspect Core")
#         self.btn_refresh.setIcon(QIcon(ICON_ARROWS_ROTATE))
#         self.btn_inspect.setIcon(QIcon(ICON_MAGNIFYING_GLASS))

#         if info.get("success"):
#             self.lbl_status.setText("Status: CONNECTED / READY")
#             self.lbl_status.setStyleSheet(
#                 "background-color: transparent; color: #10B981; font-weight: bold; font-size: 13px;")
#             self.lbl_probe_sn.setText(
#                 f"Probe/Device: {info.get('probe_serial', 'N/A')}")
#             self.lbl_part_num.setText(
#                 f"Target: {info.get('part_number', 'ARM_MCU')}")
#             self.lbl_dpidr.setText(f"DPIDR/VID: {info.get('dpidr', 'N/A')}")

#             rdp_text = info.get("rdp_status", "UNKNOWN")
#             self.lbl_rdp.setText(f"RDP State: {rdp_text}")

#             if "UNLOCKED" in rdp_text or "LEVEL 0" in rdp_text:
#                 self.lbl_rdp.setStyleSheet(
#                     "background-color: transparent; font-family: Consolas, monospace; font-size: 11px; color: #10B981; font-weight: bold;")
#             else:
#                 self.lbl_rdp.setStyleSheet(
#                     "background-color: transparent; font-family: Consolas, monospace; font-size: 11px; color: #F97316; font-weight: bold;")
#         else:
#             self.lbl_status.setText("Status: FAULT / NO TARGET")
#             self.lbl_status.setStyleSheet(
#                 "background-color: transparent; color: #EF4444; font-weight: bold; font-size: 13px;")

#             self.lbl_probe_sn.setText("Probe/Device: N/A")
#             self.lbl_part_num.setText("Target: Unknown")
#             self.lbl_dpidr.setText("DPIDR/VID: N/A")
#             self.lbl_rdp.setText("RDP State: N/A")

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
#         self.btn_refresh.setText(" Refresh Target")
#         self.btn_inspect.setText(" Inspect Core")

#         if not status.get("success"):
#             self.lbl_status.setText("Status: DIAGNOSTIC FAILED")
#             self.lbl_status.setStyleSheet(
#                 "background-color: transparent; color: #EF4444; font-weight: bold; font-size: 13px;")
#             err = status.get("error", "Unknown Diagnostic Error")
#             self.txt_diag_display.clear()
#             QMessageBox.critical(self, "Inspection Failed",
#                                  f"Failed to inspect target:\n\n{err}")
#             return

#         self.lbl_status.setText("Status: INSPECTION COMPLETE")
#         self.lbl_status.setStyleSheet(
#             "background-color: transparent; color: #10B981; font-weight: bold; font-size: 13px;")

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
#         reply = QMessageBox.question(
#             self,
#             "Confirm Online Update",
#             "This will download the latest B-Link firmware and install it.\nDo NOT unplug the probe during the update.\nProceed?",
#             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
#             QMessageBox.StandardButton.Yes,
#         )
#         if reply != QMessageBox.StandardButton.Yes:
#             return

#         if getattr(self, "_fw_worker", None) and self._fw_worker.isRunning():
#             return

#         self.btn_online_update.setEnabled(False)
#         self.btn_online_update.setIcon(QIcon(ICON_HOURGLASS))
#         self.btn_online_update.setText(" Starting update...")

#         self._fw_worker = FirmwareUpdateWorker(
#             "https://www.bluewaverobotics.ir/app_config.json",
#             parent=self,
#         )
#         self._fw_worker.progress.connect(self._on_update_progress)
#         self._fw_worker.finished_update.connect(self._on_update_finished)
#         self._fw_worker.start()

#     @Slot(str)
#     def _on_update_progress(self, message: str) -> None:
#         self.btn_online_update.setText(f" {message[:45]}")

#     @Slot(bool, str)
#     def _on_update_finished(self, success: bool, message: str) -> None:
#         """Called automatically when the background update finishes."""
#         self.btn_online_update.setText(" ONE-CLICK ONLINE UPDATE")
#         self.btn_online_update.setIcon(QIcon(ICON_CLOUD_ARROW_DOWN))
#         self.btn_online_update.setEnabled(True)

#         if success:
#             if "already up to date" in message:
#                 QMessageBox.information(self, "No Update Needed", message)
#             else:
#                 QMessageBox.information(
#                     self, "Online Update Successful", message)
#         else:
#             QMessageBox.critical(self, "Online Update Failed", message)

#     @Slot(str)
#     def _on_pack_download_started(self, target_name: str) -> None:
#         if hasattr(self, '_watchdog_timer') and self._watchdog_timer.isActive():
#             self._watchdog_timer.stop()

#     @Slot(bool, str)
#     def _on_pack_download_finished(self, success: bool, message: str) -> None:
#         if hasattr(self, '_watchdog_timer'):
#             self._watchdog_timer.start(6500)
"""
UI component for Target Diagnostics.
Displays hardware probe serial, MCU part number, DPIDR, RDP lock state,
and ARM Cortex-M core debug status flags with fixed vertical layout.
Supports ST Auto-Detect and Searchable Custom Target selection.
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
    QCompleter,
)

from src.common.logger import get_logger
from src.features.target_diagnostic.worker import TargetDiagnosticWorker
from src.features.target_diagnostic.firmware_update_service import (
    ProbeFirmwareUpdateService,
    FirmwareUpdateWorker,
)
from src.common.pack_downloader import DownloadSignalBus
from src.common.resources import QSS_CHEVRON_DOWN, ICON_ARROWS_ROTATE, ICON_CLOUD_ARROW_DOWN, ICON_MAGNIFYING_GLASS, ICON_HOURGLASS, ICON_CHEVRON_DOWN

# 🌟 دریافت خودکار لیست تمام قطعات پشتیبانی‌شده از هسته pyOCD
from pyocd.target import TARGET
ALL_SUPPORTED_TARGETS = sorted(list(TARGET.keys()))

logger = get_logger("TargetDiagnosticWidget")


class TargetDiagnosticWidget(QWidget):
    """
    Industrial diagnostic panel representing physical SWD/USB connection status,
    target identification, RDP protection state, and Cortex-M hardware registers.
    """

    interface_changed = Signal(str)
    # سیگنال اعلام تغییر میکروی هدف به سایر بخش‌ها
    target_changed = Signal(str)

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

        bus = DownloadSignalBus.instance()
        bus.download_preparing.connect(self._on_pack_download_started)
        bus.download_started.connect(self._on_pack_download_started)
        bus.download_finished.connect(self._on_pack_download_finished)

    def _apply_styles(self) -> None:
        """Applies unified industrial styles with minimal, strict color palette."""
        chevron_path = ICON_CHEVRON_DOWN.replace("\\", "/")
        self.setStyleSheet(
            """
        QGroupBox {
            background-color: #0C1327;
            border: 1px solid #1A2642;
            border-radius: 6px;
            margin-top: 14px;
            font-size: 12px;
            font-weight: bold;
            color: #00E5FF;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 0px;
            padding: 0 6px;
            background-color: transparent;
        }
        QPushButton {
            background-color: #121D38;
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
            background-color: transparent;
        }
        QComboBox {
            background-color: #0C1327;
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
            width: 22px;
            border-left: 1px solid #1A2642;
        }
        QComboBox::down-arrow {
            image: url(%s);
            width: 10px;
            height: 10px;
        }
        QComboBox QAbstractItemView {
            background-color: #0C1327;
            color: #F8FAFC;
            border: 1px solid #1A2642;
            selection-background-color: #00E5FF;
            selection-color: #070B19;
        }
        """ % chevron_path
        )

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(14)

        # -------------------------------------------------------------
        # 1. Target Connection Group
        # -------------------------------------------------------------
        connection_group = QGroupBox("Target & Interface Control")
        connection_layout = QVBoxLayout()
        connection_layout.setSpacing(10)

        self.lbl_status = QLabel("Status: DISCONNECTED")
        self.lbl_status.setStyleSheet(
            "background-color: transparent; color: #EF4444; font-weight: bold; font-size: 13px;")
        connection_layout.addWidget(self.lbl_status)

        # انتخاب Interface
        iface_layout = QHBoxLayout()
        lbl_iface = QLabel("Interface:")
        lbl_iface.setStyleSheet(
            "background-color: transparent; color: #94A3B8; font-weight: bold; font-size: 11px;")
        self.cmb_interface = QComboBox()
        self.cmb_interface.addItems(["B-Link (SWD)", "Direct USB (DFU)"])
        self.cmb_interface.currentTextChanged.connect(
            self._on_interface_changed)
        iface_layout.addWidget(lbl_iface)
        iface_layout.addWidget(self.cmb_interface, stretch=1)
        connection_layout.addLayout(iface_layout)

        # 🌟 انتخاب Vendor / Family Mode
        vendor_layout = QHBoxLayout()
        lbl_vendor = QLabel("MCU Mode:")
        lbl_vendor.setStyleSheet(
            "background-color: transparent; color: #94A3B8; font-weight: bold; font-size: 11px;")
        self.cmb_vendor_mode = QComboBox()
        self.cmb_vendor_mode.addItems([
            "STMicroelectronics (Smart Auto-Detect)",
            "Other Vendors (Searchable / Manual)"
        ])
        self.cmb_vendor_mode.currentIndexChanged.connect(
            self._on_vendor_mode_changed)
        vendor_layout.addWidget(lbl_vendor)
        vendor_layout.addWidget(self.cmb_vendor_mode, stretch=1)
        connection_layout.addLayout(vendor_layout)

        # 🌟 ComboBox قابل سرچ برای انتخاب دستی با پشتیبانی از دیتابیس کامل
        self.target_search_layout = QHBoxLayout()
        lbl_target_select = QLabel("Target MCU:")
        lbl_target_select.setStyleSheet(
            "background-color: transparent; color: #94A3B8; font-weight: bold; font-size: 11px;")

        self.cmb_target_search = QComboBox()
        self.cmb_target_search.setEditable(True)
        self.cmb_target_search.setInsertPolicy(QComboBox.NoInsert)
        self.cmb_target_search.addItems(ALL_SUPPORTED_TARGETS)

        # فعال‌سازی جستجوی لحظه‌ای (Filter Substring Search)
        completer = QCompleter(ALL_SUPPORTED_TARGETS, self.cmb_target_search)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.cmb_target_search.setCompleter(completer)
        self.cmb_target_search.currentTextChanged.connect(
            self._on_target_selection_changed)

        self.target_search_layout.addWidget(lbl_target_select)
        self.target_search_layout.addWidget(self.cmb_target_search, stretch=1)

        # ساخت فریم نگهدارنده بخش جستجو برای نمایش/مخفی‌سازی آسان
        self.target_search_container = QWidget()
        self.target_search_container.setLayout(self.target_search_layout)
        # به صورت پیش‌فرض در حالت ST مخفی است
        self.target_search_container.setVisible(False)
        connection_layout.addWidget(self.target_search_container)

        # Action Buttons
        btn_layout = QHBoxLayout()
        self.btn_refresh = QPushButton(" Refresh Target")
        self.btn_refresh.setIcon(QIcon(ICON_ARROWS_ROTATE))
        self.btn_refresh.setIconSize(QSize(14, 14))
        self.btn_refresh.clicked.connect(self.on_refresh_clicked)

        self.btn_inspect = QPushButton(" Inspect Core")
        self.btn_inspect.setIcon(QIcon(ICON_MAGNIFYING_GLASS))
        self.btn_inspect.setIconSize(QSize(14, 14))
        self.btn_inspect.clicked.connect(self.on_inspect_clicked)

        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addWidget(self.btn_inspect)
        connection_layout.addLayout(btn_layout)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
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
            }
            """
        )
        self.txt_diag_display.setPlaceholderText(
            "Click 'Inspect Core' to read status bits...")
        diag_layout.addWidget(self.txt_diag_display)
        diag_group.setLayout(diag_layout)

        main_layout.addWidget(diag_group, stretch=1)

        # -------------------------------------------------------------
        # 3. B-Link Probe Firmware Update (Cloud OTA)
        # -------------------------------------------------------------
        probe_fw_box = QGroupBox("B-Link Probe Firmware Update")
        probe_fw_layout = QVBoxLayout()
        probe_fw_layout.setSpacing(10)

        self.btn_online_update = QPushButton(" ONE-CLICK ONLINE UPDATE")
        self.btn_online_update.setIcon(QIcon(ICON_CLOUD_ARROW_DOWN))
        self.btn_online_update.setIconSize(QSize(16, 16))
        self.btn_online_update.setFixedHeight(42)
        self.btn_online_update.clicked.connect(self._start_online_update)

        probe_fw_layout.addWidget(self.btn_online_update)
        probe_fw_box.setLayout(probe_fw_layout)

        main_layout.addWidget(probe_fw_box)

    # -----------------------------------------------------------------
    # Signal / Slot Execution Logic
    # -----------------------------------------------------------------

    def _on_vendor_mode_changed(self, index: int) -> None:
        """سویچ بین حالت Auto-Detect برای ST و انتخاب دستی سایر بردها."""
        is_manual = (index == 1)
        self.target_search_container.setVisible(is_manual)

        target_name = self.get_selected_mcu_target()
        logger.info(
            f"MCU Selection Mode changed: index={index}, target='{target_name}'")
        self.target_changed.emit(target_name)

    def _on_target_selection_changed(self, text: str) -> None:
        target_name = self.get_selected_mcu_target()
        self.target_changed.emit(target_name)

    def get_selected_mcu_target(self) -> str:
        if self.cmb_vendor_mode.currentIndex() == 0:
            return "auto"
        else:
            raw_text = self.cmb_target_search.currentText().strip()
            # جداسازی امن و نرمال‌سازی برای جلوگیری از خطای نام قطعه
            clean_target = raw_text.split(
            )[0].lower() if raw_text else "cortex_m"
            return clean_target

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
                self.lbl_status.setStyleSheet(
                    "background-color: transparent; color: #10B981; font-weight: bold; font-size: 13px;")
                self._append_diag_log(
                    "\n[INFO] B-Link probe connected. Click 'Refresh Target' to scan MCU.")
        else:
            self.btn_refresh.setEnabled(True)
            self.btn_inspect.setEnabled(False)
            self.cmb_interface.setEnabled(True)

            self.lbl_status.setText("Status: DISCONNECTED")
            self.lbl_status.setStyleSheet(
                "background-color: transparent; color: #EF4444; font-weight: bold; font-size: 13px;")

            self.lbl_probe_sn.setText("Probe/Device: N/A")
            self.lbl_part_num.setText("Target: Unknown")
            self.lbl_dpidr.setText("DPIDR/VID: N/A")
            self.lbl_rdp.setText("RDP State: N/A")

    @Slot()
    def _on_hardware_timeout(self) -> None:
        QApplication.restoreOverrideCursor()
        self.shutdown_threads()

        self.btn_refresh.setEnabled(True)
        self.btn_inspect.setEnabled(True)
        self.cmb_interface.setEnabled(True)
        self.btn_refresh.setText(" Refresh Target")
        self.btn_inspect.setText(" Inspect Core")

        self.lbl_status.setText("Status: USB BUS HUNG / TIMEOUT")
        self.lbl_status.setStyleSheet(
            "background-color: transparent; color: #EF4444; font-weight: bold; font-size: 13px;")

        self.txt_diag_display.clear()
        QMessageBox.critical(
            self,
            "Critical Error: USB Timeout",
            "USB interface stopped responding.\n\nSOLUTION: Unplug the USB cable and plug it back in."
        )

    @Slot()
    def on_refresh_clicked(self) -> None:
        selected_iface = self.cmb_interface.currentText()
        selected_target = self.get_selected_mcu_target()

        self.btn_refresh.setEnabled(False)
        self.btn_inspect.setEnabled(False)
        self.cmb_interface.setEnabled(False)

        self.btn_refresh.setIcon(QIcon(ICON_HOURGLASS))
        self.btn_refresh.setText(" PROBING...")

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        self.lbl_status.setText(f"Status: PROBING ({selected_iface})...")
        self.lbl_status.setStyleSheet(
            "background-color: transparent; color: #00E5FF; font-weight: bold; font-size: 13px;")

        self._watchdog_timer.start(6500)

        self._probe_thread = QThread()
        self._probe_worker = TargetDiagnosticWorker(
            interface_type=selected_iface,
            target_type=selected_target
        )
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
        selected_target = self.get_selected_mcu_target()

        self.btn_refresh.setEnabled(False)
        self.btn_inspect.setEnabled(False)
        self.cmb_interface.setEnabled(False)

        self.btn_inspect.setIcon(QIcon(ICON_HOURGLASS))
        self.btn_inspect.setText(" INSPECTING...")

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        self.lbl_status.setText("Status: READING CORE REGISTERS...")
        self.lbl_status.setStyleSheet(
            "background-color: transparent; color: #00E5FF; font-weight: bold; font-size: 13px;")
        self.txt_diag_display.clear()

        self._watchdog_timer.start(6500)

        self._probe_thread = QThread()
        self._probe_worker = TargetDiagnosticWorker(
            interface_type=selected_iface,
            target_type=selected_target
        )
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
        self.btn_refresh.setIcon(QIcon(ICON_ARROWS_ROTATE))
        self.btn_inspect.setIcon(QIcon(ICON_MAGNIFYING_GLASS))

        if info.get("success"):
            self.lbl_status.setText("Status: CONNECTED / READY")
            self.lbl_status.setStyleSheet(
                "background-color: transparent; color: #10B981; font-weight: bold; font-size: 13px;")
            self.lbl_probe_sn.setText(
                f"Probe/Device: {info.get('probe_serial', 'N/A')}")
            self.lbl_part_num.setText(
                f"Target: {info.get('part_number', 'ARM_MCU')}")
            self.lbl_dpidr.setText(f"DPIDR/VID: {info.get('dpidr', 'N/A')}")

            rdp_text = info.get("rdp_status", "UNKNOWN")
            self.lbl_rdp.setText(f"RDP State: {rdp_text}")

            if "UNLOCKED" in rdp_text or "LEVEL 0" in rdp_text:
                self.lbl_rdp.setStyleSheet(
                    "background-color: transparent; font-family: Consolas, monospace; font-size: 11px; color: #10B981; font-weight: bold;")
            else:
                self.lbl_rdp.setStyleSheet(
                    "background-color: transparent; font-family: Consolas, monospace; font-size: 11px; color: #F97316; font-weight: bold;")
        else:
            self.lbl_status.setText("Status: FAULT / NO TARGET")
            self.lbl_status.setStyleSheet(
                "background-color: transparent; color: #EF4444; font-weight: bold; font-size: 13px;")

            self.lbl_probe_sn.setText("Probe/Device: N/A")
            self.lbl_part_num.setText("Target: Unknown")
            self.lbl_dpidr.setText("DPIDR/VID: N/A")
            self.lbl_rdp.setText("RDP State: N/A")

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

        if not status.get("success"):
            self.lbl_status.setText("Status: DIAGNOSTIC FAILED")
            self.lbl_status.setStyleSheet(
                "background-color: transparent; color: #EF4444; font-weight: bold; font-size: 13px;")
            err = status.get("error", "Unknown Diagnostic Error")
            self.txt_diag_display.clear()
            QMessageBox.critical(self, "Inspection Failed",
                                 f"Failed to inspect target:\n\n{err}")
            return

        self.lbl_status.setText("Status: INSPECTION COMPLETE")
        self.lbl_status.setStyleSheet(
            "background-color: transparent; color: #10B981; font-weight: bold; font-size: 13px;")

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
        reply = QMessageBox.question(
            self,
            "Confirm Online Update",
            "This will download the latest B-Link firmware and install it.\nDo NOT unplug the probe during the update.\nProceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if getattr(self, "_fw_worker", None) and self._fw_worker.isRunning():
            return

        self.btn_online_update.setEnabled(False)
        self.btn_online_update.setIcon(QIcon(ICON_HOURGLASS))
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
        self.btn_online_update.setText(f" {message[:45]}")

    @Slot(bool, str)
    def _on_update_finished(self, success: bool, message: str) -> None:
        """Called automatically when the background update finishes."""
        self.btn_online_update.setText(" ONE-CLICK ONLINE UPDATE")
        self.btn_online_update.setIcon(QIcon(ICON_CLOUD_ARROW_DOWN))
        self.btn_online_update.setEnabled(True)

        if success:
            if "already up to date" in message:
                QMessageBox.information(self, "No Update Needed", message)
            else:
                QMessageBox.information(
                    self, "Online Update Successful", message)
        else:
            QMessageBox.critical(self, "Online Update Failed", message)

    @Slot(str)
    def _on_pack_download_started(self, target_name: str) -> None:
        if hasattr(self, '_watchdog_timer') and self._watchdog_timer.isActive():
            self._watchdog_timer.stop()

    @Slot(bool, str)
    def _on_pack_download_finished(self, success: bool, message: str) -> None:
        if hasattr(self, '_watchdog_timer'):
            self._watchdog_timer.start(6500)
