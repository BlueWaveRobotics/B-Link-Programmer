"""
Industrial Batch Programmer UI Widget for parallel STM32 multi-target deployment.
Integrates dynamic DAPLink probe discovery, per-slot visual status cards,
firmware selection, and synchronized multi-threaded batch execution and chip erasing.
"""

import os
from typing import Dict, List, Optional
from PySide6.QtCore import Qt, Slot
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
from src.features.batch_programmer.probe_card import ProbeSlotCard
from src.features.batch_programmer.worker import BatchProgrammerCoordinator

logger = get_logger("BatchProgrammerWidget")

ADDRESS_PRESETS = [
    ("0x08000000 - Main Flash Memory (Default Start)", "0x08000000"),
    ("0x08004000 - Application Offset (16 KB Bootloader)", "0x08004000"),
    ("0x08008000 - Application Offset (32 KB Bootloader)", "0x08008000"),
    ("0x08010000 - Application Offset (64 KB Bootloader)", "0x08010000"),
]


class BatchProgrammerWidget(QWidget):
    """
    Master GUI panel for multi-target simultaneous STM32 production programming & erasing.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.coordinator = BatchProgrammerCoordinator(self)
        self.slot_cards: Dict[str, ProbeSlotCard] = {}

        self._setup_ui()
        self._connect_coordinator_signals()
        self.scan_connected_probes()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(14)

        # ----------------------------------------------------------------------
        # 1. Hardware Bus & Firmware Setup Header
        # ----------------------------------------------------------------------
        setup_box = QGroupBox("Batch Firmware & SWD Bus Configuration")
        setup_layout = QVBoxLayout(setup_box)

        # Firmware File Selector Row
        file_layout = QHBoxLayout()
        self.txt_filepath = QLineEdit()
        self.txt_filepath.setPlaceholderText(
            "Select shared firmware binary (.hex / .bin)...")
        self.txt_filepath.setReadOnly(True)

        self.btn_browse = QPushButton("Browse...")
        self.btn_browse.clicked.connect(self._select_file)

        file_layout.addWidget(QLabel("Firmware:"))
        file_layout.addWidget(self.txt_filepath, stretch=1)
        file_layout.addWidget(self.btn_browse)
        setup_layout.addLayout(file_layout)

        # Addressing & SWD Clock Row
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
        main_layout.addWidget(setup_box)

        # ----------------------------------------------------------------------
        # 2. Dynamic Probe Slots Area (Scrollable Grid)
        # ----------------------------------------------------------------------
        slots_box = QGroupBox("Detected DAPLink Probe Slots")
        slots_main_layout = QVBoxLayout(slots_box)

        toolbar_layout = QHBoxLayout()
        self.lbl_probe_count = QLabel("Active Probes: 0")
        self.lbl_probe_count.setStyleSheet(
            "font-weight: bold; color: #4EC9B0;")

        self.btn_scan = QPushButton("🔍 Scan / Refresh Probes")
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
        self.slots_grid = QGridLayout(self.slots_container)
        self.slots_grid.setSpacing(12)
        self.scroll_area.setWidget(self.slots_container)

        slots_main_layout.addWidget(self.scroll_area, stretch=1)
        main_layout.addWidget(slots_box, stretch=1)

        # ----------------------------------------------------------------------
        # 3. Batch Execution Action Bar & Summary Console
        # ----------------------------------------------------------------------
        action_layout = QHBoxLayout()

        self.btn_start_batch = QPushButton("⚡ START BATCH PRODUCTION FLASH")
        self.btn_start_batch.setMinimumHeight(48)
        self.btn_start_batch.setStyleSheet(
            "background-color: #2E8B57; color: white; font-weight: bold; font-size: 13px;"
        )
        self.btn_start_batch.clicked.connect(self._start_batch_flashing)

        self.btn_chip_erase = QPushButton("🗑 FULL CHIP ERASE (ALL SLOTS)")
        self.btn_chip_erase.setMinimumHeight(48)
        self.btn_chip_erase.setStyleSheet(
            "background-color: #D35400; color: white; font-weight: bold; font-size: 13px;"
        )
        self.btn_chip_erase.clicked.connect(self._start_batch_chip_erase)

        self.btn_stop = QPushButton("🛑 Stop All")
        self.btn_stop.setMinimumHeight(48)
        self.btn_stop.setFixedWidth(110)
        self.btn_stop.setStyleSheet(
            "background-color: #C0392B; color: white; font-weight: bold;")
        self.btn_stop.clicked.connect(self._stop_batch_execution)
        self.btn_stop.setEnabled(False)

        action_layout.addWidget(self.btn_start_batch, stretch=2)
        action_layout.addWidget(self.btn_chip_erase, stretch=1)
        action_layout.addWidget(self.btn_stop)
        main_layout.addLayout(action_layout)

        # Compact Log Display
        self.log_viewer = QTextEdit()
        self.log_viewer.setReadOnly(True)
        self.log_viewer.setMaximumHeight(95)
        self.log_viewer.setStyleSheet(
            "background-color: #181A1F; color: #58D68D; font-family: Consolas, monospace; font-size: 11px;"
        )
        main_layout.addWidget(self.log_viewer)
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
                "font-weight: bold; color: #E74C3C;")
            self._append_log(
                "[WARNING] No DAPLink hardware probes detected on USB bus.")
            return

        self.lbl_probe_count.setText(f"Active Probes: {len(probes)} detected")
        self.lbl_probe_count.setStyleSheet(
            "font-weight: bold; color: #58D68D;")

        for idx, probe_info in enumerate(probes):
            card = ProbeSlotCard(probe_info=probe_info,
                                 parent=self.slots_container)
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
        self.btn_stop.setEnabled(not enabled)

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

        self._set_action_buttons_enabled(False)
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

        self._set_action_buttons_enabled(False)
        self._append_log(
            f"[BATCH ERASE START] Launching simultaneous Full Chip Erase on {len(enabled_ids)} targets...")
        self.coordinator.start_batch_chip_erase(
            enabled_probe_ids=enabled_ids,
            clock_freq=clock_freq,
            connect_mode=self.combo_mode.currentText(),
        )

    def _stop_batch_execution(self) -> None:
        """Terminates active workers safely."""
        self._append_log("[WARNING] Stopping all parallel batch workers...")
        self.coordinator.stop_all_workers()
        self._on_batch_completed(0, 0, 0.0)

    @Slot(int)
    def _on_batch_started(self, slot_count: int) -> None:
        self._append_log(
            f"[INFO] Parallel QThreads running across {slot_count} slots.")

    @Slot(str, int)
    def _on_slot_progress(self, unique_id: str, percent: int) -> None:
        if unique_id in self.slot_cards:
            self.slot_cards[unique_id].update_progress(percent)

    @Slot(str, str, str, float, str)
    def _on_slot_status(
        self, unique_id: str, status_code: str, message: str, cycle_time: float, chip_uid: str
    ) -> None:
        if unique_id not in self.slot_cards:
            return

        card = self.slot_cards[unique_id]
        if status_code == "BUSY":
            card.set_busy_state(message)
        elif status_code == "PASS":
            card.set_pass_state(cycle_time=cycle_time, uid_str=chip_uid)
            self._append_log(
                f"[PASS] Slot [{unique_id[:8]}]: UID={chip_uid} ({cycle_time:.2f}s)")
        elif status_code == "FAIL":
            card.set_fail_state(error_msg=message, cycle_time=cycle_time)
            self._append_log(f"[FAIL] Slot [{unique_id[:8]}]: {message}")

    @Slot(int, int, float)
    def _on_batch_completed(self, total_pass: int, total_fail: int, duration: float) -> None:
        self._set_action_buttons_enabled(True)
        self._append_log(
            f"[BATCH FINISHED] Total PASS: {total_pass} | Total FAIL: {total_fail} | Total Time: {duration:.2f}s"
        )

    def _append_log(self, text: str) -> None:
        self.log_viewer.append(text)

    def shutdown_threads(self) -> None:
        """Safely terminates all active batch worker threads during application shutdown."""
        if hasattr(self, "coordinator"):
            self.coordinator.stop_all_workers()
