"""
Production Programmer Widget for STM32 deployment.
Provides visual QA PASS/FAIL banner, live shift production statistics,
96-bit UID reading, serial number provisioning, and SQLite traceability.
Now fully supports dynamic SWD / USB DFU interface switching.
"""
import os
from PySide6.QtCore import Qt, QThread, Slot, QPoint, QSize
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
)
from PySide6.QtGui import QPainter, QPolygon, QIcon

from src.common.resources import ICON_ARROWS_ROTATE, ICON_FOLDER_OPEN
from src.common import get_logger
from src.common.traceability import TraceabilityDatabase
from src.features.production_programmer.worker import ProductionProgrammerWorker
from src.features.production_programmer.provisioning import ProvisioningService
from src.features.production_programmer.qa_service import QAService
from src.features.production_programmer.qa_banner import QABannerWidget
from src.common.profile_manager import ProfileManager, SKUProfile

logger = get_logger("ProductionProgrammerWidget")


class VisibleArrowComboBox(QComboBox):
    """QComboBox with an always-visible cyan dropdown arrow."""

    def wheelEvent(self, event) -> None:
        if not self.view().isVisible():
            event.ignore()
            return
        super().wheelEvent(event)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(Qt.GlobalColor.cyan)

        cx = self.width() - 14
        cy = self.height() // 2
        arrow = QPolygon([
            QPoint(cx - 4, cy - 2),
            QPoint(cx + 4, cy - 2),
            QPoint(cx, cy + 3),
        ])
        painter.drawPolygon(arrow)
        painter.end()


class ProductionProgrammerWidget(QWidget):
    """
    Industrial GUI for firmware deployment, QA validation, and traceability logging.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.current_interface = "B-Link (SWD)"
        self._current_operation = "NONE"

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
        self.current_mcu_target: str = "cortex_m"

    def set_interface_type(self, interface_type: str) -> None:
        self.current_interface = interface_type
        logger.info(
            f"ProductionProgrammerWidget interface set to: {self.current_interface}")

    def _apply_styles(self) -> None:
        """BlueWave Dark Compact Industrial UI Theme."""
        self.setStyleSheet(
            """
            QWidget {
                background-color: #070B19;
                color: #F8FAFC;
                font-family: "Segoe UI", "Tahoma", sans-serif;
            }

            QLabel {
                background-color: transparent;
                color: #F8FAFC;
                font-size: 12px;
                font-weight: 600;
            }

            QGroupBox {
                background-color: #0C1327;
                border: 1px solid #1A2642;
                border-radius: 6px;
                margin-top: 18px; 
                padding-top: 14px; 
            }

            /* 📌 موقعیت و پدینگ عنوان باکس‌ها */
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                top: -4px;
                left: 0px; 
                padding-left: 4px;
                padding-right: 20px;
                padding-top: 2px;
                padding-bottom: 2px;
                background-color: transparent;
                color: #00E5FF;
                font-size: 12px;
                font-weight: 700;
            }

            QLineEdit {
                background-color: #03060E;
                color: #F8FAFC;
                border: 1px solid #1A2642;
                border-radius: 4px;
                padding: 4px 8px;
                min-height: 24px;
                font-family: "Consolas", monospace;
                font-size: 12px;
            }
            QLineEdit:hover { border-color: #00E5FF; }
            QLineEdit:focus {
                border: 1px solid #00E5FF;
                background-color: #070B19;
            }
            QLineEdit:read-only {
                background-color: #070B19;
                color: #94A3B8;
                border: 1px solid #1A2642;
            }
            /* استایل آبی پس از انتخاب فایل */
            QLineEdit:read-only[hasFile="true"] {
                border: 1px solid #00E5FF;
                color: #00E5FF;
            }

            QComboBox {
                background-color: #03060E;
                color: #F8FAFC;
                border: 1px solid #1A2642;
                border-radius: 4px;
                padding: 3px 25px 3px 8px;
                min-height: 24px;
                font-size: 12px;
                font-weight: 600;
            }
            QComboBox:hover { border-color: #00E5FF; }
            QComboBox::drop-down {
                width: 20px;
                border: none;
                border-left: 1px solid #1A2642;
            }
            QComboBox QAbstractItemView {
                background-color: #0C1327;
                color: #F8FAFC;
                border: 1px solid #1A2642;
                selection-background-color: #00E5FF;
                selection-color: #070B19;
                outline: none;
            }

            QPushButton {
                background-color: #121D38;
                color: #F8FAFC;
                border: 1px solid #1A2642;
                border-radius: 4px;
                padding: 5px 12px;
                min-height: 26px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #00B4D8;
                border-color: #00E5FF;
                color: #FFFFFF;
            }
            QPushButton:pressed { background-color: #121D38; }
            QPushButton:disabled {
                background-color: #070B19;
                color: #94A3B8;
                border-color: #1A2642;
            }

            QPushButton#startBtn {
                background-color: #121D38;
                border: 1px solid #00E5FF;
                color: #00E5FF;
                font-size: 13px;
                font-weight: 800;
            }
            QPushButton#startBtn:hover {
                background-color: #00E5FF;
                color: #070B19;
            }

            QPushButton#eraseBtn {
                background-color: #121D38;
                border: 1px solid #EF4444;
                color: #EF4444;
                font-size: 12px;
                font-weight: 800;
            }
            QPushButton#eraseBtn:hover {
                background-color: #EF4444;
                color: #FFFFFF;
            }

            QCheckBox {
                background-color: transparent;
                color: #F8FAFC;
                font-size: 12px;
                spacing: 6px;
            }
            QCheckBox:hover { color: #00E5FF; }
            QCheckBox:checked { color: #00E5FF; }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #1A2642;
                border-radius: 3px;
                background-color: #03060E;
            }
            QCheckBox::indicator:hover { border-color: #00E5FF; }
            QCheckBox::indicator:checked {
                background-color: #00E5FF;
                border-color: #00E5FF;
                image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%23070B19' stroke-width='4' stroke-linecap='round' stroke-linejoin='round'><polyline points='20 6 9 17 4 12'></polyline></svg>");
            }

            QProgressBar {
                border: 1px solid #1A2642;
                border-radius: 4px;
                background-color: #03060E;
                text-align: center;
                color: #F8FAFC;
                font-size: 11px;
                font-weight: 700;
                max-height: 18px;
            }
            QProgressBar::chunk {
                background-color: #00E5FF;
                border-radius: 3px;
            }

            QFrame#statCard {
                background-color: #03060E;
                border: 1px solid #1A2642;
                border-radius: 4px;
            }
            QLabel#statPass { color: #10B981; font-size: 13px; font-weight: 800; }
            QLabel#statFail { color: #EF4444; font-size: 13px; font-weight: 800; }
            QLabel#statTotal { color: #00E5FF; font-size: 13px; font-weight: 800; }

            QFrame#separator {
                background-color: #1A2642;
                max-height: 1px;
            }
            """
        )

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 8, 12, 8)
        main_layout.setSpacing(8)

        # ----------------------------------------------------------------------
        # 1. QA banner
        # ----------------------------------------------------------------------
        self.qa_banner = QABannerWidget(self)
        main_layout.addWidget(self.qa_banner)

        # ----------------------------------------------------------------------
        # 2. Production statistics
        # ----------------------------------------------------------------------
        stats_box = QGroupBox("Shift Production Statistics", self)
        stats_layout = QHBoxLayout(stats_box)
        stats_layout.setContentsMargins(8, 12, 8, 8)
        stats_layout.setSpacing(8)

        def make_stat_card(label_widget: QLabel) -> QFrame:
            card = QFrame(stats_box)
            card.setObjectName("statCard")
            card.setFixedHeight(36)
            layout = QVBoxLayout(card)
            layout.setContentsMargins(4, 2, 4, 2)
            layout.addWidget(label_widget)
            return card

        self.lbl_stat_pass = QLabel("PASS: 0", stats_box)
        self.lbl_stat_pass.setObjectName("statPass")
        self.lbl_stat_pass.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_stat_fail = QLabel("FAIL: 0", stats_box)
        self.lbl_stat_fail.setObjectName("statFail")
        self.lbl_stat_fail.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_stat_total = QLabel("TOTAL: 0", stats_box)
        self.lbl_stat_total.setObjectName("statTotal")
        self.lbl_stat_total.setAlignment(Qt.AlignmentFlag.AlignCenter)

        stats_layout.addWidget(make_stat_card(self.lbl_stat_pass), 1)
        stats_layout.addWidget(make_stat_card(self.lbl_stat_fail), 1)
        stats_layout.addWidget(make_stat_card(self.lbl_stat_total), 1)

        self.btn_reset_stats = QPushButton(" RESET COUNTERS", stats_box)
        self.btn_reset_stats.setIcon(QIcon(ICON_ARROWS_ROTATE))
        self.btn_reset_stats.setIconSize(QSize(14, 14))
        self.btn_reset_stats.setFixedHeight(36)
        self.btn_reset_stats.clicked.connect(self._on_reset_statistics)
        stats_layout.addWidget(self.btn_reset_stats)
        main_layout.addWidget(stats_box)

        # ----------------------------------------------------------------------
        # 3. Firmware image
        # ----------------------------------------------------------------------
        file_box = QGroupBox("Firmware Image Configuration", self)
        file_layout = QVBoxLayout(file_box)
        file_layout.setContentsMargins(8, 12, 8, 8)
        file_layout.setSpacing(6)

        path_layout = QHBoxLayout()
        path_layout.setSpacing(8)
        self.txt_file_path = QLineEdit(file_box)
        self.txt_file_path.setPlaceholderText(
            "Select firmware binary (.hex, .bin)...")
        self.txt_file_path.setReadOnly(True)

        self.btn_browse = QPushButton(" BROWSE...", file_box)
        self.btn_browse.setIcon(QIcon(ICON_FOLDER_OPEN))
        self.btn_browse.setIconSize(QSize(16, 16))
        self.btn_browse.setFixedWidth(115)
        self.btn_browse.clicked.connect(self._browse_firmware)

        path_layout.addWidget(self.txt_file_path, 1)
        path_layout.addWidget(self.btn_browse)
        file_layout.addLayout(path_layout)

        address_layout = QHBoxLayout()
        address_layout.setSpacing(8)
        lbl_addr = QLabel("Base Address (BIN):", file_box)
        self.txt_base_addr = QLineEdit("0x08000000", file_box)
        self.txt_base_addr.setFixedWidth(120)

        self.chk_verify = QCheckBox(
            "Verify Flash Memory Integrity After Programming", file_box)
        self.chk_verify.setChecked(True)

        address_layout.addWidget(lbl_addr)
        address_layout.addWidget(self.txt_base_addr)
        address_layout.addSpacing(15)
        address_layout.addWidget(self.chk_verify, 1)
        file_layout.addLayout(address_layout)
        main_layout.addWidget(file_box)

        # ----------------------------------------------------------------------
        # 4. Connection settings
        # ----------------------------------------------------------------------
        probe_box = QGroupBox("Connection Settings  •  SWD Modes Only", self)
        probe_layout = QHBoxLayout(probe_box)
        probe_layout.setContentsMargins(8, 12, 8, 8)
        probe_layout.setSpacing(10)

        lbl_clock = QLabel("SWD Frequency:", probe_box)
        self.combo_clock = VisibleArrowComboBox(probe_box)
        self.combo_clock.addItems(
            ["4000 kHz", "2000 kHz", "1000 kHz", "500 kHz"])
        self.combo_clock.setCurrentText("1000 kHz")

        lbl_mode = QLabel("Connect Mode:", probe_box)
        self.combo_mode = VisibleArrowComboBox(probe_box)
        self.combo_mode.addItems(["under-reset", "normal", "attach"])
        self.combo_mode.setCurrentText("under-reset")

        probe_layout.addWidget(lbl_clock)
        probe_layout.addWidget(self.combo_clock, 1)
        probe_layout.addSpacing(10)
        probe_layout.addWidget(lbl_mode)
        probe_layout.addWidget(self.combo_mode, 1)
        main_layout.addWidget(probe_box)

        # ----------------------------------------------------------------------
        # 5. Hardware provisioning & traceability
        # ----------------------------------------------------------------------
        prov_box = QGroupBox("Hardware Provisioning & Traceability", self)
        prov_layout = QVBoxLayout(prov_box)
        prov_layout.setContentsMargins(8, 12, 8, 8)
        prov_layout.setSpacing(6)

        uid_layout = QHBoxLayout()
        uid_layout.setSpacing(8)
        lbl_uid = QLabel("Target 96-bit UID:", prov_box)
        self.txt_uid_display = QLineEdit("NOT-READ", prov_box)
        self.txt_uid_display.setReadOnly(True)
        uid_layout.addWidget(lbl_uid)
        uid_layout.addWidget(self.txt_uid_display, 1)
        prov_layout.addLayout(uid_layout)

        line = QFrame(prov_box)
        line.setObjectName("separator")
        line.setFrameShape(QFrame.Shape.HLine)
        prov_layout.addWidget(line)

        serial_layout = QHBoxLayout()
        serial_layout.setSpacing(8)
        self.chk_serial_inject = QCheckBox("Inject Serial No:", prov_box)
        self.chk_serial_inject.setChecked(False)

        self.txt_serial = QLineEdit("SN-2026-0001", prov_box)
        lbl_serial_addr = QLabel("Address:", prov_box)
        self.txt_serial_addr = QLineEdit("0x0801FC00", prov_box)
        self.txt_serial_addr.setFixedWidth(110)

        serial_layout.addWidget(self.chk_serial_inject)
        serial_layout.addWidget(self.txt_serial, 1)
        serial_layout.addWidget(lbl_serial_addr)
        serial_layout.addWidget(self.txt_serial_addr)
        prov_layout.addLayout(serial_layout)
        main_layout.addWidget(prov_box)

        # ----------------------------------------------------------------------
        # 6. Progress Bar
        # ----------------------------------------------------------------------
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)

        # ----------------------------------------------------------------------
        # 7. Operation controls
        # ----------------------------------------------------------------------
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_start = QPushButton(" START PROGRAMMING", self)
        self.btn_start.setObjectName("startBtn")
        self.btn_start.setIcon(QIcon(""))
        self.btn_start.setIconSize(QSize(16, 16))
        self.btn_start.setFixedHeight(40)
        self.btn_start.clicked.connect(self._start_production_flash)

        self.btn_erase = QPushButton(" FULL CHIP ERASE", self)
        self.btn_erase.setObjectName("eraseBtn")
        self.btn_erase.setIcon(QIcon(""))
        self.btn_erase.setIconSize(QSize(16, 16))
        self.btn_erase.setFixedHeight(40)
        self.btn_erase.clicked.connect(self._start_chip_erase)

        self.btn_export = QPushButton(" EXPORT LOGS (CSV)", self)
        self.btn_export.setIcon(
            QIcon(""))
        self.btn_export.setIconSize(QSize(16, 16))
        self.btn_export.setFixedHeight(40)
        self.btn_export.clicked.connect(self._export_logs_csv)

        btn_layout.addWidget(self.btn_start, 4)
        btn_layout.addWidget(self.btn_erase, 2)
        btn_layout.addWidget(self.btn_export, 2)
        main_layout.addLayout(btn_layout)

    def _update_statistics_display(self) -> None:
        passed, failed, total, yield_pct = self.qa_service.get_statistics()
        self.lbl_stat_pass.setText(f"PASS: {passed}")
        self.lbl_stat_fail.setText(f"FAIL: {failed}")
        self.lbl_stat_total.setText(f"TOTAL: {total}")

    def _on_reset_statistics(self) -> None:
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
            self.txt_file_path.setProperty("hasFile", True)
            self.txt_file_path.style().unpolish(self.txt_file_path)
            self.txt_file_path.style().polish(self.txt_file_path)

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

        self._current_operation = "FLASH"

        enable_prov = self.chk_serial_inject.isChecked()
        serial_payload = []
        if enable_prov:
            serial_str = self.txt_serial.text().strip()
            prov_service = ProvisioningService()
            prov_service.prefix = serial_str
            serial_payload = prov_service.build_serial_payload(max_length=32)

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

        self._current_operation = "ERASE"

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
        self.current_uid = uid_string
        self.txt_uid_display.setText(uid_string)
        logger.info(f"Target UID updated in GUI: {uid_string}")

    def _on_cycle_time_received(self, elapsed_seconds: float) -> None:
        self.last_cycle_time = elapsed_seconds

    def _on_operation_finished(self, success: bool, message: str) -> None:
        self._set_ui_busy(False)
        firmware_name = os.path.basename(self.txt_file_path.text()) or "N/A"
        serial_num = self.txt_serial.text().strip(
        ) if self.chk_serial_inject.isChecked() else None

        if self._current_operation == "FLASH" and "USB" not in self.current_interface:
            uid_valid = self.qa_service.is_valid_uid(self.current_uid)
            final_success = success and uid_valid
            if not uid_valid and success:
                message = "Programming succeeded but target UID validation FAILED."
        else:
            final_success = success
            if self._current_operation == "ERASE":
                self.current_uid = "ERASE-ONLY"
            elif "USB" in self.current_interface:
                self.current_uid = "DFU-DEVICE"

        self.qa_service.record_result(final_success)
        self._update_statistics_display()

        if final_success:
            op_name = "FLASHED" if self._current_operation == "FLASH" else "ERASED"
            self.qa_banner.set_pass_state(
                self.last_cycle_time,
                f"DEVICE {op_name} SUCCESSFULLY ({self.current_interface})",
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

        self._current_operation = "NONE"

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

            self.txt_file_path.setProperty("hasFile", True)
            self.txt_file_path.style().unpolish(self.txt_file_path)
            self.txt_file_path.style().polish(self.txt_file_path)
