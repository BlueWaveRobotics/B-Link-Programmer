import sys
import os
import logging
from typing import Optional
from PySide6.QtCore import Qt, QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog, QProgressBar,
    QTextEdit, QGroupBox, QMessageBox
)

from pyocd.core.helpers import ConnectHelper
from pyocd.flash.file_programmer import FileProgrammer

# Configure Python logging to emit messages to custom GUI handler
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DAPLinkGUI")


class FlashWorker(QObject):
    """
    Background worker for executing pyOCD flash programming and diagnostics
    in a dedicated QThread to prevent GUI freezing.
    """
    log_signal = Signal(str)
    progress_signal = Signal(int)
    finished_signal = Signal(bool, str)

    def __init__(
        self,
        file_path: str,
        target_type: str = "stm32f103c8",
        clock_freq: int = 100000,
        connect_mode: str = "under-reset"
    ):
        super().__init__()
        self.file_path = file_path
        self.target_type = target_type
        self.clock_freq = clock_freq
        self.connect_mode = connect_mode
        self._is_running = True

    def _progress_callback(self, progress: float) -> None:
        """Callback invoked by pyOCD FileProgrammer to report progress (0.0 to 1.0)."""
        if self._is_running:
            percent = int(progress * 100)
            self.progress_signal.emit(percent)

    @Slot()
    def run_production_flash(self) -> None:
        """
        Execute One-Click Production Sequence:
        Connect -> Erase -> Program -> Verify -> Reset & Run.
        """
        session = None
        try:
            self.log_signal.emit(
                f"[INFO] Starting Production Mode for file: {os.path.basename(self.file_path)}")
            self.log_signal.emit(
                f"[INFO] Connecting to target '{self.target_type}' @ {self.clock_freq//1000} kHz...")

            options = {
                'connect_mode': self.connect_mode,
                'frequency': self.clock_freq,
                'target_override': self.target_type,
                'reset_type': 'hw' if self.connect_mode == 'under-reset' else 'sw',
                'resume_on_disconnect': False
            }

            # Attempt session open with automatic target fallback
            try:
                session = ConnectHelper.session_with_chosen_probe(
                    options=options)
                session.open()
            except Exception as e:
                if "not recognized" in str(e).lower() and self.target_type != "cortex_m":
                    self.log_signal.emit(
                        "[WARNING] Target pack not found. Falling back to 'cortex_m'...")
                    options['target_override'] = "cortex_m"
                    session = ConnectHelper.session_with_chosen_probe(
                        options=options)
                    session.open()
                else:
                    raise e

            self.log_signal.emit(
                "[INFO] SWD Connection established successfully.")

            # Read DPIDR as a sanity check
            dpidr = session.probe.read_dp(0x0)
            self.log_signal.emit(f"[INFO] Read DP IDCODE: 0x{dpidr:08X}")

            # Initialize FileProgrammer with live progress bar callback
            self.log_signal.emit(
                "[INFO] Initializing Flash Erase, Program, and Verify sequence...")
            self.progress_signal.emit(0)

            programmer = FileProgrammer(
                session,
                progress=self._progress_callback,
                chip_erase="sector"
            )

            # Perform programming (.hex or .bin)
            programmer.program(self.file_path)

            self.progress_signal.emit(100)
            self.log_signal.emit(
                "[INFO] ✔ Flash Program & Verify completed successfully!")

            # Reset and Run the target MCU
            self.log_signal.emit(
                "[INFO] Resetting target core to run application...")
            session.target.reset_and_halt()
            session.target.resume()
            self.log_signal.emit("[INFO] Target MCU is now running.")

            self.finished_signal.emit(
                True, "Production flash sequence completed successfully.")

        except Exception as e:
            error_msg = f"Flash operation failed: {str(e)}"
            self.log_signal.emit(f"[ERROR] {error_msg}")
            self.finished_signal.emit(False, error_msg)

        finally:
            if session:
                try:
                    session.close()
                    self.log_signal.emit("[INFO] SWD session closed.")
                except Exception:
                    pass


class MainWindow(QMainWindow):
    """
    Main GUI application window for DAPLink Programmer Management & Diagnostics.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("DAPLink Dedicated Production Programmer - v1.0")
        self.resize(750, 550)
        self.worker_thread: Optional[QThread] = None
        self.worker: Optional[FlashWorker] = None

        self._init_ui()

    def _init_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # -------------------------------------------------------------
        # 1. Target Configuration & Probe Status Group
        # -------------------------------------------------------------
        config_group = QGroupBox("Hardware & Target Configuration")
        config_layout = QHBoxLayout()

        self.lbl_target = QLabel("Target: STM32F103C8")
        self.lbl_clock = QLabel("SWD Clock: 100 kHz")
        self.lbl_mode = QLabel("Mode: Under-Reset")

        config_layout.addWidget(self.lbl_target)
        config_layout.addWidget(self.lbl_clock)
        config_layout.addWidget(self.lbl_mode)
        config_layout.addStretch()
        config_group.setLayout(config_layout)
        main_layout.addWidget(config_group)

        # -------------------------------------------------------------
        # 2. Firmware File Selection Group
        # -------------------------------------------------------------
        file_group = QGroupBox("Firmware Binary (.hex / .bin)")
        file_layout = QHBoxLayout()

        self.txt_filepath = QLineEdit()
        self.txt_filepath.setPlaceholderText(
            "Select firmware binary file (.hex or .bin)...")
        self.txt_filepath.setReadOnly(True)

        self.btn_browse = QPushButton("Browse File...")
        self.btn_browse.clicked.connect(self._select_file)

        file_layout.addWidget(self.txt_filepath)
        file_layout.addWidget(self.btn_browse)
        file_group.setLayout(file_layout)
        main_layout.addWidget(file_group)

        # -------------------------------------------------------------
        # 3. Action Controls & One-Click Production Button
        # -------------------------------------------------------------
        action_layout = QHBoxLayout()

        self.btn_production_flash = QPushButton("ONE-CLICK PRODUCTION FLASH")
        self.btn_production_flash.setMinimumHeight(45)
        self.btn_production_flash.setStyleSheet(
            "background-color: #2E8B57; color: white; font-weight: bold; font-size: 13px;"
        )
        self.btn_production_flash.clicked.connect(self._start_production_flash)

        action_layout.addWidget(self.btn_production_flash)
        main_layout.addLayout(action_layout)

        # -------------------------------------------------------------
        # 4. Real-Time Progress Bar
        # -------------------------------------------------------------
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        main_layout.addWidget(self.progress_bar)

        # -------------------------------------------------------------
        # 5. Live Console & Diagnostic Log Viewer
        # -------------------------------------------------------------
        log_group = QGroupBox("Live Debug & Operation Logs")
        log_layout = QVBoxLayout()

        self.log_viewer = QTextEdit()
        self.log_viewer.setReadOnly(True)
        self.log_viewer.setStyleSheet(
            "background-color: #1E1E1E; color: #00FF66; font-family: Consolas, monospace; font-size: 11px;"
        )
        log_layout.addWidget(self.log_viewer)

        self.btn_clear_log = QPushButton("Clear Console")
        self.btn_clear_log.clicked.connect(self.log_viewer.clear)
        log_layout.addWidget(self.btn_clear_log,
                             alignment=Qt.AlignmentFlag.AlignRight)

        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)

        self._append_log(
            "[SYSTEM] DAPLink Production GUI Initialized. Ready for firmware deployment.")

    def _select_file(self) -> None:
        """Open native file dialog to select .hex or .bin firmware file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Firmware File",
            "",
            "Firmware Files (*.hex *.bin);;All Files (*)"
        )
        if file_path:
            self.txt_filepath.setText(file_path)
            self._append_log(f"[INFO] Selected firmware binary: {file_path}")

    def _append_log(self, message: str) -> None:
        """Append messages to the live console log viewer."""
        self.log_viewer.append(message)
        # Scroll to the bottom automatically
        self.log_viewer.verticalScrollBar().setValue(
            self.log_viewer.verticalScrollBar().maximum()
        )

    def _set_ui_busy(self, is_busy: bool) -> None:
        """Enable or disable interactive GUI controls during thread execution."""
        self.btn_production_flash.setEnabled(not is_busy)
        self.btn_browse.setEnabled(not is_busy)
        if is_busy:
            self.btn_production_flash.setStyleSheet(
                "background-color: #7F8C8D; color: white; font-weight: bold; font-size: 13px;"
            )
        else:
            self.btn_production_flash.setStyleSheet(
                "background-color: #2E8B57; color: white; font-weight: bold; font-size: 13px;"
            )

    def _start_production_flash(self) -> None:
        """Launch pyOCD flash operation in a separate QThread."""
        file_path = self.txt_filepath.text().strip()
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(
                self, "Invalid File", "Please select a valid .hex or .bin firmware file first.")
            return

        self._set_ui_busy(True)
        self.progress_bar.setValue(0)
        self._append_log("-" * 65)
        self._append_log(
            "[SYSTEM] Launching SWD/pyOCD background worker thread...")

        # Create thread and worker instances
        self.worker_thread = QThread()
        self.worker = FlashWorker(
            file_path=file_path,
            target_type="stm32f103c8",
            clock_freq=100000,
            connect_mode="under-reset"
        )
        self.worker.moveToThread(self.worker_thread)

        # Connect GUI signals and slots
        self.worker_thread.started.connect(self.worker.run_production_flash)
        self.worker.log_signal.connect(self._append_log)
        self.worker.progress_signal.connect(self.progress_bar.setValue)
        self.worker.finished_signal.connect(self._on_flash_finished)

        # Auto-cleanup thread on finish
        self.worker.finished_signal.connect(self.worker_thread.quit)
        self.worker.finished_signal.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)

        self.worker_thread.start()

    @Slot(bool, str)
    def _on_flash_finished(self, success: bool, message: str) -> None:
        """Handle background worker completion."""
        self._set_ui_busy(False)
        self._append_log("-" * 65)
        if success:
            QMessageBox.information(
                self, "Success", "Firmware successfully flashed and target is running!")
        else:
            QMessageBox.critical(self, "Flash Failure",
                                 f"Operation failed:\n{message}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
