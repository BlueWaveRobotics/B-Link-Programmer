# """
# Production Programmer Widget for STM32 deployment.
# Provides visual QA PASS/FAIL banner, live shift production statistics,
# 96-bit UID reading, serial number provisioning, and SQLite traceability.
# Now fully supports dynamic SWD / USB DFU interface switching.
# """

# import os
# from PySide6.QtCore import Qt, QThread, Slot
# from PySide6.QtWidgets import (
#     QWidget,
#     QVBoxLayout,
#     QHBoxLayout,
#     QGroupBox,
#     QLabel,
#     QLineEdit,
#     QPushButton,
#     QProgressBar,
#     QFileDialog,
#     QComboBox,
#     QCheckBox,
#     QMessageBox,
# )

# from src.common import get_logger
# from src.common.traceability import TraceabilityDatabase
# from src.features.production_programmer.worker import ProductionProgrammerWorker
# from src.features.production_programmer.provisioning import ProvisioningService
# from src.features.production_programmer.qa_service import QAService
# from src.features.production_programmer.qa_banner import QABannerWidget
# from src.common.profile_manager import ProfileManager, SKUProfile


# logger = get_logger("ProductionProgrammerWidget")


# class ProductionProgrammerWidget(QWidget):
#     """
#     Industrial GUI for firmware deployment, QA validation, and traceability logging.
#     """

#     def __init__(self, parent=None):
#         super().__init__(parent)

#         # 🌟 نگهداری وضعیت نوع اتصال که از سمت منوی اصلی تغییر می‌کند
#         self.current_interface = "DAPLink (SWD)"

#         self.traceability_db = TraceabilityDatabase()
#         self.qa_service = QAService()
#         self.current_uid: str = "UNKNOWN-UID"
#         self.last_cycle_time: float = 0.0
#         self.profile_manager = ProfileManager()

#         self._thread: QThread | None = None
#         self._worker: ProductionProgrammerWorker | None = None

#         self._setup_ui()
#         self._update_statistics_display()

#     # 🌟 متد دریافت دستور تغییر رابط از MainWindow
#     def set_interface_type(self, interface_type: str) -> None:
#         """این متد توسط MainWindow فراخوانی می‌شود تا تغییر رابط اعمال گردد."""
#         self.current_interface = interface_type
#         # می‌توان اینجا متن باکس‌ها را آپدیت کرد، ولی برای سادگی در لاگ ثبت می‌کنیم
#         logger.info(
#             f"ProductionProgrammerWidget interface set to: {self.current_interface}")

#     def _setup_ui(self) -> None:
#         main_layout = QVBoxLayout(self)
#         main_layout.setContentsMargins(16, 16, 16, 16)
#         main_layout.setSpacing(12)

#         # ----------------------------------------------------------------------
#         # 1. Industrial QA Visual Banner
#         # ----------------------------------------------------------------------
#         self.qa_banner = QABannerWidget(self)
#         main_layout.addWidget(self.qa_banner)

#         # ----------------------------------------------------------------------
#         # 2. Live QA Shift Statistics Dashboard
#         # ----------------------------------------------------------------------
#         stats_box = QGroupBox("Production Shift Statistics", self)
#         stats_layout = QHBoxLayout(stats_box)
#         stats_layout.setSpacing(16)

#         self.lbl_stat_pass = QLabel("PASS: 0", self)
#         self.lbl_stat_pass.setStyleSheet(
#             "color: #58D68D; font-weight: bold; font-size: 14px;")

#         self.lbl_stat_fail = QLabel("FAIL: 0", self)
#         self.lbl_stat_fail.setStyleSheet(
#             "color: #EC7063; font-weight: bold; font-size: 14px;")

#         self.lbl_stat_total = QLabel("TOTAL: 0", self)
#         self.lbl_stat_total.setStyleSheet(
#             "font-weight: bold; font-size: 14px;")

#         self.lbl_stat_yield = QLabel("YIELD: 100.0%", self)
#         self.lbl_stat_yield.setStyleSheet(
#             "color: #F4D03F; font-weight: bold; font-size: 14px;")

#         self.btn_reset_stats = QPushButton("Reset Counters", self)
#         self.btn_reset_stats.setFixedWidth(120)
#         self.btn_reset_stats.clicked.connect(self._on_reset_statistics)

#         stats_layout.addWidget(self.lbl_stat_pass)
#         stats_layout.addWidget(self.lbl_stat_fail)
#         stats_layout.addWidget(self.lbl_stat_total)
#         stats_layout.addWidget(self.lbl_stat_yield)
#         stats_layout.addStretch()
#         stats_layout.addWidget(self.btn_reset_stats)

#         main_layout.addWidget(stats_box)

#         # ----------------------------------------------------------------------
#         # 3. Firmware Selection & Base Address
#         # ----------------------------------------------------------------------
#         file_box = QGroupBox("Firmware Image & Memory Address", self)
#         file_layout = QVBoxLayout(file_box)

#         path_layout = QHBoxLayout()
#         self.txt_file_path = QLineEdit(self)
#         self.txt_file_path.setPlaceholderText(
#             "Select firmware binary (.hex, .bin)...")
#         self.txt_file_path.setReadOnly(True)

#         self.btn_browse = QPushButton("Browse...", self)
#         self.btn_browse.clicked.connect(self._browse_firmware)

#         path_layout.addWidget(self.txt_file_path)
#         path_layout.addWidget(self.btn_browse)
#         file_layout.addLayout(path_layout)

#         addr_layout = QHBoxLayout()
#         lbl_addr = QLabel("Base Address (BIN files):", self)
#         self.txt_base_addr = QLineEdit("0x08000000", self)
#         self.txt_base_addr.setFixedWidth(120)

#         self.chk_verify = QCheckBox("Verify after Flash", self)
#         self.chk_verify.setChecked(True)

#         addr_layout.addWidget(lbl_addr)
#         addr_layout.addWidget(self.txt_base_addr)
#         addr_layout.addStretch()
#         addr_layout.addWidget(self.chk_verify)
#         file_layout.addLayout(addr_layout)

#         main_layout.addWidget(file_box)

#         # ----------------------------------------------------------------------
#         # 4. Connection Configuration
#         # ----------------------------------------------------------------------
#         probe_box = QGroupBox("Connection Settings (SWD Modes Only)", self)
#         probe_layout = QHBoxLayout(probe_box)

#         lbl_clock = QLabel("SWD Frequency:", self)
#         self.combo_clock = QComboBox(self)
#         self.combo_clock.addItems(
#             ["4000 kHz", "2000 kHz", "1000 kHz", "500 kHz"])
#         self.combo_clock.setCurrentText("1000 kHz")

#         lbl_mode = QLabel("Connect Mode:", self)
#         self.combo_mode = QComboBox(self)
#         self.combo_mode.addItems(["under-reset", "normal", "attach"])
#         self.combo_mode.setCurrentText("under-reset")

#         probe_layout.addWidget(lbl_clock)
#         probe_layout.addWidget(self.combo_clock)
#         probe_layout.addSpacing(20)
#         probe_layout.addWidget(lbl_mode)
#         probe_layout.addWidget(self.combo_mode)
#         probe_layout.addStretch()

#         main_layout.addWidget(probe_box)

#         # ----------------------------------------------------------------------
#         # 5. Production Provisioning (UID & Serial Injection)
#         # ----------------------------------------------------------------------
#         prov_box = QGroupBox("Hardware Provisioning & Traceability", self)
#         prov_layout = QVBoxLayout(prov_box)

#         uid_layout = QHBoxLayout()
#         lbl_uid = QLabel("Target 96-bit UID:", self)
#         self.txt_uid_display = QLineEdit("NOT-READ", self)
#         self.txt_uid_display.setReadOnly(True)
#         self.txt_uid_display.setStyleSheet(
#             "font-family: Consolas, monospace; font-weight: bold;")

#         uid_layout.addWidget(lbl_uid)
#         uid_layout.addWidget(self.txt_uid_display)
#         prov_layout.addLayout(uid_layout)

#         serial_layout = QHBoxLayout()
#         self.chk_serial_inject = QCheckBox(
#             "Inject Serial Number after Flash", self)
#         self.chk_serial_inject.setChecked(False)

#         lbl_serial = QLabel("Serial:", self)
#         self.txt_serial = QLineEdit("SN-2026-0001", self)
#         self.txt_serial.setFixedWidth(150)

#         lbl_serial_addr = QLabel("Address:", self)
#         self.txt_serial_addr = QLineEdit("0x0801FC00", self)
#         self.txt_serial_addr.setFixedWidth(110)

#         serial_layout.addWidget(self.chk_serial_inject)
#         serial_layout.addStretch()
#         serial_layout.addWidget(lbl_serial)
#         serial_layout.addWidget(self.txt_serial)
#         serial_layout.addWidget(lbl_serial_addr)
#         serial_layout.addWidget(self.txt_serial_addr)
#         prov_layout.addLayout(serial_layout)

#         main_layout.addWidget(prov_box)

#         # ----------------------------------------------------------------------
#         # 6. Progress & Operation Controls
#         # ----------------------------------------------------------------------
#         self.progress_bar = QProgressBar(self)
#         self.progress_bar.setValue(0)
#         self.progress_bar.setTextVisible(True)
#         main_layout.addWidget(self.progress_bar)

#         btn_layout = QHBoxLayout()
#         self.btn_start = QPushButton("⚡ START PROGRAMMING", self)
#         self.btn_start.setFixedHeight(45)
#         self.btn_start.setStyleSheet(
#             "background-color: #2E86C1; color: white; font-weight: bold; font-size: 14px;"
#         )
#         self.btn_start.clicked.connect(self._start_production_flash)

#         self.btn_erase = QPushButton("🗑 FULL CHIP ERASE", self)
#         self.btn_erase.setFixedHeight(45)
#         self.btn_erase.setStyleSheet(
#             "background-color: #C0392B; color: white; font-weight: bold; font-size: 13px;"
#         )
#         self.btn_erase.clicked.connect(self._start_chip_erase)

#         self.btn_export = QPushButton("Export Logs (CSV)", self)
#         self.btn_export.setFixedHeight(45)
#         self.btn_export.clicked.connect(self._export_logs_csv)

#         btn_layout.addWidget(self.btn_start, 3)
#         btn_layout.addWidget(self.btn_erase, 1)
#         btn_layout.addWidget(self.btn_export, 1)

#         main_layout.addLayout(btn_layout)
#         main_layout.addStretch()

#     def _update_statistics_display(self) -> None:
#         """Refreshes QA statistics labels from QAService metrics."""
#         passed, failed, total, yield_pct = self.qa_service.get_statistics()
#         self.lbl_stat_pass.setText(f"PASS: {passed}")
#         self.lbl_stat_fail.setText(f"FAIL: {failed}")
#         self.lbl_stat_total.setText(f"TOTAL: {total}")
#         self.lbl_stat_yield.setText(f"YIELD: {yield_pct:.1f}%")

#     def _on_reset_statistics(self) -> None:
#         """Resets shift pass/fail counters after operator confirmation."""
#         reply = QMessageBox.question(
#             self,
#             "Reset Counters",
#             "Are you sure you want to reset shift production statistics?",
#             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
#             QMessageBox.StandardButton.No,
#         )
#         if reply == QMessageBox.StandardButton.Yes:
#             self.qa_service.reset_statistics()
#             self._update_statistics_display()
#             self.qa_banner.set_ready_state()
#             logger.info("Shift production counters reset to zero.")

#     def _browse_firmware(self) -> None:
#         file_path, _ = QFileDialog.getOpenFileName(
#             self,
#             "Select STM32 Firmware Image",
#             "",
#             "Firmware Files (*.hex *.bin);;All Files (*.*)",
#         )
#         if file_path:
#             self.txt_file_path.setText(os.path.normpath(file_path))

#     def _parse_clock_freq(self) -> int:
#         freq_str = self.combo_clock.currentText().split()[0]
#         return int(freq_str) * 1000

#     def _parse_base_address(self) -> int:
#         return int(self.txt_base_addr.text().strip(), 16)

#     def _parse_serial_address(self) -> int:
#         return int(self.txt_serial_addr.text().strip(), 16)

#     def _set_ui_busy(self, busy: bool) -> None:
#         self.btn_start.setEnabled(not busy)
#         self.btn_erase.setEnabled(not busy)
#         self.btn_browse.setEnabled(not busy)
#         self.btn_export.setEnabled(not busy)
#         if busy:
#             self.progress_bar.setValue(0)
#             self.qa_banner.set_busy_state(
#                 f"Executing hardware sequence via {self.current_interface}...")

#     def _start_production_flash(self) -> None:
#         file_path = self.txt_file_path.text().strip()
#         if not file_path or not os.path.exists(file_path):
#             QMessageBox.warning(self, "File Error",
#                                 "Please select a valid firmware image.")
#             return

#         try:
#             base_addr = self._parse_base_address()
#             clock_freq = self._parse_clock_freq()
#             serial_addr = self._parse_serial_address()
#         except ValueError:
#             QMessageBox.critical(self, "Format Error",
#                                  "Invalid hexadecimal memory address syntax.")
#             return

#         enable_prov = self.chk_serial_inject.isChecked()
#         serial_str = self.txt_serial.text().strip()
#         serial_payload = (
#             ProvisioningService.generate_ascii_serial_payload(serial_str)
#             if enable_prov
#             else []
#         )

#         self._set_ui_busy(True)
#         self.current_uid = "UNKNOWN-UID"
#         self.txt_uid_display.setText("READING...")

#         self._thread = QThread()
#         # 🌟 پاس دادن رابط به ورکر
#         self._worker = ProductionProgrammerWorker(
#             file_path=file_path,
#             base_address=base_addr,
#             clock_freq=clock_freq,
#             connect_mode=self.combo_mode.currentText(),
#             verify_enabled=self.chk_verify.isChecked(),
#             enable_provisioning=enable_prov,
#             serial_payload=serial_payload,
#             serial_address=serial_addr,
#             interface_type=self.current_interface  # ⬅️ اینجا
#         )

#         self._worker.moveToThread(self._thread)
#         self._thread.started.connect(self._worker.run_production_flash)
#         self._worker.progress_signal.connect(self.progress_bar.setValue)
#         self._worker.uid_read_signal.connect(self._on_uid_received)
#         self._worker.cycle_time_signal.connect(self._on_cycle_time_received)
#         self._worker.finished_signal.connect(self._on_operation_finished)
#         self._worker.finished_signal.connect(self._cleanup_thread)

#         self._thread.start()

#     def _start_chip_erase(self) -> None:
#         try:
#             clock_freq = self._parse_clock_freq()
#         except ValueError:
#             return

#         self._set_ui_busy(True)
#         self.qa_banner.set_busy_state("Executing Full Chip Erase...")

#         self._thread = QThread()

#         # در worker.py قبلی شما run_chip_erase تعریف شده بود که ما الان اون را به شکل کامل پشتیبانی میکنیم
#         self._worker = ProductionProgrammerWorker(
#             clock_freq=clock_freq,
#             connect_mode=self.combo_mode.currentText(),
#             interface_type=self.current_interface  # 🌟 ⬅️ این متغیر جدید
#         )

#         self._worker.moveToThread(self._thread)
#         self._thread.started.connect(self._worker.run_chip_erase)
#         self._worker.progress_signal.connect(self.progress_bar.setValue)
#         self._worker.cycle_time_signal.connect(self._on_cycle_time_received)
#         self._worker.finished_signal.connect(self._on_operation_finished)
#         self._worker.finished_signal.connect(self._cleanup_thread)

#         self._thread.start()

#     def _on_uid_received(self, uid_string: str) -> None:
#         """Handles 96-bit Unique ID string emitted by background worker."""
#         self.current_uid = uid_string
#         self.txt_uid_display.setText(uid_string)
#         logger.info(f"Target UID updated in GUI: {uid_string}")

#     def _on_cycle_time_received(self, elapsed_seconds: float) -> None:
#         """Stores execution time of the latest programming cycle."""
#         self.last_cycle_time = elapsed_seconds

#     def _on_operation_finished(self, success: bool, message: str) -> None:
#         self._set_ui_busy(False)
#         firmware_name = os.path.basename(self.txt_file_path.text()) or "N/A"
#         serial_num = self.txt_serial.text().strip(
#         ) if self.chk_serial_inject.isChecked() else None

#         # اعتبارسنجی UID: فقط در حالت SWD که واقعاً خوانده می‌شود
#         if "USB" not in self.current_interface:
#             uid_valid = self.qa_service.is_valid_uid(self.current_uid)
#             final_success = success and uid_valid
#             if not uid_valid and success:
#                 message = "Programming succeeded but target UID validation FAILED."
#         else:
#             # در مد DFU ما UID را ارزیابی نمیکنیم
#             final_success = success
#             self.current_uid = "DFU-DEVICE"

#         self.qa_service.record_result(final_success)
#         self._update_statistics_display()

#         if final_success:
#             self.qa_banner.set_pass_state(
#                 self.last_cycle_time,
#                 f"DEVICE VERIFIED PASS ({self.current_interface})",
#             )
#             status_text = "PASS"
#         else:
#             self.qa_banner.set_fail_state(message, self.last_cycle_time)
#             status_text = "FAIL"

#         self.traceability_db.log_operation(
#             firmware_name=firmware_name,
#             uid_96bit=self.current_uid,
#             serial_number=serial_num,
#             status=status_text,
#             message=message,
#         )

#     def _export_logs_csv(self) -> None:
#         file_path, _ = QFileDialog.getSaveFileName(
#             self,
#             "Export Production Traceability Logs",
#             "production_report.csv",
#             "CSV Files (*.csv)",
#         )
#         if file_path:
#             success = self.traceability_db.export_to_csv(file_path)
#             if success:
#                 QMessageBox.information(
#                     self,
#                     "Export Complete",
#                     f"Production logs exported successfully to:\n{file_path}",
#                 )
#             else:
#                 QMessageBox.critical(
#                     self,
#                     "Export Failed",
#                     "Could not write CSV file. Please check permissions.",
#                 )

#     def _cleanup_thread(self, *args) -> None:
#         if self._thread and self._thread.isRunning():
#             self._thread.quit()
#             self._thread.wait()
#             self._thread = None
#             self._worker = None

#     def _load_selected_sku_profile(self, profile_name: str) -> None:
#         profile = self.profile_manager.load_profile(profile_name)
#         if profile:
#             self.txt_file_path.setText(profile.file_path)
#             self.txt_base_addr.setText(hex(profile.base_address))
#             self.chk_verify.setChecked(profile.verify_enabled)
#             self.chk_serial_inject.setChecked(profile.enable_provisioning)
#             self.txt_serial_addr.setText(hex(profile.serial_address))
"""
Production Programmer Widget for STM32 deployment.
Provides visual QA PASS/FAIL banner, live shift production statistics,
96-bit UID reading, serial number provisioning, and SQLite traceability.
Now fully supports dynamic SWD / USB DFU interface switching.
"""

import os
from PySide6.QtCore import Qt, QThread, Slot, QPoint
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QFileDialog,
    QComboBox,
    QCheckBox,
    QMessageBox,
    QFrame,
    QSizePolicy,
    QScrollArea,
    QStyleOptionButton,
)
from PySide6.QtGui import QPainter, QPolygon


from src.common import get_logger
from src.common.traceability import TraceabilityDatabase
from src.features.production_programmer.worker import ProductionProgrammerWorker
from src.features.production_programmer.provisioning import ProvisioningService
from src.features.production_programmer.qa_service import QAService
from src.features.production_programmer.qa_banner import QABannerWidget
from src.common.profile_manager import ProfileManager, SKUProfile

logger = get_logger("ProductionProgrammerWidget")


class VisibleArrowComboBox(QComboBox):
    """QComboBox with an always-visible white dropdown arrow.

    The mouse wheel does not change the selected value while the popup is
    closed. The user must explicitly open the dropdown and choose an item.
    Scrolling inside the opened dropdown remains available.
    """

    def wheelEvent(self, event) -> None:
        # Prevent accidental value changes caused by page scrolling when the
        # combo box is not explicitly open. The user must make an explicit
        # selection from the dropdown.
        if not self.view().isVisible():
            event.ignore()
            return

        super().wheelEvent(event)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(Qt.GlobalColor.white)

        # Draw a clear downward triangle in the dedicated dropdown area.
        cx = self.width() - 19
        cy = self.height() // 2
        arrow = QPolygon([
            QPoint(cx - 6, cy - 3),
            QPoint(cx + 6, cy - 3),
            QPoint(cx, cy + 4),
        ])
        painter.drawPolygon(arrow)
        painter.end()


class ProductionProgrammerWidget(QWidget):
    """
    Industrial GUI for firmware deployment, QA validation, and traceability logging.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # نگهداری وضعیت نوع اتصال که از سمت منوی اصلی تغییر می‌کند
        self.current_interface = "DAPLink (SWD)"

        self.traceability_db = TraceabilityDatabase()
        self.qa_service = QAService()
        self.current_uid: str = "UNKNOWN-UID"
        self.last_cycle_time: float = 0.0
        self.profile_manager = ProfileManager()

        self._thread: QThread | None = None
        self._worker: ProductionProgrammerWorker | None = None

        self._setup_ui()
        self._apply_styles()
        self._update_statistics_display()

    def set_interface_type(self, interface_type: str) -> None:
        """این متد توسط MainWindow فراخوانی می‌شود تا تغییر رابط اعمال گردد."""
        self.current_interface = interface_type
        logger.info(
            f"ProductionProgrammerWidget interface set to: {self.current_interface}")

    def _apply_styles(self) -> None:
        """Professional, spacious industrial UI styling.

        This method only changes presentation; it does not change any
        programming, erase, verification, provisioning, or traceability logic.
        """
        self.setStyleSheet(
            """
            QWidget {
                background-color: #0B1220;
                color: #E5E7EB;
                font-family: "Segoe UI", "Arial";
            }

            QScrollArea {
                border: none;
                background: #0B1220;
            }

            QScrollBar:vertical {
                background: #0F192A;
                width: 12px;
                margin: 2px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: #334A68;
                min-height: 50px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical:hover {
                background: #456180;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
            }

            QGroupBox {
                background-color: #111C2E;
                border: 1px solid #2A3D59;
                border-radius: 12px;
                margin-top: 30px;
                font-size: 15px;
                font-weight: 800;
                color: #38BDF8;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 18px;
                padding: 5px 11px;
                background-color: #0B1220;
                color: #38BDF8;
            }

            QLabel {
                color: #E5EDF7;
                font-size: 14px;
                font-weight: 650;
            }

            QLabel#sectionHint {
                color: #8293AA;
                font-size: 12px;
                font-weight: 500;
            }

            QLineEdit {
                background-color: #0A1323;
                color: #F8FAFC;
                border: 1px solid #40516B;
                border-radius: 8px;
                padding: 10px 13px;
                min-height: 24px;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 14px;
                font-weight: 700;
                selection-background-color: #155E75;
            }
            QLineEdit:hover { border-color: #38BDF8; }
            QLineEdit:focus {
                border: 2px solid #0EA5E9;
                background-color: #0E1B30;
            }
            QLineEdit:read-only {
                background-color: #162338;
                color: #CBD5E1;
                border: 1px solid #3A4E6A;
            }

            QComboBox {
                background-color: #0A1323;
                color: #F8FAFC;
                border: 1px solid #40516B;
                border-radius: 8px;
                padding: 10px 48px 10px 12px;
                min-height: 24px;
                font-size: 14px;
                font-weight: 700;
            }
            QComboBox:hover { border-color: #38BDF8; }
            QComboBox:focus { border-color: #38BDF8; }
            QComboBox:hover { background-color: #0E1B30; }
            QComboBox::drop-down {
                width: 38px;
                border: none;
                border-left: 1px solid #2A3D59;
            }
            QComboBox QAbstractItemView {
                background: #111C2E;
                color: #F8FAFC;
                border: 1px solid #40516B;
                selection-background-color: #155E75;
                selection-color: #FFFFFF;
                padding: 5px;
                outline: none;
            }

            QPushButton {
                background-color: #2A3D59;
                color: #F8FAFC;
                border: 1px solid #405675;
                border-radius: 9px;
                padding: 10px 18px;
                min-height: 26px;
                font-size: 13px;
                font-weight: 800;
            }
            QPushButton:hover {
                background-color: #344C6B;
                border-color: #5B7393;
            }
            QPushButton:pressed { background-color: #1C2B42; }
            QPushButton:disabled {
                background-color: #172236;
                color: #52627A;
                border-color: #26354B;
            }

            QPushButton#browseBtn { min-width: 150px; }
            QPushButton#resetBtn { min-width: 165px; }

            QPushButton#startBtn {
                background-color: #059669;
                border: 1px solid #10B981;
                color: white;
                font-size: 16px;
                font-weight: 900;
                letter-spacing: 1px;
            }
            QPushButton#startBtn:hover { background-color: #10B981; }
            QPushButton#startBtn:pressed { background-color: #047857; }

            QPushButton#eraseBtn {
                background-color: #DC2626;
                border: 1px solid #EF4444;
                color: white;
                font-size: 15px;
                font-weight: 900;
            }
            QPushButton#eraseBtn:hover { background-color: #EF4444; }
            QPushButton#eraseBtn:pressed { background-color: #B91C1C; }

            QCheckBox {
                color: #E5EDF7;
                font-size: 14px;
                font-weight: 700;
                spacing: 12px;
                padding: 2px 0px;
            }
            QCheckBox:hover {
                color: #38BDF8;
            }
            QCheckBox:checked {
                color: #4ADE80;
            }
            QCheckBox:checked:hover {
                color: #6EE7B7;
            }
            QCheckBox::indicator {
                width: 24px;
                height: 24px;
                border: 2px solid #64748B;
                border-radius: 6px;
                background-color: #0A1323;
            }
            QCheckBox::indicator:hover { border-color: #38BDF8; }
            QCheckBox::indicator:checked {
                background-color: #059669;
                border-color: #10B981;
            }
            QCheckBox:disabled { color: #64748B; }

            QProgressBar {
                border: 1px solid #334968;
                border-radius: 9px;
                background-color: #0A1323;
                text-align: center;
                color: #FFFFFF;
                font-size: 14px;
                font-weight: 900;
                min-height: 32px;
                max-height: 32px;
            }
            QProgressBar::chunk {
                background-color: #0891B2;
                border-radius: 7px;
            }

            QFrame#separator {
                background-color: #2A3D59;
                min-height: 1px;
                max-height: 1px;
            }

            QFrame#statCard {
                background-color: #0D182A;
                border: 1px solid #2C4160;
                border-radius: 10px;
            }
            QLabel#statPass { color: #4ADE80; font-size: 18px; font-weight: 900; }
            QLabel#statFail { color: #F87171; font-size: 18px; font-weight: 900; }
            QLabel#statTotal { color: #F1F5F9; font-size: 18px; font-weight: 900; }
            QLabel#statYield { color: #FACC15; font-size: 18px; font-weight: 900; }
            """
        )

    def _setup_ui(self) -> None:
        # The page is scrollable so no control can ever be clipped when the
        # application window is shorter than the complete production form.
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content.setMinimumWidth(760)
        main_layout = QVBoxLayout(content)
        main_layout.setContentsMargins(22, 22, 22, 22)
        main_layout.setSpacing(16)

        # ----------------------------------------------------------------------
        # 1. QA banner
        # ----------------------------------------------------------------------
        self.qa_banner = QABannerWidget(content)
        self.qa_banner.setMinimumHeight(118)
        main_layout.addWidget(self.qa_banner)

        # ----------------------------------------------------------------------
        # 2. Production statistics
        # ----------------------------------------------------------------------
        stats_box = QGroupBox("Production Shift Statistics", content)
        stats_box.setMinimumHeight(116)
        stats_layout = QHBoxLayout(stats_box)
        stats_layout.setContentsMargins(14, 18, 14, 14)
        stats_layout.setSpacing(12)

        def make_stat_card(text: str, object_name: str) -> QFrame:
            card = QFrame(stats_box)
            card.setObjectName("statCard")
            card.setMinimumHeight(64)
            layout = QVBoxLayout(card)
            layout.setContentsMargins(8, 8, 8, 8)
            label = QLabel(text, card)
            label.setObjectName(object_name)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)
            return card

        self.lbl_stat_pass = QLabel("PASS: 0", content)
        self.lbl_stat_fail = QLabel("FAIL: 0", content)
        self.lbl_stat_total = QLabel("TOTAL: 0", content)
        self.lbl_stat_yield = QLabel("YIELD: 100.0%", content)

        stats_layout.addWidget(make_stat_card("PASS: 0", "statPass"), 1)
        stats_layout.addWidget(make_stat_card("FAIL: 0", "statFail"), 1)
        stats_layout.addWidget(make_stat_card("TOTAL: 0", "statTotal"), 1)
        stats_layout.addWidget(make_stat_card("YIELD: 100.0%", "statYield"), 1)

        self.btn_reset_stats = QPushButton("RESET COUNTERS", stats_box)
        self.btn_reset_stats.setObjectName("resetBtn")
        self.btn_reset_stats.setMinimumHeight(50)
        self.btn_reset_stats.clicked.connect(self._on_reset_statistics)
        stats_layout.addWidget(self.btn_reset_stats)
        main_layout.addWidget(stats_box)

        # ----------------------------------------------------------------------
        # 3. Firmware image
        # ----------------------------------------------------------------------
        file_box = QGroupBox("Firmware Image Configuration", content)
        file_box.setMinimumHeight(166)
        file_layout = QVBoxLayout(file_box)
        file_layout.setContentsMargins(14, 18, 14, 14)
        file_layout.setSpacing(14)

        path_layout = QHBoxLayout()
        path_layout.setSpacing(12)
        self.txt_file_path = QLineEdit(file_box)
        self.txt_file_path.setPlaceholderText(
            "Select firmware binary (.hex, .bin)...")
        self.txt_file_path.setReadOnly(True)
        self.txt_file_path.setMinimumHeight(48)
        self.btn_browse = QPushButton("BROWSE...", file_box)
        self.btn_browse.setObjectName("browseBtn")
        self.btn_browse.setMinimumHeight(48)
        self.btn_browse.clicked.connect(self._browse_firmware)
        path_layout.addWidget(self.txt_file_path, 1)
        path_layout.addWidget(self.btn_browse)
        file_layout.addLayout(path_layout)

        address_layout = QHBoxLayout()
        address_layout.setSpacing(12)
        lbl_addr = QLabel("Base Address (BIN):", file_box)
        lbl_addr.setMinimumWidth(145)
        self.txt_base_addr = QLineEdit("0x08000000", file_box)
        self.txt_base_addr.setMinimumWidth(180)
        self.txt_base_addr.setMinimumHeight(46)
        self.chk_verify = QCheckBox(
            "Verify Flash Memory Integrity After Programming", file_box)
        self.chk_verify.setChecked(True)
        self.chk_verify.setMinimumHeight(44)
        address_layout.addWidget(lbl_addr)
        address_layout.addWidget(self.txt_base_addr)
        address_layout.addSpacing(24)
        address_layout.addWidget(self.chk_verify, 1)
        file_layout.addLayout(address_layout)
        main_layout.addWidget(file_box)

        # ----------------------------------------------------------------------
        # 4. Connection settings
        # ----------------------------------------------------------------------
        probe_box = QGroupBox(
            "Connection Settings  •  SWD Modes Only", content)
        probe_box.setMinimumHeight(112)
        probe_layout = QGridLayout(probe_box)
        probe_layout.setContentsMargins(14, 18, 14, 14)
        probe_layout.setHorizontalSpacing(14)
        probe_layout.setVerticalSpacing(10)

        lbl_clock = QLabel("SWD Frequency:", probe_box)
        lbl_mode = QLabel("Connect Mode:", probe_box)
        self.combo_clock = VisibleArrowComboBox(probe_box)
        self.combo_clock.addItems(
            ["4000 kHz", "2000 kHz", "1000 kHz", "500 kHz"])
        self.combo_clock.setCurrentText("1000 kHz")
        self.combo_clock.setMinimumWidth(190)
        self.combo_clock.setMinimumHeight(48)
        self.combo_mode = VisibleArrowComboBox(probe_box)
        self.combo_mode.addItems(["under-reset", "normal", "attach"])
        self.combo_mode.setCurrentText("under-reset")
        self.combo_mode.setMinimumWidth(200)
        self.combo_mode.setMinimumHeight(48)

        probe_layout.addWidget(lbl_clock, 0, 0)
        probe_layout.addWidget(self.combo_clock, 0, 1)
        probe_layout.addWidget(lbl_mode, 0, 2)
        probe_layout.addWidget(self.combo_mode, 0, 3)
        probe_layout.setColumnStretch(4, 1)
        main_layout.addWidget(probe_box)

        # ----------------------------------------------------------------------
        # 5. Hardware provisioning & traceability
        # ----------------------------------------------------------------------
        prov_box = QGroupBox("Hardware Provisioning & Traceability", content)
        prov_box.setMinimumHeight(190)
        prov_layout = QVBoxLayout(prov_box)
        prov_layout.setContentsMargins(14, 18, 14, 14)
        prov_layout.setSpacing(14)

        uid_layout = QHBoxLayout()
        uid_layout.setSpacing(12)
        lbl_uid = QLabel("Target 96-bit UID:", prov_box)
        lbl_uid.setMinimumWidth(145)
        self.txt_uid_display = QLineEdit("NOT-READ", prov_box)
        self.txt_uid_display.setReadOnly(True)
        self.txt_uid_display.setMinimumHeight(48)
        uid_layout.addWidget(lbl_uid)
        uid_layout.addWidget(self.txt_uid_display, 1)
        prov_layout.addLayout(uid_layout)

        line = QFrame(prov_box)
        line.setObjectName("separator")
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        prov_layout.addWidget(line)

        serial_layout = QGridLayout()
        serial_layout.setHorizontalSpacing(12)
        serial_layout.setVerticalSpacing(8)
        self.chk_serial_inject = QCheckBox(
            "Inject Serial Number into Flash Memory", prov_box)
        self.chk_serial_inject.setChecked(False)
        self.chk_serial_inject.setMinimumHeight(44)
        lbl_serial = QLabel("Serial No.:", prov_box)
        self.txt_serial = QLineEdit("SN-2026-0001", prov_box)
        self.txt_serial.setMinimumWidth(205)
        self.txt_serial.setMinimumHeight(46)
        lbl_serial_addr = QLabel("Memory Address:", prov_box)
        self.txt_serial_addr = QLineEdit("0x0801FC00", prov_box)
        self.txt_serial_addr.setMinimumWidth(180)
        self.txt_serial_addr.setMinimumHeight(46)

        serial_layout.addWidget(self.chk_serial_inject, 0, 0, 1, 2)
        serial_layout.addWidget(lbl_serial, 0, 2)
        serial_layout.addWidget(self.txt_serial, 0, 3)
        serial_layout.addWidget(lbl_serial_addr, 0, 4)
        serial_layout.addWidget(self.txt_serial_addr, 0, 5)
        serial_layout.setColumnStretch(1, 1)
        prov_layout.addLayout(serial_layout)
        main_layout.addWidget(prov_box)

        # ----------------------------------------------------------------------
        # 6. Progress
        # ----------------------------------------------------------------------
        self.progress_bar = QProgressBar(content)
        self.progress_bar.setValue(0)
        self.progress_bar.setMinimumHeight(36)
        main_layout.addWidget(self.progress_bar)

        # ----------------------------------------------------------------------
        # 7. Operation controls
        # ----------------------------------------------------------------------
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(14)
        self.btn_start = QPushButton("START PROGRAMMING", content)
        self.btn_start.setObjectName("startBtn")
        self.btn_start.setMinimumHeight(66)
        self.btn_start.clicked.connect(self._start_production_flash)
        self.btn_erase = QPushButton("FULL CHIP ERASE", content)
        self.btn_erase.setObjectName("eraseBtn")
        self.btn_erase.setMinimumHeight(66)
        self.btn_erase.clicked.connect(self._start_chip_erase)
        self.btn_export = QPushButton("EXPORT LOGS (CSV)", content)
        self.btn_export.setMinimumHeight(66)
        self.btn_export.clicked.connect(self._export_logs_csv)
        btn_layout.addWidget(self.btn_start, 4)
        btn_layout.addWidget(self.btn_erase, 2)
        btn_layout.addWidget(self.btn_export, 2)
        main_layout.addLayout(btn_layout)
        main_layout.addStretch(1)

        scroll.setWidget(content)
        outer_layout.addWidget(scroll)

    def _update_statistics_display(self) -> None:
        """Refreshes QA statistics labels from QAService metrics."""
        passed, failed, total, yield_pct = self.qa_service.get_statistics()
        self.lbl_stat_pass.setText(f"PASS: {passed}")
        self.lbl_stat_fail.setText(f"FAIL: {failed}")
        self.lbl_stat_total.setText(f"TOTAL: {total}")
        self.lbl_stat_yield.setText(f"YIELD: {yield_pct:.1f}%")

    def _on_reset_statistics(self) -> None:
        """Resets shift pass/fail counters after operator confirmation."""
        reply = QMessageBox.question(
            self,
            "Reset Counters",
            "Are you sure you want to reset shift production statistics?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.qa_service.reset_statistics()
            self._update_statistics_display()
            self.qa_banner.set_ready_state()
            logger.info("Shift production counters reset to zero.")

    def _browse_firmware(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select STM32 Firmware Image",
            "",
            "Firmware Files (*.hex *.bin);;All Files (*.*)",
        )
        if file_path:
            self.txt_file_path.setText(os.path.normpath(file_path))

    def _parse_clock_freq(self) -> int:
        freq_str = self.combo_clock.currentText().split()[0]
        return int(freq_str) * 1000

    def _parse_base_address(self) -> int:
        return int(self.txt_base_addr.text().strip(), 16)

    def _parse_serial_address(self) -> int:
        return int(self.txt_serial_addr.text().strip(), 16)

    def _set_ui_busy(self, busy: bool) -> None:
        self.btn_start.setEnabled(not busy)
        self.btn_erase.setEnabled(not busy)
        self.btn_browse.setEnabled(not busy)
        self.btn_export.setEnabled(not busy)
        if busy:
            self.progress_bar.setValue(0)
            self.qa_banner.set_busy_state(
                f"Executing hardware sequence via {self.current_interface}...")

    def _start_production_flash(self) -> None:
        file_path = self.txt_file_path.text().strip()
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(self, "File Error",
                                "Please select a valid firmware image.")
            return

        try:
            base_addr = self._parse_base_address()
            clock_freq = self._parse_clock_freq()
            serial_addr = self._parse_serial_address()
        except ValueError:
            QMessageBox.critical(self, "Format Error",
                                 "Invalid hexadecimal memory address syntax.")
            return

        enable_prov = self.chk_serial_inject.isChecked()
        serial_str = self.txt_serial.text().strip()
        serial_payload = (
            ProvisioningService().build_serial_payload(max_length=32)
            if enable_prov else []
        )

        self._set_ui_busy(True)
        self.current_uid = "UNKNOWN-UID"
        self.txt_uid_display.setText("READING...")

        self._thread = QThread()
        self._worker = ProductionProgrammerWorker(
            file_path=file_path,
            base_address=base_addr,
            clock_freq=clock_freq,
            connect_mode=self.combo_mode.currentText(),
            verify_enabled=self.chk_verify.isChecked(),
            enable_provisioning=enable_prov,
            serial_payload=serial_payload,
            serial_address=serial_addr,
            interface_type=self.current_interface
        )

        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run_production_flash)
        self._worker.progress_signal.connect(self.progress_bar.setValue)
        self._worker.uid_read_signal.connect(self._on_uid_received)
        self._worker.cycle_time_signal.connect(self._on_cycle_time_received)
        self._worker.finished_signal.connect(self._on_operation_finished)
        self._worker.finished_signal.connect(self._cleanup_thread)

        self._thread.start()

    def _start_chip_erase(self) -> None:
        try:
            clock_freq = self._parse_clock_freq()
        except ValueError:
            return

        self._set_ui_busy(True)
        self.qa_banner.set_busy_state("Executing Full Chip Erase...")

        self._thread = QThread()
        self._worker = ProductionProgrammerWorker(
            clock_freq=clock_freq,
            connect_mode=self.combo_mode.currentText(),
            interface_type=self.current_interface
        )

        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run_chip_erase)
        self._worker.progress_signal.connect(self.progress_bar.setValue)
        self._worker.cycle_time_signal.connect(self._on_cycle_time_received)
        self._worker.finished_signal.connect(self._on_operation_finished)
        self._worker.finished_signal.connect(self._cleanup_thread)

        self._thread.start()

    def _on_uid_received(self, uid_string: str) -> None:
        """Handles 96-bit Unique ID string emitted by background worker."""
        self.current_uid = uid_string
        self.txt_uid_display.setText(uid_string)
        logger.info(f"Target UID updated in GUI: {uid_string}")

    def _on_cycle_time_received(self, elapsed_seconds: float) -> None:
        """Stores execution time of the latest programming cycle."""
        self.last_cycle_time = elapsed_seconds

    def _on_operation_finished(self, success: bool, message: str) -> None:
        self._set_ui_busy(False)
        firmware_name = os.path.basename(self.txt_file_path.text()) or "N/A"
        serial_num = self.txt_serial.text().strip(
        ) if self.chk_serial_inject.isChecked() else None

        if "USB" not in self.current_interface:
            uid_valid = self.qa_service.is_valid_uid(self.current_uid)
            final_success = success and uid_valid
            if not uid_valid and success:
                message = "Programming succeeded but target UID validation FAILED."
        else:
            final_success = success
            self.current_uid = "DFU-DEVICE"

        self.qa_service.record_result(final_success)
        self._update_statistics_display()

        if final_success:
            self.qa_banner.set_pass_state(
                self.last_cycle_time,
                f"DEVICE VERIFIED PASS ({self.current_interface})",
            )
            status_text = "PASS"
        else:
            self.qa_banner.set_fail_state(message, self.last_cycle_time)
            status_text = "FAIL"

        self.traceability_db.log_operation(
            firmware_name=firmware_name,
            uid_96bit=self.current_uid,
            serial_number=serial_num,
            status=status_text,
            message=message,
        )

    def _export_logs_csv(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Production Traceability Logs",
            "production_report.csv",
            "CSV Files (*.csv)",
        )
        if file_path:
            success = self.traceability_db.export_to_csv(file_path)
            if success:
                QMessageBox.information(
                    self,
                    "Export Complete",
                    f"Production logs exported successfully to:\n{file_path}",
                )
            else:
                QMessageBox.critical(
                    self,
                    "Export Failed",
                    "Could not write CSV file. Please check permissions.",
                )

    def _cleanup_thread(self, *args) -> None:
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait()
            self._thread = None
            self._worker = None

    def _load_selected_sku_profile(self, profile_name: str) -> None:
        profile = self.profile_manager.load_profile(profile_name)
        if profile:
            self.txt_file_path.setText(profile.file_path)
            self.txt_base_addr.setText(hex(profile.base_address))
            self.chk_verify.setChecked(profile.verify_enabled)
            self.chk_serial_inject.setChecked(profile.enable_provisioning)
            self.txt_serial_addr.setText(hex(profile.serial_address))
