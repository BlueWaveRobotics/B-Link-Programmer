"""
Main application entry point for B-Link DAPLink Production & Diagnostic Suite.
Assembles all feature modules into an industrial multi-tab desktop interface
and mounts a real-time hardware status bar.
"""

import sys
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTabWidget,
    QWidget,
)

# Import feature widgets from modular architecture
from src.features.target_diagnostic import TargetDiagnosticWidget
from src.features.production_programmer import ProductionProgrammerWidget
from src.features.rdp_protection import RDPProtectionWidget
from src.features.serial_monitor import SerialMonitorWidget

# Import common infrastructure
from src.common import get_logger, GlobalStatusBar

logger = get_logger("MainApplication")


class MainWindow(QMainWindow):
    """
    Industrial main window hosting isolated feature modules inside a
    structured tabbed workspace with a real-time DAPLink status bar.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(
            "B-Link DAPLink Production & Diagnostic Suite v1.0")
        self.resize(880, 680)

        # Initialize core UI tabs
        self.tab_widget = QTabWidget()
        self.setCentralWidget(self.tab_widget)

        # Instantiate feature widgets
        self.diagnostic_widget = TargetDiagnosticWidget()
        self.programmer_widget = ProductionProgrammerWidget()
        self.rdp_widget = RDPProtectionWidget()
        self.serial_widget = SerialMonitorWidget()

        # Mount widgets into application tabs
        self.tab_widget.addTab(self.diagnostic_widget, "🔍 Target Diagnostic")
        self.tab_widget.addTab(self.programmer_widget,
                               "⚡ Production Programmer")
        self.tab_widget.addTab(self.rdp_widget, "🔒 RDP Protection")
        self.tab_widget.addTab(self.serial_widget, "📡 Serial CDC Monitor")

        # Instantiate and attach global real-time DAPLink status bar
        self.status_bar = GlobalStatusBar(self)
        self.setStatusBar(self.status_bar)

        logger.info("Main window initialized and all feature modules mounted.")

    def closeEvent(self, event) -> None:
        """
        Intercept window close event to ensure graceful shutdown of all
        active background QThreads across feature modules and status bar.
        """
        logger.info(
            "Application shutting down. Terminating background threads...")
        try:
            # Terminate feature threads
            self.diagnostic_widget.shutdown_threads()
            self.programmer_widget.shutdown_threads()
            self.rdp_widget.shutdown_threads()
            self.serial_widget.shutdown_threads()

            # Terminate status bar monitoring thread
            self.status_bar.shutdown_threads()

            logger.info("✔ All background threads closed safely.")
            event.accept()
        except Exception as exc:
            logger.error(f"Error during thread shutdown: {str(exc)}")
            event.accept()


def main() -> None:
    """Application bootstrap function."""
    # Enable High-DPI scaling for modern displays
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # Consistent industrial look across OS platforms

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
