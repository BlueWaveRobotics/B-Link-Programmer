"""
Industrial Memory Viewer Widget providing STM32CubeProgrammer-like memory inspection.
Supports customizable base address, size, data width (8/16/32-bit), and live Hex/ASCII dump.
"""

from typing import Optional, List
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QGroupBox,
)

from src.common import get_logger
from src.features.memory_viewer.worker import MemoryReadWorker

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
        self._worker: Optional[MemoryReadWorker] = None
        self._init_ui()

    def _init_ui(self) -> None:
        """Constructs the control toolbar and hexadecimal dump table."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # -------------------------------------------------------------
        # Top Toolbar Group (Address, Size, Data Width, Read Button)
        # -------------------------------------------------------------
        ctrl_group = QGroupBox("Device Memory Configuration")
        ctrl_layout = QHBoxLayout(ctrl_group)
        ctrl_layout.setSpacing(12)

        # 1. Address ComboBox with presets & editable hex input
        ctrl_layout.addWidget(QLabel("Address:"))
        self.combo_address = QComboBox()
        self.combo_address.setEditable(True)
        self.combo_address.setMinimumWidth(220)
        for label, addr in MEMORY_PRESETS:
            self.combo_address.addItem(label, addr)
        ctrl_layout.addWidget(self.combo_address)

        # 2. Size input (in hex or decimal bytes)
        ctrl_layout.addWidget(QLabel("Size (Bytes):"))
        self.txt_size = QLineEdit("0x200")  # Default 512 bytes
        self.txt_size.setMaximumWidth(80)
        ctrl_layout.addWidget(self.txt_size)

        # 3. Data Width selection
        ctrl_layout.addWidget(QLabel("Data Width:"))
        self.combo_width = QComboBox()
        self.combo_width.addItems(["32-bit", "16-bit", "8-bit"])
        self.combo_width.setCurrentText("32-bit")
        self.combo_width.currentTextChanged.connect(
            self._reformat_current_view)
        ctrl_layout.addWidget(self.combo_width)

        ctrl_layout.addStretch()

        # 4. Read Button
        self.btn_read = QPushButton("📖 Read Memory")
        self.btn_read.setStyleSheet(
            """
            QPushButton {
                background-color: #2980B9; color: white; font-weight: bold;
                padding: 6px 16px; border-radius: 4px;
            }
            QPushButton:hover { background-color: #3498DB; }
            QPushButton:disabled { background-color: #555555; }
            """
        )
        self.btn_read.clicked.connect(self._on_read_clicked)
        ctrl_layout.addWidget(self.btn_read)

        main_layout.addWidget(ctrl_group)

        # -------------------------------------------------------------
        # Hex & ASCII Memory Table Display
        # -------------------------------------------------------------
        self.table_memory = QTableWidget()
        self.table_memory.setFont(QFont("Consolas", 10))
        self.table_memory.setStyleSheet(
            """
            QTableWidget {
                background-color: #1A1A1A; color: #E0E0E0;
                gridline-color: #333333; border: 1px solid #444444;
            }
            QHeaderView::section {
                background-color: #2D2D30; color: #CCCCCC;
                font-weight: bold; padding: 4px; border: 1px solid #3E3E42;
            }
            """
        )
        self.table_memory.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self.table_memory.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        main_layout.addWidget(self.table_memory)

        # Cache for holding raw read bytes to allow fast width re-formatting
        self._cached_address: int = 0
        self._cached_data: List[int] = []

    def _parse_input_number(self, text: str) -> int:
        """Parses hexadecimal (0x...) or decimal integer inputs safely."""
        clean_text = text.strip()
        if clean_text.lower().startswith("0x"):
            return int(clean_text, 16)
        return int(clean_text)

    @Slot()
    def _on_read_clicked(self) -> None:
        """Validates inputs and triggers background memory reading."""
        try:
            # Get address from combobox current text or user custom text
            addr_text = self.combo_address.currentText()
            if " - " in addr_text:
                addr_text = self.combo_address.currentData()

            start_address = self._parse_input_number(addr_text)
            size_bytes = self._parse_input_number(self.txt_size.text())

            if size_bytes <= 0 or size_bytes > 0x10000:
                raise ValueError(
                    "Size must be between 1 and 65536 (0x10000) bytes.")

            # Ensure 4-byte alignment for cleaner display
            if size_bytes % 4 != 0:
                size_bytes += 4 - (size_bytes % 4)

        except ValueError as err:
            QMessageBox.warning(self, "Input Error",
                                f"Invalid input parameters: {str(err)}")
            return

        # Disable UI during read
        self.btn_read.setEnabled(False)
        self.btn_read.setText("⏳ Reading...")

        # Start Worker
        self._worker = MemoryReadWorker(
            address=start_address, size_bytes=size_bytes)
        self._worker.memory_read_finished.connect(
            self._on_memory_read_finished)
        self._worker.start()

    @Slot(bool, int, list, str)
    def _on_memory_read_finished(
        self, success: bool, address: int, data: List[int], error_msg: str
    ) -> None:
        """Handles completion of the background memory read."""
        self.btn_read.setEnabled(True)
        self.btn_read.setText("📖 Read Memory")

        if not success:
            QMessageBox.critical(self, "Hardware Error", error_msg)
            return

        self._cached_address = address
        self._cached_data = data
        self._populate_memory_table()

    @Slot()
    def _reformat_current_view(self) -> None:
        """Re-renders the table when the user switches data width (8/16/32-bit)."""
        if self._cached_data:
            self._populate_memory_table()

    def _populate_memory_table(self) -> None:
        """
        Renders raw byte array into rows of 16 bytes formatted according
        to selected Data Width (Little-Endian) plus ASCII representation.
        """
        data = self._cached_data
        width_mode = self.combo_width.currentText()  # "32-bit", "16-bit", "8-bit"

        # Determine column count and headers based on data width (16 bytes per row)
        if width_mode == "32-bit":
            headers = ["0x0", "0x4", "0x8", "0xC", "ASCII Dump"]
            col_count = 4
            step = 4
        elif width_mode == "16-bit":
            headers = ["0x0", "0x2", "0x4", "0x6",
                       "0x8", "0xA", "0xC", "0xE", "ASCII Dump"]
            col_count = 8
            step = 2
        else:  # "8-bit"
            headers = [f"0x{i:X}" for i in range(16)] + ["ASCII Dump"]
            col_count = 16
            step = 1

        self.table_memory.clear()
        self.table_memory.setColumnCount(len(headers))
        self.table_memory.setHorizontalHeaderLabels(headers)

        rows = (len(data) + 15) // 16
        self.table_memory.setRowCount(rows)

        # Build row header addresses (0x08000000, 0x08000010, ...)
        row_headers = [
            f"0x{self._cached_address + (r * 16):08X}" for r in range(rows)]
        self.table_memory.setVerticalHeaderLabels(row_headers)

        # Fill table cells
        for r in range(rows):
            row_bytes = data[r * 16: (r + 1) * 16]

            # 1. Fill Hex data columns (handling ARM Little-Endian byte order)
            for c in range(0, 16, step):
                if c < len(row_bytes):
                    chunk = row_bytes[c: c + step]
                    if step == 4:
                        # 32-bit Little Endian: [B0, B1, B2, B3] -> 0xB3B2B1B0
                        val = (
                            (chunk[3] << 24 | chunk[2] <<
                             16 | chunk[1] << 8 | chunk[0])
                            if len(chunk) == 4
                            else 0
                        )
                        cell_text = f"{val:08X}"
                    elif step == 2:
                        # 16-bit Little Endian: [B0, B1] -> 0xB1B0
                        val = (
                            (chunk[1] << 8 | chunk[0])
                            if len(chunk) == 2
                            else 0
                        )
                        cell_text = f"{val:04X}"
                    else:
                        # 8-bit
                        cell_text = f"{chunk[0]:02X}"
                else:
                    cell_text = ""

                item = QTableWidgetItem(cell_text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table_memory.setItem(r, c // step, item)

            # 2. Fill ASCII column
            ascii_chars = "".join(
                [chr(b) if 32 <= b <= 126 else "." for b in row_bytes]
            )
            ascii_item = QTableWidgetItem(ascii_chars)
            # Soft teal color for ASCII
            ascii_item.setForeground(QColor("#4EC9B0"))
            self.table_memory.setItem(r, col_count, ascii_item)

        # Auto-resize columns nicely
        self.table_memory.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table_memory.horizontalHeader().setSectionResizeMode(
            col_count, QHeaderView.ResizeMode.Stretch
        )

    def shutdown_threads(self) -> None:
        """Safely stops active worker threads during application exit."""
        if self._worker and self._worker.isRunning():
            logger.info("Stopping MemoryReadWorker thread...")
            self._worker.quit()
            self._worker.wait()
            logger.info("✔ MemoryReadWorker thread stopped.")
