# """
# Production Programmer Feature Widget for STM32 deployment.
# Provides visual QA PASS/FAIL banner, live shift production statistics,
# 96-bit UID reading, serial number provisioning, and SQLite traceability.
# """

# import os
# from PySide6.QtCore import Qt, QThread
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
#         self.traceability_db = TraceabilityDatabase()
#         self.qa_service = QAService()
#         self.current_uid: str = "UNKNOWN-UID"
#         self.last_cycle_time: float = 0.0
#         self.profile_manager = ProfileManager()

#         self._thread: QThread | None = None
#         self._worker: ProductionProgrammerWorker | None = None

#         self._setup_ui()
#         self._update_statistics_display()

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
#         # 4. SWD Probe Configuration
#         # ----------------------------------------------------------------------
#         probe_box = QGroupBox("SWD Probe Connection Settings", self)
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
#         self.btn_start = QPushButton("START PROGRAMMING", self)
#         self.btn_start.setFixedHeight(45)
#         self.btn_start.setStyleSheet(
#             "background-color: #2E86C1; color: white; font-weight: bold; font-size: 14px;"
#         )
#         self.btn_start.clicked.connect(self._start_production_flash)

#         self.btn_erase = QPushButton("FULL CHIP ERASE", self)
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
#             QMessageBox.Yes | QMessageBox.No,
#             QMessageBox.No,
#         )
#         if reply == QMessageBox.Yes:
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
#                 "Executing hardware programming sequence...")

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
#         self._worker = ProductionProgrammerWorker(
#             file_path=file_path,
#             base_address=base_addr,
#             clock_freq=clock_freq,
#             connect_mode=self.combo_mode.currentText(),
#             verify_enabled=self.chk_verify.isChecked(),
#             enable_provisioning=enable_prov,
#             serial_payload=serial_payload,
#             serial_address=serial_addr,
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
#         self._worker = ProductionProgrammerWorker(
#             clock_freq=clock_freq,
#             connect_mode=self.combo_mode.currentText(),
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

#         # Validate chip UID integrity rules
#         uid_valid = self.qa_service.is_valid_uid(self.current_uid)
#         final_success = success and uid_valid

#         if not uid_valid and success:
#             message = "Programming succeeded but target UID validation FAILED."

#         # Update QA statistics & industrial banner
#         self.qa_service.record_result(final_success)
#         self._update_statistics_display()

#         if final_success:
#             self.qa_banner.set_pass_state(
#                 self.last_cycle_time,
#                 "DEVICE VERIFIED PASS",
#             )
#             status_text = "PASS"
#         else:
#             self.qa_banner.set_fail_state(message, self.last_cycle_time)
#             status_text = "FAIL"

#         # Record event in local SQLite traceability database
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
from PySide6.QtCore import Qt, QThread, Slot
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QFileDialog,
    QComboBox,
    QCheckBox,
    QMessageBox,
)

from src.common import get_logger
from src.common.traceability import TraceabilityDatabase
from src.features.production_programmer.worker import ProductionProgrammerWorker
from src.features.production_programmer.provisioning import ProvisioningService
from src.features.production_programmer.qa_service import QAService
from src.features.production_programmer.qa_banner import QABannerWidget
from src.common.profile_manager import ProfileManager, SKUProfile


logger = get_logger("ProductionProgrammerWidget")


class ProductionProgrammerWidget(QWidget):
    """
    Industrial GUI for firmware deployment, QA validation, and traceability logging.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # 🌟 نگهداری وضعیت نوع اتصال که از سمت منوی اصلی تغییر می‌کند
        self.current_interface = "DAPLink (SWD)"

        self.traceability_db = TraceabilityDatabase()
        self.qa_service = QAService()
        self.current_uid: str = "UNKNOWN-UID"
        self.last_cycle_time: float = 0.0
        self.profile_manager = ProfileManager()

        self._thread: QThread | None = None
        self._worker: ProductionProgrammerWorker | None = None

        self._setup_ui()
        self._update_statistics_display()

    # 🌟 متد دریافت دستور تغییر رابط از MainWindow
    def set_interface_type(self, interface_type: str) -> None:
        """این متد توسط MainWindow فراخوانی می‌شود تا تغییر رابط اعمال گردد."""
        self.current_interface = interface_type
        # می‌توان اینجا متن باکس‌ها را آپدیت کرد، ولی برای سادگی در لاگ ثبت می‌کنیم
        logger.info(
            f"ProductionProgrammerWidget interface set to: {self.current_interface}")

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # ----------------------------------------------------------------------
        # 1. Industrial QA Visual Banner
        # ----------------------------------------------------------------------
        self.qa_banner = QABannerWidget(self)
        main_layout.addWidget(self.qa_banner)

        # ----------------------------------------------------------------------
        # 2. Live QA Shift Statistics Dashboard
        # ----------------------------------------------------------------------
        stats_box = QGroupBox("Production Shift Statistics", self)
        stats_layout = QHBoxLayout(stats_box)
        stats_layout.setSpacing(16)

        self.lbl_stat_pass = QLabel("PASS: 0", self)
        self.lbl_stat_pass.setStyleSheet(
            "color: #58D68D; font-weight: bold; font-size: 14px;")

        self.lbl_stat_fail = QLabel("FAIL: 0", self)
        self.lbl_stat_fail.setStyleSheet(
            "color: #EC7063; font-weight: bold; font-size: 14px;")

        self.lbl_stat_total = QLabel("TOTAL: 0", self)
        self.lbl_stat_total.setStyleSheet(
            "font-weight: bold; font-size: 14px;")

        self.lbl_stat_yield = QLabel("YIELD: 100.0%", self)
        self.lbl_stat_yield.setStyleSheet(
            "color: #F4D03F; font-weight: bold; font-size: 14px;")

        self.btn_reset_stats = QPushButton("Reset Counters", self)
        self.btn_reset_stats.setFixedWidth(120)
        self.btn_reset_stats.clicked.connect(self._on_reset_statistics)

        stats_layout.addWidget(self.lbl_stat_pass)
        stats_layout.addWidget(self.lbl_stat_fail)
        stats_layout.addWidget(self.lbl_stat_total)
        stats_layout.addWidget(self.lbl_stat_yield)
        stats_layout.addStretch()
        stats_layout.addWidget(self.btn_reset_stats)

        main_layout.addWidget(stats_box)

        # ----------------------------------------------------------------------
        # 3. Firmware Selection & Base Address
        # ----------------------------------------------------------------------
        file_box = QGroupBox("Firmware Image & Memory Address", self)
        file_layout = QVBoxLayout(file_box)

        path_layout = QHBoxLayout()
        self.txt_file_path = QLineEdit(self)
        self.txt_file_path.setPlaceholderText(
            "Select firmware binary (.hex, .bin)...")
        self.txt_file_path.setReadOnly(True)

        self.btn_browse = QPushButton("Browse...", self)
        self.btn_browse.clicked.connect(self._browse_firmware)

        path_layout.addWidget(self.txt_file_path)
        path_layout.addWidget(self.btn_browse)
        file_layout.addLayout(path_layout)

        addr_layout = QHBoxLayout()
        lbl_addr = QLabel("Base Address (BIN files):", self)
        self.txt_base_addr = QLineEdit("0x08000000", self)
        self.txt_base_addr.setFixedWidth(120)

        self.chk_verify = QCheckBox("Verify after Flash", self)
        self.chk_verify.setChecked(True)

        addr_layout.addWidget(lbl_addr)
        addr_layout.addWidget(self.txt_base_addr)
        addr_layout.addStretch()
        addr_layout.addWidget(self.chk_verify)
        file_layout.addLayout(addr_layout)

        main_layout.addWidget(file_box)

        # ----------------------------------------------------------------------
        # 4. Connection Configuration
        # ----------------------------------------------------------------------
        probe_box = QGroupBox("Connection Settings (SWD Modes Only)", self)
        probe_layout = QHBoxLayout(probe_box)

        lbl_clock = QLabel("SWD Frequency:", self)
        self.combo_clock = QComboBox(self)
        self.combo_clock.addItems(
            ["4000 kHz", "2000 kHz", "1000 kHz", "500 kHz"])
        self.combo_clock.setCurrentText("1000 kHz")

        lbl_mode = QLabel("Connect Mode:", self)
        self.combo_mode = QComboBox(self)
        self.combo_mode.addItems(["under-reset", "normal", "attach"])
        self.combo_mode.setCurrentText("under-reset")

        probe_layout.addWidget(lbl_clock)
        probe_layout.addWidget(self.combo_clock)
        probe_layout.addSpacing(20)
        probe_layout.addWidget(lbl_mode)
        probe_layout.addWidget(self.combo_mode)
        probe_layout.addStretch()

        main_layout.addWidget(probe_box)

        # ----------------------------------------------------------------------
        # 5. Production Provisioning (UID & Serial Injection)
        # ----------------------------------------------------------------------
        prov_box = QGroupBox("Hardware Provisioning & Traceability", self)
        prov_layout = QVBoxLayout(prov_box)

        uid_layout = QHBoxLayout()
        lbl_uid = QLabel("Target 96-bit UID:", self)
        self.txt_uid_display = QLineEdit("NOT-READ", self)
        self.txt_uid_display.setReadOnly(True)
        self.txt_uid_display.setStyleSheet(
            "font-family: Consolas, monospace; font-weight: bold;")

        uid_layout.addWidget(lbl_uid)
        uid_layout.addWidget(self.txt_uid_display)
        prov_layout.addLayout(uid_layout)

        serial_layout = QHBoxLayout()
        self.chk_serial_inject = QCheckBox(
            "Inject Serial Number after Flash", self)
        self.chk_serial_inject.setChecked(False)

        lbl_serial = QLabel("Serial:", self)
        self.txt_serial = QLineEdit("SN-2026-0001", self)
        self.txt_serial.setFixedWidth(150)

        lbl_serial_addr = QLabel("Address:", self)
        self.txt_serial_addr = QLineEdit("0x0801FC00", self)
        self.txt_serial_addr.setFixedWidth(110)

        serial_layout.addWidget(self.chk_serial_inject)
        serial_layout.addStretch()
        serial_layout.addWidget(lbl_serial)
        serial_layout.addWidget(self.txt_serial)
        serial_layout.addWidget(lbl_serial_addr)
        serial_layout.addWidget(self.txt_serial_addr)
        prov_layout.addLayout(serial_layout)

        main_layout.addWidget(prov_box)

        # ----------------------------------------------------------------------
        # 6. Progress & Operation Controls
        # ----------------------------------------------------------------------
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        main_layout.addWidget(self.progress_bar)

        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("⚡ START PROGRAMMING", self)
        self.btn_start.setFixedHeight(45)
        self.btn_start.setStyleSheet(
            "background-color: #2E86C1; color: white; font-weight: bold; font-size: 14px;"
        )
        self.btn_start.clicked.connect(self._start_production_flash)

        self.btn_erase = QPushButton("🗑 FULL CHIP ERASE", self)
        self.btn_erase.setFixedHeight(45)
        self.btn_erase.setStyleSheet(
            "background-color: #C0392B; color: white; font-weight: bold; font-size: 13px;"
        )
        self.btn_erase.clicked.connect(self._start_chip_erase)

        self.btn_export = QPushButton("Export Logs (CSV)", self)
        self.btn_export.setFixedHeight(45)
        self.btn_export.clicked.connect(self._export_logs_csv)

        btn_layout.addWidget(self.btn_start, 3)
        btn_layout.addWidget(self.btn_erase, 1)
        btn_layout.addWidget(self.btn_export, 1)

        main_layout.addLayout(btn_layout)
        main_layout.addStretch()

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
            ProvisioningService.generate_ascii_serial_payload(serial_str)
            if enable_prov
            else []
        )

        self._set_ui_busy(True)
        self.current_uid = "UNKNOWN-UID"
        self.txt_uid_display.setText("READING...")

        self._thread = QThread()
        # 🌟 پاس دادن رابط به ورکر
        self._worker = ProductionProgrammerWorker(
            file_path=file_path,
            base_address=base_addr,
            clock_freq=clock_freq,
            connect_mode=self.combo_mode.currentText(),
            verify_enabled=self.chk_verify.isChecked(),
            enable_provisioning=enable_prov,
            serial_payload=serial_payload,
            serial_address=serial_addr,
            interface_type=self.current_interface  # ⬅️ اینجا
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

        # در worker.py قبلی شما run_chip_erase تعریف شده بود که ما الان اون را به شکل کامل پشتیبانی میکنیم
        self._worker = ProductionProgrammerWorker(
            clock_freq=clock_freq,
            connect_mode=self.combo_mode.currentText(),
            interface_type=self.current_interface  # 🌟 ⬅️ این متغیر جدید
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

        # اعتبارسنجی UID: فقط در حالت SWD که واقعاً خوانده می‌شود
        if "USB" not in self.current_interface:
            uid_valid = self.qa_service.is_valid_uid(self.current_uid)
            final_success = success and uid_valid
            if not uid_valid and success:
                message = "Programming succeeded but target UID validation FAILED."
        else:
            # در مد DFU ما UID را ارزیابی نمیکنیم
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
