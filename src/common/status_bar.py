"""
Global status bar widget and background probe monitoring worker.
Provides asynchronous real-time detection of DAPLink/CMSIS-DAP hardware probes
without blocking the main application UI thread.
"""

from typing import Optional, Any, List
from PySide6.QtCore import Qt, QThread, Signal, Slot, QTimer
from PySide6.QtWidgets import (
    QStatusBar,
    QLabel,
    QWidget,
    QHBoxLayout,
    QFrame,
)
from pyocd.core.helpers import ConnectHelper
from pyocd.probe.debug_probe import DebugProbe

from src.common.logger import get_logger

logger = get_logger("GlobalStatusBar")


class ProbeMonitorWorker(QThread):
    """
    Dedicated background worker thread that polls connected pyOCD debug probes
    at a fixed interval and emits status updates to the UI.
    """

    # Signals: (is_connected: bool, probe_name: str, probe_uid: str)
    status_updated = Signal(bool, str, str)

    def __init__(self, poll_interval_ms: int = 2000, parent: Optional[Any] = None):
        super().__init__(parent)
        self.poll_interval_ms = poll_interval_ms
        self._is_running = True
        self._last_state: Optional[bool] = None
        self._last_uid: Optional[str] = None

    def run(self) -> None:
        """
        Main worker loop executing hardware probe polling without freezing UI.
        """
        logger.info("ProbeMonitorWorker thread started.")
        while self._is_running:
            try:
                # Discover connected debug probes via pyOCD
                probes: List[DebugProbe] = ConnectHelper.get_all_connected_probes(
                    blocking=False
                )

                if probes:
                    primary_probe = probes[0]
                    name = primary_probe.product_name or "B-Link"
                    uid = primary_probe.unique_id or "UNKNOWN_ID"

                    # Only emit signal if state or connected probe changed
                    if self._last_state is not True or self._last_uid != uid:
                        self._last_state = True
                        self._last_uid = uid
                        self.status_updated.emit(True, name, uid)
                        logger.info(
                            f"Hardware probe detected: {name} (UID: {uid})")
                else:
                    if self._last_state is not False:
                        self._last_state = False
                        self._last_uid = None
                        self.status_updated.emit(
                            False, "No B-Link Probe Detected", "-")
                        logger.warning("No B-Link hardware probe connected.")

            except Exception as exc:
                logger.debug(
                    f"Probe scanning background check exception: {str(exc)}")
                if self._last_state is not False:
                    self._last_state = False
                    self._last_uid = None
                    self.status_updated.emit(
                        False, f"Scan Error: {str(exc)}", "-")

            # Efficient non-blocking sleep inside the thread loop
            self.msleep(self.poll_interval_ms)

        logger.info("ProbeMonitorWorker thread terminated cleanly.")

    def stop_monitoring(self) -> None:
        """Safely signals the thread loop to terminate."""
        self._is_running = False


class GlobalStatusBar(QStatusBar):
    """
    Industrial status bar widget displaying real-time DAPLink probe connectivity,
    probe model, and unique hardware serial number.
    """

    # ⬅️ Added Signal to notify the rest of the application (like TargetDiagnosticWidget)
    probe_status_changed = Signal(bool, str, str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._monitor_thread: Optional[ProbeMonitorWorker] = None
        self._init_ui()
        self._start_probe_monitor()

    def _init_ui(self) -> None:
        """Configures visual indicators and layout of the status bar."""
        self.setStyleSheet(
            """
            QStatusBar {
                background-color: #1E1E1E;
                color: #CCCCCC;
                border-top: 1px solid #333333;
                font-family: Consolas, monospace;
                font-size: 11px;
            }
            QLabel {
                padding: 0 8px;
            }
            """
        )

        # Container for right-aligned hardware diagnostics
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 10, 0)
        layout.setSpacing(8)

        # 1. LED Dot Indicator
        self.lbl_led = QLabel("●")
        self.lbl_led.setStyleSheet("color: #7F8C8D; font-size: 14px;")
        layout.addWidget(self.lbl_led)

        # 2. Connection State Label
        self.lbl_status = QLabel("SCANNING HARDWARE...")
        self.lbl_status.setStyleSheet("color: #F39C12; font-weight: bold;")
        layout.addWidget(self.lbl_status)

        # Separator line
        sep1 = self._create_separator()
        layout.addWidget(sep1)

        # 3. Probe Name / Model Label
        self.lbl_probe_name = QLabel("Probe: --")
        layout.addWidget(self.lbl_probe_name)

        # Separator line
        sep2 = self._create_separator()
        layout.addWidget(sep2)

        # 4. Probe Unique ID / Serial Label
        self.lbl_probe_id = QLabel("UID: --")
        self.lbl_probe_id.setStyleSheet("color: #85929E;")
        layout.addWidget(self.lbl_probe_id)

        # Add container to the right side of the status bar (permanent widget)
        self.addPermanentWidget(container)

        # Left side general status message
        self.showMessage(
            "System Ready. Monitoring B-Link hardware connection...", 5000)

    def _create_separator(self) -> QFrame:
        """Creates a subtle vertical separator for the status bar."""
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("color: #444444;")
        return line

    def _start_probe_monitor(self) -> None:
        """Launches the asynchronous hardware monitoring worker thread."""
        self._monitor_thread = ProbeMonitorWorker(poll_interval_ms=2000)
        self._monitor_thread.status_updated.connect(
            self._on_probe_status_updated)
        self._monitor_thread.start()

    @Slot(bool, str, str)
    def _on_probe_status_updated(self, connected: bool, name: str, uid: str) -> None:
        """
        Updates visual indicators when hardware probe connectivity changes.
        """
        if connected:
            self.lbl_led.setStyleSheet(
                "color: #2ECC71; font-size: 14px;")  # Bright Green
            self.lbl_status.setText("B-Link CONNECTED")
            self.lbl_status.setStyleSheet("color: #2ECC71; font-weight: bold;")
            self.lbl_probe_name.setText(f"Probe: {name}")
            self.lbl_probe_id.setText(f"UID: {uid}")
            self.showMessage(f"Hardware Connected: {name} ({uid})", 4000)
        else:
            self.lbl_led.setStyleSheet(
                "color: #E74C3C; font-size: 14px;")  # Bright Red
            self.lbl_status.setText("PROBE DISCONNECTED")
            self.lbl_status.setStyleSheet("color: #E74C3C; font-weight: bold;")
            self.lbl_probe_name.setText("Probe: No Hardware")
            self.lbl_probe_id.setText("UID: --")
            self.showMessage("Warning: B-Link probe disconnected.", 4000)

        # ⬅️ Emit the global signal to lock/unlock the right panel
        self.probe_status_changed.emit(connected, name, uid)

    def shutdown_threads(self) -> None:
        """
        Safely stops the background probe monitoring thread on app exit.
        """
        if self._monitor_thread and self._monitor_thread.isRunning():
            logger.info("Stopping GlobalStatusBar probe monitor thread...")
            self._monitor_thread.stop_monitoring()
            self._monitor_thread.quit()
            self._monitor_thread.wait()
            logger.info("✔ GlobalStatusBar monitor thread stopped.")
