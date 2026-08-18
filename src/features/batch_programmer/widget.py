"""
Industrial Batch Programmer UI Widget for parallel STM32 multi-target deployment.
Integrates dynamic DAPLink probe discovery, per-slot visual status cards,
firmware selection, and synchronized multi-threaded batch execution and chip erasing.
"""

import os
from typing import Dict, List, Optional
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QIcon, QColor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QGroupBox,
    QPushButton,
    QLabel,
    QLineEdit,
    QFileDialog,
    QComboBox,
    QCheckBox,
    QMessageBox,
    QScrollArea,
    QTextEdit,
)

from src.common import get_logger
from src.features.batch_programmer.probe_manager import ProbeManagerService, ProbeInfo
from src.features.batch_programmer.worker import BatchProgrammerCoordinator
from src.features.batch_programmer.probe_card import ProbeSlotCard

logger = get_logger("BatchProgrammerWidget")

ADDRESS_PRESETS = [
    ("0x08000000 - Main Flash Memory (Default Start)", "0x08000000"),
    ("0x08004000 - Application Offset (16 KB Bootloader)", "0x08004000"),
    ("0x08008000 - Application Offset (32 KB Bootloader)", "0x08008000"),
    ("0x08010000 - Application Offset (64 KB Bootloader)", "0x08010000"),
]

BLUEWAVE_STYLE = """
/* تنظیمات پایه ویجت */
QWidget {
    background-color: #070B19;
    color: #F8FAFC;
    font-family: "Segoe UI", Arial, sans-serif;
}

/* باکس‌های گروه‌بندی - فشرده‌تر شده برای ذخیره فضا */
QGroupBox {
    border: 1px solid #1A2642;
    border-radius: 4px;
    margin-top: 10px;
    padding-top: 12px;
    background-color: #0C1327;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 0px;
    padding: 0 4px;
    color: #00E5FF;
    font-weight: bold;
    background: transparent;
}

/* لیبل‌ها */
QLabel {
    background: transparent;
    color: #94A3B8;
}

/* فیلدهای متنی */
QLineEdit {
    background-color: #070B19;
    color: #F8FAFC;
    border: 1px solid #1A2642;
    border-radius: 4px;
    padding: 4px 6px;
}
QLineEdit:read-only {
    color: #94A3B8;
}
QLineEdit:read-only[hasFile="true"] {
    border: 1px solid #00E5FF;
    color: #00E5FF;
}

/* دکمه‌های اصلی پیش‌فرض */
QPushButton {
    background-color: #121D38;
    border: 1px solid #1A2642;
    border-radius: 4px;
    color: #F8FAFC;
    padding: 6px 12px;
}
QPushButton:hover {
    background-color: #00B4D8;
    color: #FFFFFF;
}
QPushButton:disabled {
    background-color: #070B19;
    color: #94A3B8;
    border: 1px solid #1A2642;
}

/* 🔵 1. دکمه Start Batch */
QPushButton#btnStartBatch {
    background-color: #121D38;
    color: #00E5FF;
    border: 1px solid #00E5FF;
}
QPushButton#btnStartBatch:hover {
    background-color: #00B4D8;
    color: #FFFFFF;
    border: 1px solid #00B4D8;
}

/* 🔴 2. دکمه Full Chip Erase */
QPushButton#btnChipErase {
    background-color: #121D38;
    color: #EF4444;
    border: 1px solid #EF4444;
}
QPushButton#btnChipErase:hover {
    background-color: #EF4444;
    color: #FFFFFF;
    border: 1px solid #EF4444;
}

/* منوی کشویی */
QComboBox {
    background-color: #070B19;
    border: 1px solid #1A2642;
    border-radius: 4px;
    color: #F8FAFC;
    padding: 4px 6px;
}
QComboBox:hover {
    border: 1px solid #00B4D8;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border-left: 1px solid #1A2642;
}
QComboBox::down-arrow {
    image: url(assets/icons/chevron-down-solid-full.svg);
    width: 14px;
    height: 14px;
}

/* چک‌باکس */
QCheckBox {
    color: #F8FAFC;
    background-color: transparent;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #1A2642;
    border-radius: 4px;
    background-color: #070B19;
}
QCheckBox:checked {
    color: #00E5FF;
}
QCheckBox::indicator:checked {
    background-color: #00E5FF;
    border: 1px solid #00E5FF;
    image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%23070B19' stroke-width='4' stroke-linecap='round' stroke-linejoin='round'><polyline points='20 6 9 17 4 12'></polyline></svg>");
}

/* کارت اسلات‌ها */
QGroupBox#ProbeSlotCard {
    border: 1px solid #1A2642;
    border-radius: 4px;
    background-color: #0C1327;
    margin-top: 4px;
    padding-top: 10px;
}
QGroupBox#ProbeSlotCard[status="PASS"] {
    border-left: 4px solid #10B981;
}
QGroupBox#ProbeSlotCard[status="FAIL"] {
    border-left: 4px solid #EF4444;
}
QGroupBox#ProbeSlotCard[status="BUSY"] {
    border-left: 4px solid #00E5FF;
}
QGroupBox#ProbeSlotCard[status="NORMAL"] {
    border-left: 4px solid #1A2642;
}

/* ترمینال (Log) */
QTextEdit#terminalConsole {
    background-color: #03060E;
    color: #00FF66;
    border: 1px solid #1A2642;
    border-radius: 4px;
    font-family: Consolas, monospace;
    font-size: 13px;
    padding: 6px;
}
"""


class BatchProgrammerWidget(QWidget):
    """
    Master GUI panel for multi-target simultaneous STM32 production programming & erasing.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.coordinator = BatchProgrammerCoordinator(self)
        self.slot_cards: Dict[str, ProbeSlotCard] = {}

        self.setStyleSheet(BLUEWAVE_STYLE)

        self._setup_ui()
        self._connect_coordinator_signals()
        self.scan_connected_probes()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # ----------------------------------------------------------------------
        # 1. Hardware Bus & Firmware Setup Header
        # ----------------------------------------------------------------------
        setup_box = QGroupBox("Batch Firmware & SWD Bus Configuration")
        setup_layout = QVBoxLayout(setup_box)
        setup_layout.setContentsMargins(8, 14, 8, 8)
        setup_layout.setSpacing(8)

        file_layout = QHBoxLayout()
        self.txt_filepath = QLineEdit()
        self.txt_filepath.setPlaceholderText(
            "Select shared firmware binary (.hex / .bin)...")
        self.txt_filepath.setReadOnly(True)

        self.btn_browse = QPushButton(" Browse...")
        self.btn_browse.setIcon(
            QIcon("assets/icons/folder-open-solid-full.svg"))
        self.btn_browse.clicked.connect(self._select_file)

        file_layout.addWidget(QLabel("Firmware:"))
        file_layout.addWidget(self.txt_filepath, stretch=1)
        file_layout.addWidget(self.btn_browse)
        setup_layout.addLayout(file_layout)

        cfg_layout = QHBoxLayout()
        cfg_layout.addWidget(QLabel("Base Address:"))
        self.combo_address = QComboBox()
        self.combo_address.setEditable(True)
        for label, addr in ADDRESS_PRESETS:
            self.combo_address.addItem(label, addr)
        cfg_layout.addWidget(self.combo_address, stretch=1)

        cfg_layout.addWidget(QLabel("SWD Clock:"))
        self.combo_clock = QComboBox()
        self.combo_clock.addItems(
            ["1000 kHz", "2000 kHz", "4000 kHz", "500 kHz"])
        self.combo_clock.setCurrentText("1000 kHz")
        cfg_layout.addWidget(self.combo_clock)

        cfg_layout.addWidget(QLabel("Connect Mode:"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["under-reset", "attach", "normal"])
        self.combo_mode.setCurrentText("under-reset")
        cfg_layout.addWidget(self.combo_mode)

        self.chk_verify = QCheckBox("Verify after Flash")
        self.chk_verify.setChecked(True)
        cfg_layout.addWidget(self.chk_verify)

        setup_layout.addLayout(cfg_layout)

        main_layout.addWidget(setup_box, stretch=0)

        # ----------------------------------------------------------------------
        # 2. Dynamic Probe Slots Area (Scrollable Grid)
        # ----------------------------------------------------------------------
        slots_box = QGroupBox("Detected DAPLink Probe Slots")
        slots_main_layout = QVBoxLayout(slots_box)
        slots_main_layout.setContentsMargins(8, 14, 8, 8)
        slots_main_layout.setSpacing(6)

        toolbar_layout = QHBoxLayout()
        self.lbl_probe_count = QLabel("Active Probes: 0")
        self.lbl_probe_count.setStyleSheet(
            "font-weight: bold; color: #10B981;")

        self.btn_scan = QPushButton(" Scan / Refresh Probes")
        self.btn_scan.setIcon(
            QIcon("assets/icons/arrows-rotate-solid-full.svg"))
        self.btn_scan.clicked.connect(self.scan_connected_probes)

        toolbar_layout.addWidget(self.lbl_probe_count)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.btn_scan)
        slots_main_layout.addLayout(toolbar_layout)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }")

        self.slots_container = QWidget()
        self.slots_container.setStyleSheet("background: transparent;")
        self.slots_grid = QGridLayout(self.slots_container)
        self.slots_grid.setSpacing(10)

        self.scroll_area.setWidget(self.slots_container)

        slots_main_layout.addWidget(self.scroll_area, stretch=1)

        main_layout.addWidget(slots_box, stretch=2)

        # ----------------------------------------------------------------------
        # 3. Batch Execution Action Bar & Summary Console
        # ----------------------------------------------------------------------
        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)

        self.btn_start_batch = QPushButton(" START BATCH PRODUCTION FLASH")
        self.btn_start_batch.setObjectName("btnStartBatch")
        self.btn_start_batch.setIcon(
            QIcon("assets/icons/pen-to-square-solid-full.svg"))
        self.btn_start_batch.setMinimumHeight(40)
        self.btn_start_batch.clicked.connect(self._start_batch_flashing)

        self.btn_chip_erase = QPushButton(" FULL CHIP ERASE (ALL SLOTS)")
        self.btn_chip_erase.setObjectName("btnChipErase")
        self.btn_chip_erase.setIcon(
            QIcon("assets/icons/eraser-solid-full.svg"))
        self.btn_chip_erase.setMinimumHeight(40)
        self.btn_chip_erase.clicked.connect(self._start_batch_chip_erase)

        action_layout.addWidget(self.btn_start_batch, stretch=2)
        action_layout.addWidget(self.btn_chip_erase, stretch=1)

        main_layout.addLayout(action_layout)

        # Compact Log Display
        self.log_viewer = QTextEdit()
        self.log_viewer.setObjectName("terminalConsole")
        self.log_viewer.setReadOnly(True)
        self.log_viewer.setMinimumHeight(120)

        main_layout.addWidget(self.log_viewer, stretch=2)

        self._append_log(
            "[SYSTEM] Batch Programmer Suite Ready. Please scan connected DAPLink probes.")

    def _connect_coordinator_signals(self) -> None:
        """Wires batch coordinator signals to UI state handlers."""
        self.coordinator.batch_started_signal.connect(self._on_batch_started)
        self.coordinator.batch_progress_signal.connect(self._on_slot_progress)
        self.coordinator.batch_slot_status_signal.connect(self._on_slot_status)
        self.coordinator.batch_completed_signal.connect(
            self._on_batch_completed)

    @Slot()
    def scan_connected_probes(self) -> None:
        """Discovers active hardware probes and rebuilds slot cards in a responsive grid."""
        self._clear_slot_cards()
        probes: List[ProbeInfo] = ProbeManagerService.discover_connected_probes()

        if not probes:
            self.lbl_probe_count.setText(
                "Active Probes: 0 (No DAPLink devices found)")
            self.lbl_probe_count.setStyleSheet(
                "font-weight: bold; color: #EF4444;")
            self._append_log(
                "[WARNING] No DAPLink hardware probes detected on USB bus.")
            return

        self.lbl_probe_count.setText(f"Active Probes: {len(probes)} detected")
        self.lbl_probe_count.setStyleSheet(
            "font-weight: bold; color: #10B981;")

        for idx, probe_info in enumerate(probes):
            card = ProbeSlotCard(probe_info=probe_info,
                                 parent=self.slots_container)

            card.setObjectName("ProbeSlotCard")
            card.setProperty("status", "NORMAL")

            row, col = divmod(idx, 2)
            self.slots_grid.addWidget(card, row, col)
            self.slot_cards[probe_info.unique_id] = card

        self._append_log(
            f"[INFO] Enumerate complete. Displaying {len(probes)} probe slots.")

    def _clear_slot_cards(self) -> None:
        """Removes existing slot cards from UI grid."""
        while self.slots_grid.count():
            item = self.slots_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.slot_cards.clear()

    def _select_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Shared Firmware", "", "Firmware Files (*.hex *.bin);;All Files (*)"
        )
        if file_path:
            self.txt_filepath.setText(os.path.normpath(file_path))

            self.txt_filepath.setProperty("hasFile", True)
            self.txt_filepath.style().unpolish(self.txt_filepath)
            self.txt_filepath.style().polish(self.txt_filepath)

            self._append_log(f"[INFO] Selected firmware: {file_path}")

    def _parse_input_address(self, text: str) -> int:
        clean_text = text.strip()
        if " - " in clean_text:
            clean_text = self.combo_address.currentData()
        return int(clean_text, 16) if clean_text.lower().startswith("0x") else int(clean_text)

    def _parse_clock_freq(self) -> int:
        freq_str = self.combo_clock.currentText().split()[0]
        return int(freq_str) * 1000

    def _get_enabled_probe_ids(self) -> List[str]:
        """Returns unique IDs of all checked probe slots."""
        return [uid for uid, card in self.slot_cards.items() if card.is_slot_enabled]

    def _set_action_buttons_enabled(self, enabled: bool) -> None:
        """Toggles main action controls during background execution."""
        self.btn_start_batch.setEnabled(enabled)
        self.btn_chip_erase.setEnabled(enabled)
        self.btn_scan.setEnabled(enabled)

    def _start_batch_flashing(self) -> None:
        file_path = self.txt_filepath.text().strip()
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(
                self, "Invalid File", "Please select a valid firmware file before flashing.")
            return

        enabled_ids = self._get_enabled_probe_ids()
        if not enabled_ids:
            QMessageBox.warning(self, "No Active Slots",
                                "Please enable at least one probe slot.")
            return

        try:
            base_addr = self._parse_input_address(
                self.combo_address.currentText())
            clock_freq = self._parse_clock_freq()
        except ValueError as err:
            QMessageBox.critical(self, "Configuration Error",
                                 f"Invalid numeric format: {str(err)}")
            return

        for uid in enabled_ids:
            if uid in self.slot_cards:
                self.slot_cards[uid].set_busy_state(
                    "Waiting for flash thread spawn...")

                card = self.slot_cards[uid]
                card.setProperty("status", "BUSY")
                card.style().unpolish(card)
                card.style().polish(card)

        self._set_action_buttons_enabled(False)

        self.btn_start_batch.setIcon(
            QIcon("assets/icons/hourglass-half-solid-full.svg"))
        self.btn_start_batch.setText(" FLASHING IN PROGRESS...")

        self._append_log(
            f"[BATCH FLASH START] Launching simultaneous programming on {len(enabled_ids)} targets...")
        self.coordinator.start_batch_flashing(
            enabled_probe_ids=enabled_ids,
            file_path=file_path,
            base_address=base_addr,
            clock_freq=clock_freq,
            connect_mode=self.combo_mode.currentText(),
            verify_enabled=self.chk_verify.isChecked(),
        )

    def _start_batch_chip_erase(self) -> None:
        """Triggers simultaneous Full Chip Erase across all enabled slots."""
        enabled_ids = self._get_enabled_probe_ids()
        if not enabled_ids:
            QMessageBox.warning(self, "No Active Slots",
                                "Please enable at least one probe slot.")
            return

        reply = QMessageBox.question(
            self,
            "Confirm Batch Chip Erase",
            f"Are you sure you want to perform FULL CHIP ERASE on {len(enabled_ids)} connected target(s)?\n\n"
            "This will completely wipe internal flash memory across all enabled slots simultaneously.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            clock_freq = self._parse_clock_freq()
        except ValueError as err:
            QMessageBox.critical(self, "Configuration Error",
                                 f"Invalid numeric format: {str(err)}")
            return

        for uid in enabled_ids:
            if uid in self.slot_cards:
                self.slot_cards[uid].set_busy_state("Erasing target flash...")

                card = self.slot_cards[uid]
                card.setProperty("status", "BUSY")
                card.style().unpolish(card)
                card.style().polish(card)

        self._set_action_buttons_enabled(False)

        self.btn_chip_erase.setIcon(
            QIcon("assets/icons/hourglass-half-solid-full.svg"))
        self.btn_chip_erase.setText(" ERASING IN PROGRESS...")

        self._append_log(
            f"[BATCH ERASE START] Launching simultaneous Full Chip Erase on {len(enabled_ids)} targets...")
        self.coordinator.start_batch_chip_erase(
            enabled_probe_ids=enabled_ids,
            clock_freq=clock_freq,
            connect_mode=self.combo_mode.currentText(),
        )

    @Slot(int)
    def _on_batch_started(self, slot_count: int) -> None:
        self._append_log(
            f"[INFO] Parallel QThreads running across {slot_count} slots.")

    @Slot(str, int)
    def _on_slot_progress(self, unique_id: str, percent: int) -> None:
        if unique_id in self.slot_cards:
            self.slot_cards[unique_id].update_progress(percent)

    @Slot(str, str, str, float, str)
    def _on_slot_status(self, unique_id: str, status_code: str, message: str, cycle_time: float, chip_uid: str) -> None:
        if unique_id not in self.slot_cards:
            return

        card = self.slot_cards[unique_id]
        if status_code == "BUSY":
            card.set_busy_state(message)
            card.setProperty("status", "BUSY")
        elif status_code == "PASS":
            card.set_pass_state(cycle_time=cycle_time, uid_str=chip_uid)
            card.setProperty("status", "PASS")
            self._append_log(
                f"[PASS] Slot [{unique_id[:8]}]: UID={chip_uid} ({cycle_time:.2f}s)")
        elif status_code == "FAIL":
            card.set_fail_state(error_msg=message, cycle_time=cycle_time)
            card.setProperty("status", "FAIL")
            self._append_log(f"[FAIL] Slot [{unique_id[:8]}]: {message}")

        card.style().unpolish(card)
        card.style().polish(card)

    @Slot(int, int, float)
    def _on_batch_completed(self, total_pass: int, total_fail: int, duration: float) -> None:
        self._set_action_buttons_enabled(True)

        self.btn_start_batch.setIcon(
            QIcon("assets/icons/pen-to-square-solid-full.svg"))
        self.btn_start_batch.setText(" START BATCH PRODUCTION FLASH")

        self.btn_chip_erase.setIcon(
            QIcon("assets/icons/eraser-solid-full.svg"))
        self.btn_chip_erase.setText(" FULL CHIP ERASE (ALL SLOTS)")

        self._append_log(
            f"[BATCH FINISHED] Total PASS: {total_pass} | Total FAIL: {total_fail} | Total Time: {duration:.2f}s")

    def _append_log(self, text: str) -> None:
        self.log_viewer.append(text)
        self.log_viewer.verticalScrollBar().setValue(
            self.log_viewer.verticalScrollBar().maximum())

    def shutdown_threads(self) -> None:
        """Safely terminates all active batch worker threads during application shutdown."""
        if hasattr(self, "coordinator"):
            self.coordinator.stop_all_workers()
