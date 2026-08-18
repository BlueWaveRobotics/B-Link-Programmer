"""
Industrial Memory Viewer Widget providing STM32CubeProgrammer-like memory inspection.
Supports customizable base address, size, data width (8/16/32-bit), and live Hex/ASCII dump.
"""

from typing import Optional, List
from PySide6.QtCore import Qt, Slot, QSize
from PySide6.QtGui import QFont, QColor, QIcon
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QGridLayout,
    QLabel,
    QComboBox,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QGroupBox,
    QSizePolicy,
)

from src.common import get_logger
from src.features.memory_viewer.worker import MemoryReadWorker
from src.features.batch_programmer.probe_manager import ProbeManagerService
from src.common.resources import QSS_CHEVRON_DOWN, ICON_ARROWS_ROTATE, ICON_HOURGLASS, ICON_BOOK_OPEN

logger = get_logger("MemoryViewerWidget")

# Standard STM32 Memory Map Presets
MEMORY_PRESETS = [
    ("0x08000000 - Main Flash Memory", "0x08000000"),
    ("0x20000000 - SRAM1 (System RAM)", "0x20000000"),
    ("0x1FFFF000 - System Memory (Bootloader)", "0x1FFFF000"),
    ("0x1FFFF800 - STM32F1 Option Bytes", "0x1FFFF800"),
    ("0x1FFF7A10 - Unique Device ID (STM32F1)", "0x1FFF7A10"),
    ("0xE000ED00 - Cortex-M SCB Registers", "0xE000ED00"),
]


class MemoryViewerWidget(QWidget):
    """
    Feature widget displaying hardware device memory in Hex and ASCII formats.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.current_interface = "B-Link (SWD)"
        self._worker: Optional[MemoryReadWorker] = None
        self._init_ui()
        self.scan_connected_probes()  # ⬅️ اسکن خودکار پروب‌ها در زمان باز شدن صفحه

    def _init_ui(self) -> None:
        """Constructs the control toolbar and hexadecimal dump table."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # -------------------------------------------------------------
        # Top Toolbar Group (3-Row Compact Grid for Responsive UX)
        # -------------------------------------------------------------
        ctrl_group = QGroupBox(" Device Memory Configuration")
        ctrl_group.setStyleSheet(
            """
            QGroupBox {
                border: 1px solid #1A2642;
                border-radius: 6px;
                margin-top: 10px;
                color: #00E5FF;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
            }
            """
        )

        ctrl_layout = QGridLayout(ctrl_group)
        ctrl_layout.setContentsMargins(12, 16, 12, 12)
        ctrl_layout.setHorizontalSpacing(12)
        ctrl_layout.setVerticalSpacing(10)

        COMBOBOX_STYLESHEET = """
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
            QComboBox::down-arrow {
                image: url(CHEVRON_DOWN);
                width: 12px;
                height: 12px;
            }
            QComboBox QAbstractItemView {
                background-color: #0F172A;
                color: #F8FAFC;
                selection-background-color: #0284C7;
                border: 1px solid #475569;
            }
        """
        COMBOBOX_STYLESHEET = COMBOBOX_STYLESHEET.replace(
            "CHEVRON_DOWN", QSS_CHEVRON_DOWN)

        # -------------------------------------------------------------
        # Row 0: Target Probe Selector ⬅️ (بخش جدید)
        # -------------------------------------------------------------
        ctrl_layout.addWidget(QLabel("Target Probe:"), 0, 0)
        self.combo_probe = QComboBox()
        self.combo_probe.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.combo_probe.setMinimumWidth(140)
        self.combo_probe.setStyleSheet(COMBOBOX_STYLESHEET)
        ctrl_layout.addWidget(self.combo_probe, 0, 1, 1, 2)

        self.btn_scan = QPushButton(" Scan")
        self.btn_scan.setIcon(
            QIcon(ICON_ARROWS_ROTATE))
        self.btn_scan.setMinimumHeight(30)
        self.btn_scan.setStyleSheet(
            """
            QPushButton {
                background-color: #121D38; color: white; font-weight: bold;
                padding: 6px 16px; border: 1px solid #1A2642; border-radius: 4px; 
            }
            QPushButton:hover { background-color: #00B4D8; border: 1px solid #00B4D8; }
            """
        )
        self.btn_scan.clicked.connect(self.scan_connected_probes)
        ctrl_layout.addWidget(self.btn_scan, 0, 3)

        # -------------------------------------------------------------
        # Row 1: Address Selector + Read Button
        # -------------------------------------------------------------
        ctrl_layout.addWidget(QLabel("Address:"), 1, 0)
        self.combo_address = QComboBox()
        self.combo_address.setEditable(True)
        self.combo_address.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.combo_address.setMinimumWidth(140)
        self.combo_address.setStyleSheet(COMBOBOX_STYLESHEET)

        for label, addr in MEMORY_PRESETS:
            self.combo_address.addItem(label, addr)
        ctrl_layout.addWidget(self.combo_address, 1, 1, 1, 2)

        self.btn_read = QPushButton(" Read Memory")
        self.btn_read.setIcon(QIcon(ICON_BOOK_OPEN))
        self.btn_read.setIconSize(QSize(16, 16))
        self.btn_read.setMinimumHeight(30)

        self.btn_read.setStyleSheet(
            """
            QPushButton {
                background-color: #121D38; color: white; font-weight: bold;
                padding: 6px 16px; border: 1px solid #1A2642; border-radius: 4px; text-align: center;
            }
            QPushButton:hover { background-color: #00B4D8; border: 1px solid #00B4D8;}
            QPushButton:pressed { background-color: #0077B6; }
            QPushButton:disabled { background-color: #070B19; color: #475569; border: 1px dashed #1A2642; }
            """
        )
        self.btn_read.clicked.connect(self._on_read_clicked)
        ctrl_layout.addWidget(self.btn_read, 1, 3)

        # -------------------------------------------------------------
        # Row 2: Size Input + Data Width Selection
        # -------------------------------------------------------------
        ctrl_layout.addWidget(QLabel("Size (Bytes):"), 2, 0)
        self.txt_size = QLineEdit("0x200")  # Default 512 bytes
        self.txt_size.setFixedWidth(85)
        self.txt_size.setStyleSheet(
            """
            QLineEdit {
                background-color: #070B19; color: #F8FAFC;
                border: 1px solid #1A2642; border-radius: 4px; padding: 4px;
            }
            QLineEdit:focus { border: 1px solid #00E5FF; }
            """
        )
        ctrl_layout.addWidget(self.txt_size, 2, 1)

        ctrl_layout.addWidget(QLabel("Data Width:"), 2, 2)
        self.combo_width = QComboBox()
        self.combo_width.addItems(["32-bit", "16-bit", "8-bit"])
        self.combo_width.setCurrentText("32-bit")
        self.combo_width.setFixedWidth(95)
        self.combo_width.setStyleSheet(COMBOBOX_STYLESHEET)

        self.combo_width.currentTextChanged.connect(
            self._reformat_current_view)
        ctrl_layout.addWidget(self.combo_width, 2, 3)

        ctrl_layout.setColumnStretch(1, 1)
        main_layout.addWidget(ctrl_group)

        # -------------------------------------------------------------
        # Hex & ASCII Memory Table Display
        # -------------------------------------------------------------
        self.table_memory = QTableWidget()
        self.table_memory.setFont(QFont("Consolas", 10))
        self.table_memory.setStyleSheet(
            """
            QTableWidget {
                background-color: #03060E; /* پس‌زمینه بسیار تیره */
                color: #E2E8F0;
                gridline-color: #1A2642; 
                border: 1px solid #1A2642;
                border-radius: 4px;
            }
            QTableWidget::item:selected {
                background-color: #0077B6;
            }
            QHeaderView::section {
                background-color: #0C1327; 
                color: #00E5FF; /* سایان برای هدرها */
                font-weight: bold; 
                padding: 4px; 
                border: 1px solid #1A2642;
            }
            """
        )
        self.table_memory.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self.table_memory.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        main_layout.addWidget(self.table_memory)

        self._cached_address: int = 0
        self._cached_data: List[int] = []

    # ⬅️ متد جدید برای اسکن سخت‌افزارها و پر کردن کمبوباکس
    @Slot()
    def scan_connected_probes(self) -> None:
        """Scans for connected hardware probes and populates the probe selector."""
        self.combo_probe.clear()
        probes = ProbeManagerService.discover_connected_probes()

        if not probes:
            self.combo_probe.addItem("No Probes Found (Auto-detect)", None)
        else:
            for probe in probes:
                # مقدار نمایشی به کاربر نشان داده می‌شود، مقدار دوم (unique_id) ذخیره می‌شود
                self.combo_probe.addItem(probe.display_name, probe.unique_id)

    def set_interface_type(self, interface_type: str) -> None:
        self.current_interface = interface_type

    def _parse_input_number(self, text: str) -> int:
        clean_text = text.strip()
        if clean_text.lower().startswith("0x"):
            return int(clean_text, 16)
        return int(clean_text)

    @Slot()
    def _on_read_clicked(self) -> None:
        try:
            addr_text = self.combo_address.currentText()
            if " - " in addr_text:
                addr_text = self.combo_address.currentData()

            start_address = self._parse_input_number(addr_text)
            size_bytes = self._parse_input_number(self.txt_size.text())

            if size_bytes <= 0 or size_bytes > 0x10000:
                raise ValueError(
                    "Size must be between 1 and 65536 (0x10000) bytes.")

            if size_bytes % 4 != 0:
                size_bytes += 4 - (size_bytes % 4)

        except ValueError as err:
            QMessageBox.warning(self, "Input Error",
                                f"Invalid input parameters: {str(err)}")
            return

        # ⬅️ دریافت آیدی پروب انتخاب شده (اگر None باشد یعنی خودکار پیدا کن)
        selected_probe_id = self.combo_probe.currentData()

        self.btn_read.setEnabled(False)
        self.btn_read.setIcon(QIcon(ICON_HOURGLASS))
        self.btn_read.setText(" Reading...")

        # ⬅️ ارسال آیدی پروب به ورکر
        self._worker = MemoryReadWorker(
            address=start_address,
            size_bytes=size_bytes,
            interface_type=self.current_interface,
            probe_id=selected_probe_id
        )
        self._worker.memory_read_finished.connect(
            self._on_memory_read_finished)
        self._worker.start()

    @Slot(bool, int, list, str)
    def _on_memory_read_finished(
        self, success: bool, address: int, data: List[int], error_msg: str
    ) -> None:
        self.btn_read.setEnabled(True)
        self.btn_read.setIcon(QIcon(ICON_BOOK_OPEN))
        self.btn_read.setText(" Read Memory")

        if not success:
            QMessageBox.critical(self, "Hardware Error", error_msg)
            return

        self._cached_address = address
        self._cached_data = data
        self._populate_memory_table()

    @Slot()
    def _reformat_current_view(self) -> None:
        if self._cached_data:
            self._populate_memory_table()

    def _populate_memory_table(self) -> None:
        data = self._cached_data
        width_mode = self.combo_width.currentText()

        if width_mode == "32-bit":
            headers = ["0x0", "0x4", "0x8", "0xC", "ASCII Dump"]
            col_count = 4
            step = 4
        elif width_mode == "16-bit":
            headers = ["0x0", "0x2", "0x4", "0x6",
                       "0x8", "0xA", "0xC", "0xE", "ASCII Dump"]
            col_count = 8
            step = 2
        else:
            headers = [f"0x{i:X}" for i in range(16)] + ["ASCII Dump"]
            col_count = 16
            step = 1

        self.table_memory.clear()
        self.table_memory.setColumnCount(len(headers))
        self.table_memory.setHorizontalHeaderLabels(headers)

        rows = (len(data) + 15) // 16
        self.table_memory.setRowCount(rows)

        row_headers = [
            f"0x{self._cached_address + (r * 16):08X}" for r in range(rows)]
        self.table_memory.setVerticalHeaderLabels(row_headers)

        for r in range(rows):
            row_bytes = data[r * 16: (r + 1) * 16]

            for c in range(0, 16, step):
                if c < len(row_bytes):
                    chunk = row_bytes[c: c + step]
                    if step == 4:
                        val = (
                            (chunk[3] << 24 | chunk[2] <<
                             16 | chunk[1] << 8 | chunk[0])
                            if len(chunk) == 4
                            else 0
                        )
                        cell_text = f"{val:08X}"
                    elif step == 2:
                        val = (
                            (chunk[1] << 8 | chunk[0])
                            if len(chunk) == 2
                            else 0
                        )
                        cell_text = f"{val:04X}"
                    else:
                        cell_text = f"{chunk[0]:02X}"
                else:
                    cell_text = ""

                item = QTableWidgetItem(cell_text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table_memory.setItem(r, c // step, item)

            ascii_chars = "".join(
                [chr(b) if 32 <= b <= 126 else "." for b in row_bytes]
            )
            ascii_item = QTableWidgetItem(ascii_chars)
            ascii_item.setForeground(QColor("#4EC9B0"))
            self.table_memory.setItem(r, col_count, ascii_item)

        self.table_memory.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table_memory.horizontalHeader().setMinimumSectionSize(45)

    def shutdown_threads(self) -> None:
        if self._worker and self._worker.isRunning():
            logger.info("Stopping MemoryReadWorker thread...")
            self._worker.quit()
            self._worker.wait()
            logger.info("✔ MemoryReadWorker thread stopped.")
