"""
Main application entry point for B-Link DAPLink Production & Diagnostic Suite.
Assembles all feature modules into an industrial 4-pane desktop interface
modeled after STM32CubeProgrammer, incorporating a vertical navigation sidebar,
persistent right-hand diagnostic panel, collapsible bottom log console,
and a real-time hardware status bar.
"""

import sys
from typing import Optional
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QStackedWidget,
    QListWidget,
    QListWidgetItem,
    QDockWidget,
    QPlainTextEdit,
)

# Import feature widgets cleanly from modular architecture (RDP module removed as it is in Option Bytes)
from src.features.memory_viewer.widget import MemoryViewerWidget
from src.features.production_programmer.widget import ProductionProgrammerWidget
from src.features.option_bytes.widget import OptionBytesWidget
from src.features.serial_monitor.widget import SerialMonitorWidget
from src.features.target_diagnostic.widget import TargetDiagnosticWidget

# Import common infrastructure
from src.common import get_logger, GlobalStatusBar

logger = get_logger("MainApplication")


class SidebarNavWidget(QListWidget):
    """
    Industrial vertical navigation sidebar for switching between primary
    workspace modules in the central QStackedWidget.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedWidth(210)
        self.setIconSize(QSize(24, 24))
        self.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet(
            """
            QListWidget {
                background-color: #1E1E1E;
                border: none;
                border-right: 1px solid #333333;
                outline: 0;
                padding-top: 10px;
            }
            QListWidget::item {
                color: #CCCCCC;
                padding: 14px 16px;
                margin: 4px 8px;
                border-radius: 6px;
            }
            QListWidget::item:hover {
                background-color: #2D2D30;
                color: #FFFFFF;
            }
            QListWidget::item:selected {
                background-color: #007ACC;
                color: #FFFFFF;
                font-weight: bold;
            }
            """
        )

    def add_nav_item(self, text: str, tooltip: str = "") -> None:
        """Appends a styled navigation item to the sidebar."""
        item = QListWidgetItem(text)
        item.setToolTip(tooltip)
        self.addItem(item)


class MainWindow(QMainWindow):
    """
    Industrial 4-pane main window hosting isolated feature modules inside an
    STM32CubeProgrammer-style workspace with a persistent right-hand diagnostic
    dock and a real-time DAPLink status bar.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(
            "B-Link DAPLink Production & Diagnostic Suite v1.0"
        )
        self.resize(1280, 800)
        self.setMinimumSize(1024, 640)

        # Instantiate isolated feature modules (No redundant RDP widget)
        self.memory_widget = MemoryViewerWidget()
        self.programmer_widget = ProductionProgrammerWidget()
        self.ob_widget = OptionBytesWidget()
        self.serial_widget = SerialMonitorWidget()
        self.diagnostic_widget = TargetDiagnosticWidget()

        # Build application layout
        self._init_central_workspace()
        self._init_right_diagnostic_dock()
        self._init_bottom_log_dock()

        # Mount global real-time DAPLink status bar
        self.status_bar = GlobalStatusBar(self)
        self.setStatusBar(self.status_bar)

        logger.info("Industrial 4-pane workspace initialized successfully.")

    def _init_central_workspace(self) -> None:
        """Constructs the left navigation sidebar and central stacked workspace."""
        central_container = QWidget()
        layout = QHBoxLayout(central_container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. Sidebar Navigation (Clean 4 Primary Features)
        self.sidebar = SidebarNavWidget()
        self.sidebar.add_nav_item(
            "💾  Device Memory", "Inspect & Edit Flash/RAM"
        )
        self.sidebar.add_nav_item(
            "⚡  Programmer", "Production Flash Programming & Provisioning"
        )
        self.sidebar.add_nav_item(
            "🔒  Option Bytes (OB)", "RDP Levels, Watchdog, BOR & User OB"
        )
        self.sidebar.add_nav_item(
            "📡  Serial Monitor", "Real-time CDC UART Console"
        )

        # 2. Central Workspace Stack (Indices 0 to 3)
        self.workspace_stack = QStackedWidget()
        self.workspace_stack.addWidget(self.memory_widget)      # Index 0
        self.workspace_stack.addWidget(self.programmer_widget)  # Index 1
        self.workspace_stack.addWidget(self.ob_widget)          # Index 2
        self.workspace_stack.addWidget(self.serial_widget)      # Index 3

        # Connect sidebar selection to stacked widget view
        self.sidebar.currentRowChanged.connect(
            self.workspace_stack.setCurrentIndex
        )
        self.sidebar.setCurrentRow(0)  # Default view: Device Memory

        layout.addWidget(self.sidebar)
        layout.addWidget(self.workspace_stack, stretch=1)
        self.setCentralWidget(central_container)

    def _init_right_diagnostic_dock(self) -> None:
        """Mounts the Target Diagnostic module inside a persistent right-hand dock."""
        self.right_dock = QDockWidget(
            "Target Configuration & Diagnostic", self
        )
        self.right_dock.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self.right_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.right_dock.setWidget(self.diagnostic_widget)
        self.right_dock.setMinimumWidth(340)
        self.addDockWidget(
            Qt.DockWidgetArea.RightDockWidgetArea, self.right_dock
        )
        # Explicitly show the right diagnostic panel so it is never hidden
        self.right_dock.show()

    def _init_bottom_log_dock(self) -> None:
        """Mounts a collapsible shared log console inside a bottom dock."""
        self.log_dock = QDockWidget("Application & Target Log Console", self)
        self.log_dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea)
        self.log_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

        self.log_console = QPlainTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setFont(QFont("Consolas", 9))
        self.log_console.setMaximumHeight(140)
        self.log_console.setStyleSheet(
            """
            QPlainTextEdit {
                background-color: #121212;
                color: #D4D4D4;
                border: 1px solid #333333;
                selection-background-color: #264F78;
            }
            """
        )
        self.log_console.appendPlainText(
            "[INFO] B-Link DAPLink Industrial Suite initialized. Ready for target connection."
        )

        self.log_dock.setWidget(self.log_console)
        self.addDockWidget(
            Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock
        )

    def closeEvent(self, event) -> None:
        """
        Intercept window close event to ensure graceful shutdown of all
        active background QThreads across feature modules and status bar.
        """
        logger.info(
            "Application shutting down. Terminating background threads..."
        )
        try:
            active_modules = [
                getattr(self, "diagnostic_widget", None),
                getattr(self, "programmer_widget", None),
                getattr(self, "memory_widget", None),
                getattr(self, "ob_widget", None),
                getattr(self, "serial_widget", None),
                getattr(self, "status_bar", None),
            ]

            for module in active_modules:
                if module and hasattr(module, "shutdown_threads"):
                    try:
                        module.shutdown_threads()
                    except Exception as mod_exc:
                        logger.warning(
                            f"Warning while shutting down {module.__class__.__name__}: {mod_exc}"
                        )

            logger.info("✔ All background threads closed safely.")
            event.accept()

        except Exception as exc:
            logger.error(f"Critical error during thread shutdown: {str(exc)}")
            event.accept()


def main() -> None:
    """Application bootstrap function."""
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
