"""
UI component for RDP (Readout Protection) Management.
Provides visual indicators for chip security status and control actions for locking/unlocking.
"""

import os
from typing import Optional, Any
from PySide6.QtCore import Qt, QThread, Slot
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QPushButton,
    QLabel,
    QMessageBox,
    QTextEdit,
)

from src.common import BaseWorker, SessionManager, get_logger
from src.features.rdp_protection.option_bytes import OptionBytesService

logger = get_logger("RDPProtectionWidget")


class _RDPWorker(BaseWorker):
    """
    Background worker to handle RDP read and write operations via SWD
    without causing interface freezes.
    """

    def __init__(
        self,
        action: str = "read",
        rdp_level: int = 1,
        clock_freq: int = 1000000,
        connect_mode: str = "attach",
        parent: Optional[Any] = None,
    ):
        super().__init__(parent)
        self.action = action
        self.rdp_level = rdp_level
        self.clock_freq = clock_freq
        self.connect_mode = connect_mode

    @Slot()
    def run_operation(self) -> None:
        session_mgr = SessionManager(
            clock_freq=self.clock_freq,
            connect_mode=self.connect_mode,
        )
        try:
            self.log("[INFO] Establishing SWD session for RDP operation...")
            if not session_mgr.connect():
                self.finished_signal.emit(
                    False, "Failed to connect to target via SWD.")
                return

            ob_service = OptionBytesService(session_mgr.session)

            if self.action == "read":
                status = ob_service.read_rdp_status()
                if status["success"]:
                    msg = f"RDP Status: {status['level']} (Raw: 0x{status['raw_value']:02X})"
                    self.finished_signal.emit(True, msg)
                else:
                    self.finished_signal.emit(False, status["error"])

            elif self.action == "write":
                success = ob_service.set_rdp_level(self.rdp_level)
                if success:
                    self.finished_signal.emit(
                        True, f"Successfully updated RDP to Level {self.rdp_level}.")
                else:
                    self.finished_signal.emit(
                        False, f"Failed to apply RDP Level {self.rdp_level}.")

        except Exception as exc:
            err = str(exc)
            logger.error(f"RDP worker execution error: {err}")
            self.finished_signal.emit(False, f"Operation exception: {err}")
        finally:
            session_mgr.close()


class RDPProtectionWidget(QWidget):
    """
    Industrial UI Widget for monitoring and altering STM32 Readout Protection (RDP).
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._thread: Optional[QThread] = None
        self._worker: Optional[_RDPWorker] = None

        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # -------------------------------------------------------------
        # Security Status Group
        # -------------------------------------------------------------
        status_group = QGroupBox("Flash Security & Readout Protection (RDP)")
        status_layout = QVBoxLayout()

        top_layout = QHBoxLayout()
        self.lbl_rdp_state = QLabel("RDP State: UNKNOWN / NOT SCANNED")
        self.lbl_rdp_state.setStyleSheet("color: #F39C12; font-weight: bold;")

        self.btn_check_rdp = QPushButton("🔍 Check RDP Status")
        self.btn_check_rdp.clicked.connect(
            lambda: self._execute_action("read", 0))

        top_layout.addWidget(self.lbl_rdp_state)
        top_layout.addStretch()
        top_layout.addWidget(self.btn_check_rdp)
        status_layout.addLayout(top_layout)

        # Action Buttons Layout
        btn_layout = QHBoxLayout()

        self.btn_lock = QPushButton("🔒 Set RDP Level 1 (Lock Protection)")
        self.btn_lock.setStyleSheet(
            "QPushButton { color: #C0392B; font-weight: bold; }")
        self.btn_lock.setToolTip(
            "Protects flash memory against external reading and debugging.")
        self.btn_lock.clicked.connect(self._confirm_lock)

        self.btn_unlock = QPushButton(
            "🔓 Set RDP Level 0 (Unlock / Full Erase)")
        self.btn_unlock.setStyleSheet(
            "QPushButton { color: #27AE60; font-weight: bold; }")
        self.btn_unlock.setToolTip(
            "Disables protection (Warning: Triggers mass erase on STM32).")
        self.btn_unlock.clicked.connect(self._confirm_unlock)

        btn_layout.addWidget(self.btn_lock)
        btn_layout.addWidget(self.btn_unlock)
        status_layout.addLayout(btn_layout)

        status_group.setLayout(status_layout)
        main_layout.addWidget(status_group)

        # -------------------------------------------------------------
        # RDP Log Console
        # -------------------------------------------------------------
        log_group = QGroupBox("RDP Operation Logs")
        log_layout = QVBoxLayout()

        self.log_viewer = QTextEdit()
        self.log_viewer.setReadOnly(True)
        self.log_viewer.setMaximumHeight(130)
        self.log_viewer.setStyleSheet(
            "background-color: #1E1E1E; color: #00FF66; font-family: Consolas, monospace; font-size: 11px;"
        )
        log_layout.addWidget(self.log_viewer)

        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)

        self._append_log("[SYSTEM] RDP Protection Module Initialized.")

    # -----------------------------------------------------------------
    # Interaction & Confirmation Logic
    # -----------------------------------------------------------------
    def _confirm_lock(self) -> None:
        reply = QMessageBox.question(
            self,
            "Confirm RDP Level 1 Lock",
            "Are you sure you want to activate Readout Protection Level 1?\n\n"
            "This will secure the microcontroller against unauthorized firmware extraction.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._execute_action("write", 1)

    def _confirm_unlock(self) -> None:
        reply = QMessageBox.warning(
            self,
            "WARNING: Unlock RDP Level 0",
            "Disabling Readout Protection (Level 0) will initiate a MASS CHIP ERASE "
            "on standard STM32 targets, wiping all user code and data!\n\n"
            "Do you wish to proceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._execute_action("write", 0)

    def _execute_action(self, action: str, level: int) -> None:
        self.btn_check_rdp.setEnabled(False)
        self.btn_lock.setEnabled(False)
        self.btn_unlock.setEnabled(False)
        self._append_log(f"-" * 55)
        self._append_log(
            f"[SYSTEM] Starting RDP operation ({action.upper()} - Level {level})...")

        self._thread = QThread()
        self._worker = _RDPWorker(action=action, rdp_level=level)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run_operation)
        self._worker.log_signal.connect(self._append_log)
        self._worker.finished_signal.connect(self._on_operation_finished)

        self._worker.finished_signal.connect(self._thread.quit)
        self._worker.finished_signal.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

    @Slot(bool, str)
    def _on_operation_finished(self, success: bool, message: str) -> None:
        self.btn_check_rdp.setEnabled(True)
        self.btn_lock.setEnabled(True)
        self.btn_unlock.setEnabled(True)

        if success:
            self.lbl_rdp_state.setText(f"Status: {message}")
            self.lbl_rdp_state.setStyleSheet(
                "color: #2ECC71; font-weight: bold;")
            self._append_log(f"[SUCCESS] {message}")
        else:
            self.lbl_rdp_state.setText("Status: OPERATION FAILED")
            self.lbl_rdp_state.setStyleSheet(
                "color: #E74C3C; font-weight: bold;")
            self._append_log(f"[FAILED] {message}")

    def _append_log(self, message: str) -> None:
        self.log_viewer.append(message)
        self.log_viewer.verticalScrollBar().setValue(
            self.log_viewer.verticalScrollBar().maximum()
        )

    def shutdown_threads(self) -> None:
        """Safely terminate background RDP threads on exit."""
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait()
