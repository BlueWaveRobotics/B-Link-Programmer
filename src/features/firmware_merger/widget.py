"""
Industrial UI Widget for Firmware Merging and Memory Offset Patching.
Allows users to add multiple firmware segments, define custom start offsets,
validate memory overlap, and export a unified binary image padded with 0xFF.
"""

import os
from typing import List, Optional
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QPushButton,
    QLabel,
    QLineEdit,
    QFileDialog,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QComboBox,
    QMessageBox,
    QAbstractItemView,
)

from src.common import get_logger
from src.features.firmware_merger.merger_service import (
    FirmwareSegment,
    FirmwareMergerService,
)

logger = get_logger("FirmwareMergerWidget")


class FirmwareMergerWidget(QWidget):
    """
    GUI panel for managing binary segments and exporting unified memory images.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.segments: List[FirmwareSegment] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(14)

        # ----------------------------------------------------------------------
        # 1. Add Segment Toolbar
        # ----------------------------------------------------------------------
        add_box = QGroupBox("Add Firmware Segment (.bin / .hex)")
        add_layout = QHBoxLayout(add_box)

        add_layout.addWidget(QLabel("File:"))
        self.txt_filepath = QLineEdit()
        self.txt_filepath.setPlaceholderText("Select binary segment file...")
        self.txt_filepath.setReadOnly(True)
        add_layout.addWidget(self.txt_filepath, stretch=1)

        self.btn_browse = QPushButton("Browse...")
        self.btn_browse.clicked.connect(self._browse_file)
        add_layout.addWidget(self.btn_browse)

        add_layout.addWidget(QLabel("Start Offset:"))
        self.txt_offset = QLineEdit("0x08000000")
        self.txt_offset.setFixedWidth(110)
        add_layout.addWidget(self.txt_offset)

        self.btn_add_segment = QPushButton("➕ Add to List")
        self.btn_add_segment.setStyleSheet(
            "background-color: #2980B9; color: white; font-weight: bold; padding: 6px 14px;"
        )
        self.btn_add_segment.clicked.connect(self._add_segment_to_list)
        add_layout.addWidget(self.btn_add_segment)

        main_layout.addWidget(add_box)

        # ----------------------------------------------------------------------
        # 2. Segments Table Display
        # ----------------------------------------------------------------------
        table_box = QGroupBox("Memory Layout Segments (Sorted by Address)")
        table_layout = QVBoxLayout(table_box)

        self.table_segments = QTableWidget()
        self.table_segments.setColumnCount(4)
        self.table_segments.setHorizontalHeaderLabels([
            "Segment Name",
            "Start Offset",
            "Size (Bytes)",
            "File Path",
        ])
        self.table_segments.setFont(QFont("Consolas", 10))
        self.table_segments.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table_segments.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table_segments.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table_segments.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table_segments.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table_segments.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table_segments.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch
        )

        table_layout.addWidget(self.table_segments)

        # Table Control Buttons
        btn_table_layout = QHBoxLayout()
        self.btn_remove_selected = QPushButton("🗑 Remove Selected")
        self.btn_remove_selected.clicked.connect(self._remove_selected_segment)

        self.btn_clear_all = QPushButton("Clear All")
        self.btn_clear_all.clicked.connect(self._clear_all_segments)

        btn_table_layout.addWidget(self.btn_remove_selected)
        btn_table_layout.addWidget(self.btn_clear_all)
        btn_table_layout.addStretch()
        table_layout.addLayout(btn_table_layout)

        main_layout.addWidget(table_box, stretch=1)

        # ----------------------------------------------------------------------
        # 3. Export Controls & Fill Byte Configuration
        # ----------------------------------------------------------------------
        export_box = QGroupBox("Merge & Export Settings")
        export_layout = QHBoxLayout(export_box)

        export_layout.addWidget(QLabel("Gap Fill Byte:"))
        self.combo_fill_byte = QComboBox()
        self.combo_fill_byte.addItems([
            "0xFF (Standard Flash Blank)",
            "0x00 (Zero Padding)",
        ])
        self.combo_fill_byte.setCurrentIndex(0)
        export_layout.addWidget(self.combo_fill_byte)

        export_layout.addStretch()

        self.btn_merge_export = QPushButton("⚡ MERGE & EXPORT UNIFIED BINARY")
        self.btn_merge_export.setMinimumHeight(44)
        self.btn_merge_export.setStyleSheet(
            "background-color: #2E8B57; color: white; font-weight: bold; font-size: 13px; padding: 0 20px;"
        )
        self.btn_merge_export.clicked.connect(self._merge_and_export)
        export_layout.addWidget(self.btn_merge_export)

        main_layout.addWidget(export_box)

    def _browse_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Firmware Segment File",
            "",
            "Firmware Files (*.bin *.hex);;All Files (*.*)",
        )
        if file_path:
            self.txt_filepath.setText(os.path.normpath(file_path))

    def _parse_offset(self, text: str) -> int:
        clean = text.strip()
        return int(clean, 16) if clean.lower().startswith("0x") else int(clean)

    @Slot()
    def _add_segment_to_list(self) -> None:
        file_path = self.txt_filepath.text().strip()
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(
                self, "Invalid File", "Please select a valid binary file."
            )
            return

        try:
            offset_addr = self._parse_offset(self.txt_offset.text())
        except ValueError:
            QMessageBox.critical(
                self, "Offset Error", "Invalid start offset hexadecimal address."
            )
            return

        # Create segment and append
        seg = FirmwareSegment(file_path=file_path, offset_address=offset_addr)
        if seg.size_bytes == 0:
            QMessageBox.warning(
                self, "Empty File", "The selected binary file is empty (0 bytes)."
            )
            return

        self.segments.append(seg)
        self._refresh_segments_table()
        logger.info(
            f"Added segment '{seg.name}' @ 0x{seg.offset_address:08X} ({seg.size_bytes} bytes)"
        )

    def _refresh_segments_table(self) -> None:
        """Sorts segments by address and rebuilds the display table."""
        self.segments.sort(key=lambda s: s.offset_address)
        self.table_segments.setRowCount(len(self.segments))

        for row, seg in enumerate(self.segments):
            item_name = QTableWidgetItem(seg.name)
            item_addr = QTableWidgetItem(f"0x{seg.offset_address:08X}")
            item_size = QTableWidgetItem(str(seg.size_bytes))
            item_path = QTableWidgetItem(seg.file_path)

            item_addr.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_size.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.table_segments.setItem(row, 0, item_name)
            self.table_segments.setItem(row, 1, item_addr)
            self.table_segments.setItem(row, 2, item_size)
            self.table_segments.setItem(row, 3, item_path)

    @Slot()
    def _remove_selected_segment(self) -> None:
        selected_row = self.table_segments.currentRow()
        if selected_row < 0 or selected_row >= len(self.segments):
            return
        removed = self.segments.pop(selected_row)
        self._refresh_segments_table()
        logger.info(f"Removed segment '{removed.name}' from list.")

    @Slot()
    def _clear_all_segments(self) -> None:
        self.segments.clear()
        self._refresh_segments_table()
        logger.info("Cleared all firmware segments.")

    def _validate_overlap(self) -> bool:
        """Checks if any adjacent segments overlap in memory address space."""
        for i in range(len(self.segments) - 1):
            curr = self.segments[i]
            nxt = self.segments[i + 1]
            curr_end = curr.offset_address + curr.size_bytes
            if curr_end > nxt.offset_address:
                QMessageBox.critical(
                    self,
                    "Memory Overlap Error",
                    f"Segment '{curr.name}' ends at 0x{curr_end:08X}, which overlaps "
                    f"with segment '{nxt.name}' starting at 0x{nxt.offset_address:08X}.\n\n"
                    "Please adjust segment start offsets.",
                )
                return False
        return True

    @Slot()
    def _merge_and_export(self) -> None:
        if len(self.segments) < 1:
            QMessageBox.warning(
                self,
                "No Segments",
                "Please add at least one binary segment to export.",
            )
            return

        if not self._validate_overlap():
            return

        fill_byte = 0xFF if "0xFF" in self.combo_fill_byte.currentText() else 0x00

        try:
            merged_bytes, base_addr, meta = (
                FirmwareMergerService.merge_segments(
                    segments=self.segments, fill_byte=fill_byte
                )
            )
        except Exception as exc:
            QMessageBox.critical(
                self, "Merge Failed", f"An error occurred during merge: {str(exc)}"
            )
            return

        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Unified Binary Image",
            "Unified_Firmware_Image.bin",
            "Binary Files (*.bin);;All Files (*.*)",
        )
        if not output_path:
            return

        if FirmwareMergerService.export_to_file(output_path, merged_bytes):
            QMessageBox.information(
                self,
                "Export Successful",
                f"Unified binary successfully created!\n\n"
                f"File: {os.path.basename(output_path)}\n"
                f"Base Address: 0x{base_addr:08X}\n"
                f"Total Size: {meta['total_size_bytes']} bytes ({meta['total_size_bytes'] / 1024:.2f} KB)\n"
                f"Segments Merged: {meta['segment_count']}",
            )
        else:
            QMessageBox.critical(
                self, "Export Error", "Failed to write merged file to disk."
            )

    def shutdown_threads(self) -> None:
        """Lifecycle clean-up hook for main window exit."""
        pass
