"""
UI Widget for Pre-Flash and Post-Flash Automation Script Hooks.
Provides controls for script selection, argument mapping, timeout configuration,
and live test execution with stdout/stderr console logging.
"""

import os
from typing import Dict, Any
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QCheckBox,
    QSpinBox,
    QFileDialog,
    QTextEdit,
    QSplitter,
    QMessageBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QTextCursor

from src.common import get_logger
from src.features.script_hooks.hook_service import HookService, HookExecutionResult

logger = get_logger("ScriptHooksWidget")


class ScriptHooksWidget(QWidget):
    """
    Industrial UI for configuring and testing pre-flash and post-flash script hooks.
    """

    # Signal emitted when hook settings change (useful for Profile auto-saving)
    config_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # Title / Description Header
        header_label = QLabel(
            "<b>Automation Script Hooks</b> — Execute external scripts (.py, .sh, .bat) "
            "before or after the programming cycle."
        )
        header_label.setWordWrap(True)
        main_layout.addWidget(header_label)

        # Splitter to separate configuration panels from the test console
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Top Container for Pre and Post GroupBoxes
        config_container = QWidget()
        config_layout = QVBoxLayout(config_container)
        config_layout.setContentsMargins(0, 0, 0, 0)
        config_layout.setSpacing(10)

        # 1. Pre-Flash Hook Group
        self.pre_group, self.pre_controls = self._create_hook_group(
            "Pre-Flash Hook (e.g., Power Relay Control, UID Verification)"
        )
        config_layout.addWidget(self.pre_group)

        # 2. Post-Flash Hook Group
        self.post_group, self.post_controls = self._create_hook_group(
            "Post-Flash Hook (e.g., Serial Calibration, Database Logging)"
        )
        config_layout.addWidget(self.post_group)

        splitter.addWidget(config_container)

        # 3. Execution Console / Log Area
        console_group = QGroupBox("Hook Test Execution Log")
        console_layout = QVBoxLayout(console_group)

        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setStyleSheet(
            "background-color: #1e1e1e; color: #d4d4d4; font-family: 'Consolas', 'Courier New', monospace; font-size: 11pt;"
        )
        console_layout.addWidget(self.log_console)

        clear_btn_layout = QHBoxLayout()
        clear_btn_layout.addStretch()
        self.clear_console_btn = QPushButton("Clear Console")
        self.clear_console_btn.clicked.connect(self.log_console.clear)
        clear_btn_layout.addWidget(self.clear_console_btn)
        console_layout.addLayout(clear_btn_layout)

        splitter.addWidget(console_group)
        splitter.setSizes([320, 240])

        main_layout.addWidget(splitter)

    def _create_hook_group(self, title: str):
        """Helper to create standardized UI controls for a script hook."""
        group = QGroupBox(title)
        layout = QVBoxLayout(group)

        # Row 1: Enable Checkbox & Script Path Selector
        row1 = QHBoxLayout()
        chk_enable = QCheckBox("Enable Hook")
        chk_enable.setChecked(False)

        path_input = QLineEdit()
        path_input.setPlaceholderText("Select script file (.py, .bat, .sh)...")
        path_input.setEnabled(False)

        browse_btn = QPushButton("Browse...")
        browse_btn.setEnabled(False)

        row1.addWidget(chk_enable)
        row1.addWidget(path_input, 1)
        row1.addWidget(browse_btn)
        layout.addLayout(row1)

        # Row 2: Arguments & Timeout Configuration
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Arguments:"))
        args_input = QLineEdit()
        args_input.setPlaceholderText("e.g., --port COM3 --verbose")
        args_input.setEnabled(False)

        row2.addWidget(args_input, 1)

        row2.addWidget(QLabel("Timeout (s):"))
        timeout_spin = QSpinBox()
        timeout_spin.setRange(1, 300)
        timeout_spin.setValue(15)
        timeout_spin.setEnabled(False)
        row2.addWidget(timeout_spin)

        test_btn = QPushButton("▶ Test Run")
        test_btn.setEnabled(False)
        row2.addWidget(test_btn)
        layout.addLayout(row2)

        # UI State Binding
        chk_enable.toggled.connect(path_input.setEnabled)
        chk_enable.toggled.connect(browse_btn.setEnabled)
        chk_enable.toggled.connect(args_input.setEnabled)
        chk_enable.toggled.connect(timeout_spin.setEnabled)
        chk_enable.toggled.connect(test_btn.setEnabled)
        chk_enable.toggled.connect(lambda _: self.config_changed.emit())

        # Connect Browse Action
        browse_btn.clicked.connect(lambda: self._browse_script(path_input))

        # Connect Test Run Action
        test_btn.clicked.connect(
            lambda: self._execute_test_run(
                path_input.text(), args_input.text(), timeout_spin.value())
        )

        controls = {
            "checkbox": chk_enable,
            "path": path_input,
            "args": args_input,
            "timeout": timeout_spin,
        }
        return group, controls

    def _browse_script(self, line_edit: QLineEdit) -> None:
        """Opens file dialog to pick an automation script."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Automation Script",
            "",
            "Script Files (*.py *.bat *.sh *.exe);;All Files (*.*)",
        )
        if file_path:
            line_edit.setText(os.path.normpath(file_path))
            self.config_changed.emit()

    def _execute_test_run(self, script_path: str, arguments: str, timeout: int) -> None:
        """Executes the selected hook immediately and logs output to console."""
        if not script_path:
            QMessageBox.warning(
                self, "Warning", "Please select a script file first.")
            return

        arg_list = arguments.split() if arguments else None
        self._append_log(f"--- [TEST RUN START]: {script_path} ---", "#4fc1ff")

        result: HookExecutionResult = HookService.execute_hook(
            script_path=script_path,
            arguments=arg_list,
            timeout_seconds=timeout,
        )

        if result.stdout_text:
            self._append_log("[STDOUT]:", "#dcdcaa")
            self._append_log(result.stdout_text, "#cccccc")

        if result.stderr_text:
            self._append_log("[STDERR]:", "#f48771")
            self._append_log(result.stderr_text, "#f48771")

        if result.success:
            self._append_log(
                f"✔ [TEST PASS] Script finished with exit code {result.exit_code} ({result.execution_time:.2f}s)\n",
                "#4ec9b0",
            )
        else:
            self._append_log(
                f"✖ [TEST FAIL] Script terminated with code {result.exit_code} ({result.execution_time:.2f}s)\n",
                "#f14c4c",
            )

    def _append_log(self, text: str, color_hex: str = "#d4d4d4") -> None:
        """Appends formatted and colored HTML text to the console log."""
        html = f"<span style='color:{color_hex};'>{text.replace(chr(10), '<br>')}</span>"
        self.log_console.append(html)
        self.log_console.moveCursor(QTextCursor.MoveOperation.End)

    def get_hooks_configuration(self) -> Dict[str, Dict[str, Any]]:
        """
        Returns a dictionary representation of the current hook configuration
        to be used by the production programmer engine.
        """
        return {
            "pre_flash": {
                "enabled": self.pre_controls["checkbox"].isChecked(),
                "path": self.pre_controls["path"].text().strip(),
                "arguments": self.pre_controls["args"].text().split(),
                "timeout": self.pre_controls["timeout"].value(),
            },
            "post_flash": {
                "enabled": self.post_controls["checkbox"].isChecked(),
                "path": self.post_controls["path"].text().strip(),
                "arguments": self.post_controls["args"].text().split(),
                "timeout": self.post_controls["timeout"].value(),
            },
        }

    def set_hooks_configuration(self, config: Dict[str, Dict[str, Any]]) -> None:
        """
        Populates UI widgets from a saved configuration dictionary.
        """
        pre_cfg = config.get("pre_flash", {})
        self.pre_controls["checkbox"].setChecked(pre_cfg.get("enabled", False))
        self.pre_controls["path"].setText(pre_cfg.get("path", ""))
        self.pre_controls["args"].setText(
            " ".join(pre_cfg.get("arguments", [])))
        self.pre_controls["timeout"].setValue(pre_cfg.get("timeout", 15))

        post_cfg = config.get("post_flash", {})
        self.post_controls["checkbox"].setChecked(
            post_cfg.get("enabled", False))
        self.post_controls["path"].setText(post_cfg.get("path", ""))
        self.post_controls["args"].setText(
            " ".join(post_cfg.get("arguments", [])))
        self.post_controls["timeout"].setValue(post_cfg.get("timeout", 15))
