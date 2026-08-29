# """
# Main application entry point for B-Link DAPLink Production & Diagnostic Suite.
# Assembles all feature modules into an industrial 4-pane desktop interface
# modeled after STM32CubeProgrammer, incorporating a vertical navigation sidebar,
# persistent right-hand diagnostic panel, collapsible bottom log console,
# and a real-time hardware status bar.
# """

# from src.common.pack_downloader import GlobalDownloadDialog
# from src.common.resources import ICON_MEMORY, ICON_PROGRAMMER, ICON_LOCK, ICON_SERIAL, ICON_BATCH
# import sys
# import os

# if getattr(sys, 'frozen', False):
#     os.environ["PATH"] += os.pathsep + sys._MEIPASS

# from typing import Optional
# from PySide6.QtCore import Qt, QSize
# from PySide6.QtGui import QFont, QPalette, QColor, QIcon
# from src.common import get_logger, GlobalStatusBar
# from src.features.batch_programmer.widget import BatchProgrammerWidget
# from src.features.target_diagnostic.widget import TargetDiagnosticWidget
# from src.features.serial_monitor.widget import SerialMonitorWidget
# from src.features.option_bytes.widget import OptionBytesWidget
# from src.features.production_programmer.widget import ProductionProgrammerWidget
# from src.features.memory_viewer.widget import MemoryViewerWidge
# from PySide6.QtCore import QTimer, QUrl
# from PySide6.QtWidgets import QMessageBox
# from PySide6.QtGui import QDesktopServices
# from src.common.app_updater import AppUpdateWorker
# from typing import Optional
# from PySide6.QtCore import Qt, QSize
# from PySide6.QtWidgets import (
#     QApplication,
#     QMainWindow,
#     QWidget,
#     QVBoxLayout,
#     QHBoxLayout,
#     QStackedWidget,
#     QListWidget,
#     QListWidgetItem,
#     QDockWidget,
#     QPlainTextEdit,
#     QPushButton,
# )
# import textwrap
# import textwrap
# import libusb_package
# libusb_package.find()

# logger = get_logger("MainApplication")

# # ==============================================================================
# # BLUEWAVE SPORT & PROFESSIONAL THEME (QSS)
# # ==============================================================================
# BLUEWAVE_SPORTY_QSS = """
# /* 1. Global Application Baseline */
# QWidget {
#     background-color: #070B19; /* Deep space navy blue */
#     color: #F8FAFC;
#     font-family: "Segoe UI", "Tahoma", sans-serif;
#     font-size: 13px;
#     selection-background-color: #00E5FF;
#     selection-color: #000000;
# }

# /* 2. Main Window & Docking Splitters */
# QMainWindow {
#     background-color: #070B19;
# }

# QMainWindow::separator {
#     background-color: #121A2F;
#     width: 2px;
#     height: 2px;
# }

# QMainWindow::separator:hover {
#     background-color: #00E5FF; /* Sporty Cyan hover */
# }

# /* 3. Dock Widgets (Right Diagnostic & Bottom Log Console) */
# QDockWidget {
#     color: #00E5FF;
#     font-weight: 800;
#     text-transform: uppercase;
# }

# QDockWidget::title {
#     background-color: #0C1327;
#     padding: 10px 14px;
#     border-bottom: 2px solid #00B4D8;
#     border-top-left-radius: 8px;
#     border-top-right-radius: 8px;
#     text-align: left;
#     font-size: 14px;
#     letter-spacing: 1px;
# }

# /* 4. Scrollbars (Custom Sleek Sport Scrollbars) */
# QScrollBar:vertical {
#     border: none;
#     background: #070B19;
#     width: 8px;
#     margin: 0px;
# }

# QScrollBar::handle:vertical {
#     background: #1A2642;
#     min-height: 30px;
#     border-radius: 4px;
# }

# QScrollBar::handle:vertical:hover {
#     background: #00B4D8;
# }

# QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
#     height: 0px;
# }

# QScrollBar:horizontal {
#     border: none;
#     background: #070B19;
#     height: 8px;
#     margin: 0px;
# }

# QScrollBar::handle:horizontal {
#     background: #1A2642;
#     min-width: 30px;
#     border-radius: 4px;
# }

# QScrollBar::handle:horizontal:hover {
#     background: #00B4D8;
# }

# QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
#     width: 0px;
# }

# /* 5. Tooltips */
# QToolTip {
#     background-color: #0C1327;
#     color: #00E5FF;
#     border: 1px solid #00B4D8;
#     padding: 6px 10px;
#     border-radius: 6px;
#     font-weight: bold;
# }
# """


# class SidebarNavWidget(QWidget):
#     """
#     Ultra-modern vertical navigation sidebar.
#     Supports expanding/collapsing via Hamburger menu.
#     """

#     def __init__(self, parent: Optional[QWidget] = None):
#         super().__init__(parent)
#         self.is_expanded = False
#         self.setFixedWidth(75)

#         layout = QVBoxLayout(self)
#         layout.setContentsMargins(0, 0, 0, 0)
#         layout.setSpacing(0)

#         self.btn_style_collapsed = """
#             QPushButton {
#                 background-color: #070B19; color: #00E5FF; border: none;
#                 border-bottom: 1px solid #1A2642; border-right: 1px solid #1A2642;
#                 font-weight: 800; font-size: 28px; text-align: center;
#             }
#             QPushButton:hover { background-color: #121D38; }
#         """

#         self.btn_style_expanded = """
#             QPushButton {
#                 background-color: #0C1327; color: #00E5FF; border: none;
#                 border-bottom: 1px solid #1A2642; border-right: 1px solid #1A2642;
#                 font-weight: 900; font-size: 16px; text-align: left; padding-left: 20px; letter-spacing: 2px;
#             }
#             QPushButton:hover { background-color: #121D38; }
#         """

#         self.top_logo_btn = QPushButton("≡")
#         self.top_logo_btn.setFixedHeight(60)
#         self.top_logo_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
#         self.top_logo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
#         self.top_logo_btn.setStyleSheet(self.btn_style_collapsed)
#         self.top_logo_btn.clicked.connect(self.toggle_sidebar)
#         layout.addWidget(self.top_logo_btn)

#         self.list_widget = QListWidget()
#         self.list_widget.setHorizontalScrollBarPolicy(
#             Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
#         self.list_widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)

#         self.list_widget.setIconSize(QSize(26, 26))

#         self.list_widget.setStyleSheet(
#             """
#             QListWidget {
#                 background-color: #070B19;
#                 border: none;
#                 border-right: 1px solid #1A2642;
#                 outline: 0;
#                 padding-top: 15px;
#             }
#             QListWidget::item {
#                 padding: 10px 10px;
#                 margin: 6px 10px;
#                 border-radius: 8px;
#                 border-left: 4px solid transparent;
#                 color: #94A3B8;
#                 font-weight: bold;
#                 font-size: 13px;
#             }
#             QListWidget::item:hover {
#                 background-color: #121D38;
#                 color: #00E5FF;
#             }
#             QListWidget::item:selected {
#                 background-color: rgba(0, 229, 255, 0.08);
#                 border-left: 4px solid #00E5FF;
#                 color: #FFFFFF;
#             }
#             """
#         )
#         layout.addWidget(self.list_widget)

#     @property
#     def currentRowChanged(self):
#         return self.list_widget.currentRowChanged

#     def setCurrentRow(self, row: int) -> None:
#         self.list_widget.setCurrentRow(row)

#     def toggle_sidebar(self):
#         self.is_expanded = not self.is_expanded

#         if self.is_expanded:
#             self.setFixedWidth(230)
#             self.top_logo_btn.setText("≡  MENU")
#             self.top_logo_btn.setStyleSheet(self.btn_style_expanded)

#             for i in range(self.list_widget.count()):
#                 item = self.list_widget.item(i)
#                 icon_path, full_text, tooltip = item.data(
#                     Qt.ItemDataRole.UserRole)
#                 item.setText(f"   {full_text}")
#                 item.setTextAlignment(
#                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
#         else:
#             self.setFixedWidth(75)
#             self.top_logo_btn.setText("≡")
#             self.top_logo_btn.setStyleSheet(self.btn_style_collapsed)

#             for i in range(self.list_widget.count()):
#                 item = self.list_widget.item(i)
#                 item.setText("")
#                 item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

#     def add_nav_item(self, icon_path: str, full_text: str, tooltip: str = "") -> None:
#         item = QListWidgetItem(QIcon(icon_path), "")

#         item.setData(Qt.ItemDataRole.UserRole, (icon_path, full_text, tooltip))
#         item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

#         if tooltip:
#             wrapped_tooltip = "<br>".join(textwrap.wrap(tooltip, width=25))
#             hover_text = (
#                 f"<span style='color: #00E5FF; font-size: 13px; font-weight: bold;'>{full_text}</span><br><br>"
#                 f"<span style='color: #E2E8F0; font-size: 11px;'>{wrapped_tooltip}</span>"
#             )
#         else:
#             hover_text = f"<span style='color: #00E5FF; font-size: 13px; font-weight: bold;'>{full_text}</span>"

#         item.setToolTip(hover_text)
#         self.list_widget.addItem(item)


# class MainWindow(QMainWindow):
#     """
#     Sporty 4-pane main window hosting isolated feature modules inside an
#     STM32CubeProgrammer-style workspace with a persistent right-hand diagnostic
#     dock and a real-time DAPLink status bar.
#     """

#     def __init__(self, parent: Optional[QWidget] = None):
#         super().__init__(parent)
#         self.current_interface = "B-Link (SWD)"
#         self.setWindowTitle(
#             "B-Link Production & Diagnostic Suite v1.0"
#         )
#         self.resize(1366, 820)
#         self.setMinimumSize(1024, 640)

#         # Instantiate isolated feature modules
#         self.memory_widget = MemoryViewerWidget()
#         self.programmer_widget = ProductionProgrammerWidget()
#         self.ob_widget = OptionBytesWidget()
#         self.serial_widget = SerialMonitorWidget()
#         self.diagnostic_widget = TargetDiagnosticWidget()
#         self.diagnostic_widget.setMinimumWidth(380)
#         self.batch_widget = BatchProgrammerWidget()

#         # Build application layout
#         self._init_central_workspace()
#         self._init_right_diagnostic_dock()
#         self._init_bottom_log_dock()

#         self.status_bar = GlobalStatusBar(self)
#         self.setStatusBar(self.status_bar)

#         self.diagnostic_widget.interface_changed.connect(
#             self.on_global_interface_changed
#         )
#         self.status_bar.probe_status_changed.connect(
#             self.diagnostic_widget.on_global_probe_status_changed
#         )

#         self.diagnostic_widget.target_changed.connect(
#             self.memory_viewer_widget.set_mcu_target)

#         logger.info("4-pane workspace initialized successfully.")
#         QTimer.singleShot(2000, self._run_silent_update_check)
#         self.global_pack_downloader = GlobalDownloadDialog(self)

#     def _run_silent_update_check(self):
#         self.updater_thread = AppUpdateWorker(self)
#         self.updater_thread.check_finished.connect(self._on_auto_update_result)
#         self.updater_thread.start()

#     def _on_auto_update_result(self, success: bool, is_newer: bool, version: str, notes: str, url: str, error: str):

#         if success and is_newer:
#             msg_box = QMessageBox(self)
#             msg_box.setWindowTitle("Software Update Available")
#             msg_box.setText(
#                 f"A new version of B-Link software (v{version}) is available!")
#             msg_box.setInformativeText(
#                 f"Release Notes:\n{notes}\n\nWould you like to download the update now?")

#             btn_download = msg_box.addButton(
#                 "📥 Download Update", QMessageBox.ButtonRole.AcceptRole)
#             btn_cancel = msg_box.addButton(
#                 "Remind Me Later", QMessageBox.ButtonRole.RejectRole)

#             msg_box.exec()

#             if msg_box.clickedButton() == btn_download:
#                 QDesktopServices.openUrl(QUrl(url))

#     def on_global_interface_changed(self, new_interface: str) -> None:
#         self.current_interface = new_interface

#         if hasattr(self.memory_widget, "set_interface_type"):
#             self.memory_widget.set_interface_type(new_interface)

#         if hasattr(self.programmer_widget, "set_interface_type"):
#             self.programmer_widget.set_interface_type(new_interface)

#         if hasattr(self.ob_widget, "set_interface_type"):
#             self.ob_widget.set_interface_type(new_interface)

#         logger.info(f"MainWindow updated global interface to: {new_interface}")

#     def _init_central_workspace(self) -> None:
#         central_container = QWidget()
#         layout = QHBoxLayout(central_container)
#         layout.setContentsMargins(0, 0, 0, 0)
#         layout.setSpacing(0)

#         self.sidebar = SidebarNavWidget()

#         self.sidebar.add_nav_item(ICON_MEMORY, "Device Memory")
#         self.sidebar.add_nav_item(ICON_PROGRAMMER, "Programmer")
#         self.sidebar.add_nav_item(ICON_LOCK, "Option Bytes")
#         self.sidebar.add_nav_item(ICON_SERIAL, "Serial Monitor")
#         self.sidebar.add_nav_item(ICON_BATCH, "Batch Flashing")

#         self.workspace_stack = QStackedWidget()
#         self.workspace_stack.addWidget(self.memory_widget)        # Index 0
#         self.workspace_stack.addWidget(self.programmer_widget)    # Index 1
#         self.workspace_stack.addWidget(self.ob_widget)            # Index 2
#         self.workspace_stack.addWidget(self.serial_widget)        # Index 3
#         self.workspace_stack.addWidget(self.batch_widget)         # Index 4

#         self.sidebar.currentRowChanged.connect(
#             self.workspace_stack.setCurrentIndex
#         )
#         self.sidebar.setCurrentRow(0)

#         layout.addWidget(self.sidebar)
#         layout.addWidget(self.workspace_stack, stretch=1)
#         self.setCentralWidget(central_container)

#     def _init_right_diagnostic_dock(self) -> None:
#         self.right_dock = QDockWidget(
#             "Target Diagnostic", self
#         )
#         self.right_dock.setAllowedAreas(
#             Qt.DockWidgetArea.RightDockWidgetArea
#         )
#         self.right_dock.setFeatures(
#             QDockWidget.DockWidgetFeature.NoDockWidgetFeatures
#         )
#         self.right_dock.setWidget(self.diagnostic_widget)
#         self.right_dock.setMinimumWidth(320)
#         self.addDockWidget(
#             Qt.DockWidgetArea.RightDockWidgetArea, self.right_dock
#         )
#         self.right_dock.show()

#     def _init_bottom_log_dock(self) -> None:
#         self.log_dock = QDockWidget("System Log Console", self)
#         self.log_dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea)

#         self.log_dock.setFeatures(
#             QDockWidget.DockWidgetFeature.NoDockWidgetFeatures
#         )

#         self.log_console = QPlainTextEdit()
#         self.log_console.setReadOnly(True)
#         self.log_console.setFont(QFont("Consolas", 10))
#         self.log_console.setMaximumHeight(160)

#         # استایل خفن ترمینالی برای بخش لاگ‌ها
#         self.log_console.setStyleSheet(
#             """
#             QPlainTextEdit {
#                 background-color: #03060E; /* مشکی بسیار عمیق */
#                 color: #00E5FF; /* متن سایان درخشان */
#                 border: 2px solid #0C1327;
#                 border-radius: 6px;
#                 selection-background-color: #0077B6;
#                 padding: 10px;
#             }
#             """
#         )

#         self.log_console.appendPlainText(
#             "[INFO] BlueWave B-Link Suite initialized. Ready for extreme performance."
#         )

#         self.log_dock.setWidget(self.log_console)
#         self.addDockWidget(
#             Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock
#         )

#     def closeEvent(self, event) -> None:
#         logger.info(
#             "Application shutting down. Terminating background threads...")
#         try:
#             active_modules = [
#                 getattr(self, "diagnostic_widget", None),
#                 getattr(self, "programmer_widget", None),
#                 getattr(self, "memory_widget", None),
#                 getattr(self, "ob_widget", None),
#                 getattr(self, "serial_widget", None),
#                 getattr(self, "status_bar", None),
#                 getattr(self, "batch_widget", None),
#                 # getattr(self, "merger_widget", None),
#                 # getattr(self, "script_hooks_widget", None),
#             ]

#             for module in active_modules:
#                 if module and hasattr(module, "shutdown_threads"):
#                     try:
#                         module.shutdown_threads()
#                     except Exception as mod_exc:
#                         logger.warning(
#                             f"Warning while shutting down {module.__class__.__name__}: {mod_exc}"
#                         )

#             logger.info("✔ All background threads closed safely.")
#             event.accept()

#         except Exception as exc:
#             logger.error(f"Critical error during thread shutdown: {str(exc)}")
#             event.accept()


# def main() -> None:
#     QApplication.setHighDpiScaleFactorRoundingPolicy(
#         Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
#     )

#     app = QApplication(sys.argv)

#     app.setStyle("Fusion")

#     dark_palette = QPalette()
#     dark_palette.setColor(QPalette.ColorRole.Window, QColor("#070B19"))
#     dark_palette.setColor(QPalette.ColorRole.WindowText, QColor("#F8FAFC"))
#     dark_palette.setColor(QPalette.ColorRole.Base, QColor("#03060E"))
#     dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#0C1327"))
#     dark_palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#0C1327"))
#     dark_palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#00E5FF"))
#     dark_palette.setColor(QPalette.ColorRole.Text, QColor("#F8FAFC"))
#     dark_palette.setColor(QPalette.ColorRole.Button, QColor("#121D38"))
#     dark_palette.setColor(QPalette.ColorRole.ButtonText, QColor("#F8FAFC"))
#     dark_palette.setColor(QPalette.ColorRole.BrightText, QColor("#E63946"))
#     dark_palette.setColor(QPalette.ColorRole.Highlight, QColor("#00B4D8"))
#     dark_palette.setColor(
#         QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))

#     app.setPalette(dark_palette)
#     app.setStyleSheet(BLUEWAVE_SPORTY_QSS)

#     window = MainWindow()
#     window.show()

#     sys.exit(app.exec())


# if __name__ == "__main__":
#     main()
"""
Main application entry point for B-Link DAPLink Production & Diagnostic Suite.
Assembles all feature modules into an industrial 4-pane desktop interface
modeled after STM32CubeProgrammer, incorporating a vertical navigation sidebar,
persistent right-hand diagnostic panel, collapsible bottom log console,
and a real-time hardware status bar.
"""

from src.common.app_updater import AppUpdateWorker
from src.features.memory_viewer.widget import MemoryViewerWidget  # ⬅️ حرف t اضافه شد
from src.features.production_programmer.widget import ProductionProgrammerWidget
from src.features.option_bytes.widget import OptionBytesWidget
from src.features.serial_monitor.widget import SerialMonitorWidget
from src.features.target_diagnostic.widget import TargetDiagnosticWidget
from src.features.batch_programmer.widget import BatchProgrammerWidget
from src.common import get_logger, GlobalStatusBar
from src.common.resources import ICON_MEMORY, ICON_PROGRAMMER, ICON_LOCK, ICON_SERIAL, ICON_BATCH
from src.common.pack_downloader import GlobalDownloadDialog
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
    QPushButton,
    QMessageBox,
)
from PySide6.QtGui import QFont, QPalette, QColor, QIcon, QDesktopServices
from PySide6.QtCore import Qt, QSize, QTimer, QUrl
from typing import Optional
import sys
import os
import textwrap
import libusb_package

if getattr(sys, 'frozen', False):
    os.environ["PATH"] += os.pathsep + sys._MEIPASS

libusb_package.find()


logger = get_logger("MainApplication")

# ==============================================================================
# BLUEWAVE SPORT & PROFESSIONAL THEME (QSS)
# ==============================================================================
BLUEWAVE_SPORTY_QSS = """
/* 1. Global Application Baseline */
QWidget {
    background-color: #070B19; /* Deep space navy blue */
    color: #F8FAFC;
    font-family: "Segoe UI", "Tahoma", sans-serif;
    font-size: 13px;
    selection-background-color: #00E5FF;
    selection-color: #000000;
}

/* 2. Main Window & Docking Splitters */
QMainWindow {
    background-color: #070B19;
}

QMainWindow::separator {
    background-color: #121A2F;
    width: 2px;
    height: 2px;
}

QMainWindow::separator:hover {
    background-color: #00E5FF; /* Sporty Cyan hover */
}

/* 3. Dock Widgets (Right Diagnostic & Bottom Log Console) */
QDockWidget {
    color: #00E5FF;
    font-weight: 800;
    text-transform: uppercase;
}

QDockWidget::title {
    background-color: #0C1327;
    padding: 10px 14px;
    border-bottom: 2px solid #00B4D8;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    text-align: left;
    font-size: 14px;
    letter-spacing: 1px;
}

/* 4. Scrollbars (Custom Sleek Sport Scrollbars) */
QScrollBar:vertical {
    border: none;
    background: #070B19;
    width: 8px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #1A2642;
    min-height: 30px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #00B4D8;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    border: none;
    background: #070B19;
    height: 8px;
    margin: 0px;
}

QScrollBar::handle:horizontal {
    background: #1A2642;
    min-width: 30px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal:hover {
    background: #00B4D8;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* 5. Tooltips */
QToolTip {
    background-color: #0C1327;
    color: #00E5FF;
    border: 1px solid #00B4D8;
    padding: 6px 10px;
    border-radius: 6px;
    font-weight: bold;
}
"""


class SidebarNavWidget(QWidget):
    """
    Ultra-modern vertical navigation sidebar.
    Supports expanding/collapsing via Hamburger menu.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.is_expanded = False
        self.setFixedWidth(75)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.btn_style_collapsed = """
            QPushButton {
                background-color: #070B19; color: #00E5FF; border: none;
                border-bottom: 1px solid #1A2642; border-right: 1px solid #1A2642;
                font-weight: 800; font-size: 28px; text-align: center;
            }
            QPushButton:hover { background-color: #121D38; }
        """

        self.btn_style_expanded = """
            QPushButton {
                background-color: #0C1327; color: #00E5FF; border: none;
                border-bottom: 1px solid #1A2642; border-right: 1px solid #1A2642;
                font-weight: 900; font-size: 16px; text-align: left; padding-left: 20px; letter-spacing: 2px;
            }
            QPushButton:hover { background-color: #121D38; }
        """

        self.top_logo_btn = QPushButton("≡")
        self.top_logo_btn.setFixedHeight(60)
        self.top_logo_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.top_logo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.top_logo_btn.setStyleSheet(self.btn_style_collapsed)
        self.top_logo_btn.clicked.connect(self.toggle_sidebar)
        layout.addWidget(self.top_logo_btn)

        self.list_widget = QListWidget()
        self.list_widget.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.list_widget.setIconSize(QSize(26, 26))

        self.list_widget.setStyleSheet(
            """
            QListWidget {
                background-color: #070B19;
                border: none;
                border-right: 1px solid #1A2642;
                outline: 0;
                padding-top: 15px;
            }
            QListWidget::item {
                padding: 10px 10px; 
                margin: 6px 10px;
                border-radius: 8px;
                border-left: 4px solid transparent; 
                color: #94A3B8; 
                font-weight: bold;
                font-size: 13px;
            }
            QListWidget::item:hover {
                background-color: #121D38;
                color: #00E5FF;
            }
            QListWidget::item:selected {
                background-color: rgba(0, 229, 255, 0.08); 
                border-left: 4px solid #00E5FF; 
                color: #FFFFFF;
            }
            """
        )
        layout.addWidget(self.list_widget)

    @property
    def currentRowChanged(self):
        return self.list_widget.currentRowChanged

    def setCurrentRow(self, row: int) -> None:
        self.list_widget.setCurrentRow(row)

    def toggle_sidebar(self):
        self.is_expanded = not self.is_expanded

        if self.is_expanded:
            self.setFixedWidth(230)
            self.top_logo_btn.setText("≡  MENU")
            self.top_logo_btn.setStyleSheet(self.btn_style_expanded)

            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                icon_path, full_text, tooltip = item.data(
                    Qt.ItemDataRole.UserRole)
                item.setText(f"   {full_text}")
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        else:
            self.setFixedWidth(75)
            self.top_logo_btn.setText("≡")
            self.top_logo_btn.setStyleSheet(self.btn_style_collapsed)

            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                item.setText("")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

    def add_nav_item(self, icon_path: str, full_text: str, tooltip: str = "") -> None:
        item = QListWidgetItem(QIcon(icon_path), "")

        item.setData(Qt.ItemDataRole.UserRole, (icon_path, full_text, tooltip))
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        if tooltip:
            wrapped_tooltip = "<br>".join(textwrap.wrap(tooltip, width=25))
            hover_text = (
                f"<span style='color: #00E5FF; font-size: 13px; font-weight: bold;'>{full_text}</span><br><br>"
                f"<span style='color: #E2E8F0; font-size: 11px;'>{wrapped_tooltip}</span>"
            )
        else:
            hover_text = f"<span style='color: #00E5FF; font-size: 13px; font-weight: bold;'>{full_text}</span>"

        item.setToolTip(hover_text)
        self.list_widget.addItem(item)


class MainWindow(QMainWindow):
    """
    Sporty 4-pane main window hosting isolated feature modules inside an
    STM32CubeProgrammer-style workspace with a persistent right-hand diagnostic
    dock and a real-time DAPLink status bar.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.current_interface = "B-Link (SWD)"
        self.setWindowTitle(
            "B-Link Production & Diagnostic Suite v1.0"
        )
        self.resize(1366, 820)
        self.setMinimumSize(1024, 640)

        # Instantiate isolated feature modules
        self.memory_widget = MemoryViewerWidget()
        self.programmer_widget = ProductionProgrammerWidget()
        self.ob_widget = OptionBytesWidget()
        self.serial_widget = SerialMonitorWidget()
        self.diagnostic_widget = TargetDiagnosticWidget()
        self.diagnostic_widget.setMinimumWidth(380)
        self.batch_widget = BatchProgrammerWidget()

        # Build application layout
        self._init_central_workspace()
        self._init_right_diagnostic_dock()
        self._init_bottom_log_dock()

        self.status_bar = GlobalStatusBar(self)
        self.setStatusBar(self.status_bar)

        self.diagnostic_widget.interface_changed.connect(
            self.on_global_interface_changed
        )
        self.status_bar.probe_status_changed.connect(
            self.diagnostic_widget.on_global_probe_status_changed
        )

        # ⬅️ نام متغیر حافظه اصلاح شد تا سیگنال درست متصل شود
        self.diagnostic_widget.target_changed.connect(
            self.memory_widget.set_mcu_target
        )

        logger.info("4-pane workspace initialized successfully.")
        QTimer.singleShot(2000, self._run_silent_update_check)
        self.global_pack_downloader = GlobalDownloadDialog(self)

    def _run_silent_update_check(self):
        self.updater_thread = AppUpdateWorker(self)
        self.updater_thread.check_finished.connect(self._on_auto_update_result)
        self.updater_thread.start()

    def _on_auto_update_result(self, success: bool, is_newer: bool, version: str, notes: str, url: str, error: str):

        if success and is_newer:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Software Update Available")
            msg_box.setText(
                f"A new version of B-Link software (v{version}) is available!")
            msg_box.setInformativeText(
                f"Release Notes:\n{notes}\n\nWould you like to download the update now?")

            btn_download = msg_box.addButton(
                "📥 Download Update", QMessageBox.ButtonRole.AcceptRole)
            btn_cancel = msg_box.addButton(
                "Remind Me Later", QMessageBox.ButtonRole.RejectRole)

            msg_box.exec()

            if msg_box.clickedButton() == btn_download:
                QDesktopServices.openUrl(QUrl(url))

    def on_global_interface_changed(self, new_interface: str) -> None:
        self.current_interface = new_interface

        if hasattr(self.memory_widget, "set_interface_type"):
            self.memory_widget.set_interface_type(new_interface)

        if hasattr(self.programmer_widget, "set_interface_type"):
            self.programmer_widget.set_interface_type(new_interface)

        if hasattr(self.ob_widget, "set_interface_type"):
            self.ob_widget.set_interface_type(new_interface)

        logger.info(f"MainWindow updated global interface to: {new_interface}")

    def _init_central_workspace(self) -> None:
        central_container = QWidget()
        layout = QHBoxLayout(central_container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = SidebarNavWidget()

        self.sidebar.add_nav_item(ICON_MEMORY, "Device Memory")
        self.sidebar.add_nav_item(ICON_PROGRAMMER, "Programmer")
        self.sidebar.add_nav_item(ICON_LOCK, "Option Bytes")
        self.sidebar.add_nav_item(ICON_SERIAL, "Serial Monitor")
        self.sidebar.add_nav_item(ICON_BATCH, "Batch Flashing")

        self.workspace_stack = QStackedWidget()
        self.workspace_stack.addWidget(self.memory_widget)        # Index 0
        self.workspace_stack.addWidget(self.programmer_widget)    # Index 1
        self.workspace_stack.addWidget(self.ob_widget)            # Index 2
        self.workspace_stack.addWidget(self.serial_widget)        # Index 3
        self.workspace_stack.addWidget(self.batch_widget)         # Index 4

        self.sidebar.currentRowChanged.connect(
            self.workspace_stack.setCurrentIndex
        )
        self.sidebar.setCurrentRow(0)

        layout.addWidget(self.sidebar)
        layout.addWidget(self.workspace_stack, stretch=1)
        self.setCentralWidget(central_container)

    def _init_right_diagnostic_dock(self) -> None:
        self.right_dock = QDockWidget(
            "Target Diagnostic", self
        )
        self.right_dock.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.right_dock.setFeatures(
            QDockWidget.DockWidgetFeature.NoDockWidgetFeatures
        )
        self.right_dock.setWidget(self.diagnostic_widget)
        self.right_dock.setMinimumWidth(320)
        self.addDockWidget(
            Qt.DockWidgetArea.RightDockWidgetArea, self.right_dock
        )
        self.right_dock.show()

    def _init_bottom_log_dock(self) -> None:
        self.log_dock = QDockWidget("System Log Console", self)
        self.log_dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea)

        self.log_dock.setFeatures(
            QDockWidget.DockWidgetFeature.NoDockWidgetFeatures
        )

        self.log_console = QPlainTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setFont(QFont("Consolas", 10))
        self.log_console.setMaximumHeight(160)

        self.log_console.setStyleSheet(
            """
            QPlainTextEdit {
                background-color: #03060E; /* مشکی بسیار عمیق */
                color: #00E5FF; /* متن سایان درخشان */
                border: 2px solid #0C1327;
                border-radius: 6px;
                selection-background-color: #0077B6;
                padding: 10px;
            }
            """
        )

        self.log_console.appendPlainText(
            "[INFO] BlueWave B-Link Suite initialized. Ready for extreme performance."
        )

        self.log_dock.setWidget(self.log_console)
        self.addDockWidget(
            Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock
        )

    def closeEvent(self, event) -> None:
        logger.info(
            "Application shutting down. Terminating background threads...")
        try:
            active_modules = [
                getattr(self, "diagnostic_widget", None),
                getattr(self, "programmer_widget", None),
                getattr(self, "memory_widget", None),
                getattr(self, "ob_widget", None),
                getattr(self, "serial_widget", None),
                getattr(self, "status_bar", None),
                getattr(self, "batch_widget", None),
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
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)

    app.setStyle("Fusion")

    dark_palette = QPalette()
    dark_palette.setColor(QPalette.ColorRole.Window, QColor("#070B19"))
    dark_palette.setColor(QPalette.ColorRole.WindowText, QColor("#F8FAFC"))
    dark_palette.setColor(QPalette.ColorRole.Base, QColor("#03060E"))
    dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#0C1327"))
    dark_palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#0C1327"))
    dark_palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#00E5FF"))
    dark_palette.setColor(QPalette.ColorRole.Text, QColor("#F8FAFC"))
    dark_palette.setColor(QPalette.ColorRole.Button, QColor("#121D38"))
    dark_palette.setColor(QPalette.ColorRole.ButtonText, QColor("#F8FAFC"))
    dark_palette.setColor(QPalette.ColorRole.BrightText, QColor("#E63946"))
    dark_palette.setColor(QPalette.ColorRole.Highlight, QColor("#00B4D8"))
    dark_palette.setColor(
        QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))

    app.setPalette(dark_palette)
    app.setStyleSheet(BLUEWAVE_SPORTY_QSS)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
