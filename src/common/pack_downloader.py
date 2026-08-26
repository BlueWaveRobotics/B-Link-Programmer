import sys
from PySide6.QtCore import Qt, QObject, Signal, Slot, QMetaObject, Q_RETURN_ARG, Q_ARG
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QApplication, QProgressBar, QPushButton, QMessageBox
from src.common.logger import get_logger

logger = get_logger("GlobalDownloader")


class DownloadSignalBus(QObject):
    _instance = None

    # ⬅️ سیگنال جدید برای توقف تایمر قبل از سوال
    download_preparing = Signal(str)
    download_started = Signal(str)
    download_finished = Signal(bool, str)
    download_progress = Signal(int, str)

    def __init__(self):
        super().__init__()
        self.cancel_requested = False
        self.dialog_instance = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = DownloadSignalBus()
        return cls._instance


class GlobalDownloadDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Hardware Pack Download")
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint)
        self.setModal(True)
        self.setFixedSize(450, 210)
        self.setStyleSheet("""
            QDialog {
                background-color: #070B19;
                border: 2px solid #00E5FF;
                border-radius: 8px;
            }
            QLabel {
                color: #F8FAFC;
                font-size: 13px;
                font-family: "Segoe UI";
            }
            QLabel#title {
                color: #00E5FF;
                font-size: 16px;
                font-weight: bold;
                margin-bottom: 5px;
            }
            QProgressBar {
                border: 1px solid #1A2642;
                border-radius: 4px;
                background-color: #03060E;
                text-align: center;
                color: #F8FAFC;
                font-size: 12px;
                font-weight: bold;
                height: 24px; 
                padding-top: 3px;     
                padding-bottom: 2px;
                margin-top: 10px;
                margin-bottom: 10px;
            }
            QProgressBar::chunk {
                background-color: #00E5FF;
                border-radius: 3px;
            }
            QPushButton {
                background-color: #121D38;
                color: #EF4444;
                border: 1px solid #EF4444;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #EF4444;
                color: #FFFFFF;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)

        title = QLabel("DOWNLOADING HARDWARE DRIVER", self)
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self.lbl_info = QLabel("Connecting to ARM Global Index...", self)
        self.lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_info.setWordWrap(True)
        layout.addWidget(self.lbl_info)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.btn_cancel = QPushButton("Cancel Download", self)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        layout.addWidget(
            self.btn_cancel, alignment=Qt.AlignmentFlag.AlignCenter)

        bus = DownloadSignalBus.instance()
        bus.dialog_instance = self
        bus.download_started.connect(self._on_download_started)
        bus.download_finished.connect(self._on_download_finished)
        bus.download_progress.connect(self._on_download_progress)

    @Slot(str, result=bool)
    def ask_permission(self, target_name: str) -> bool:
        while QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()

        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setWindowTitle("First Time Setup")
        msg.setText(
            f"Hardware drivers for '{target_name}' were not found on this computer.")
        msg.setInformativeText(
            "This is the first time you are connecting to this MCU type.\n\nDo you want to download and install the required CMSIS-Pack from ARM Global Index now?")
        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        msg.setStyleSheet("""
            QMessageBox { background-color: #070B19; color: #F8FAFC; }
            QLabel { color: #F8FAFC; font-size: 13px; font-weight: bold; }
            QPushButton { background-color: #121D38; color: #00E5FF; border: 1px solid #00E5FF; padding: 6px 15px; border-radius: 4px; font-weight: bold;}
            QPushButton:hover { background-color: #00E5FF; color: #070B19; }
        """)

        return msg.exec() == QMessageBox.StandardButton.Yes

    def _on_cancel_clicked(self):
        self.lbl_info.setText("Cancelling... Stopping processes.")
        self.progress_bar.setRange(0, 0)
        self.btn_cancel.setEnabled(False)
        DownloadSignalBus.instance().cancel_requested = True

    @Slot(str)
    def _on_download_started(self, target_name: str):
        self.btn_cancel.setEnabled(True)
        DownloadSignalBus.instance().cancel_requested = False
        self.lbl_info.setText(
            f"Missing definitions for {target_name}. Fetching from ARM...")
        self.progress_bar.setRange(0, 0)

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.show()
        self.raise_()
        self.activateWindow()

    @Slot(int, str)
    def _on_download_progress(self, pct: int, msg: str):
        if pct == 100:
            self.progress_bar.setRange(0, 0)
            self.lbl_info.setText(
                "Download complete!\nFinalizing installation & configuring core cache. Almost done...")
        elif pct >= 0:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(pct)
            if msg:
                self.lbl_info.setText(msg)
        else:
            self.progress_bar.setRange(0, 0)
            if msg:
                self.lbl_info.setText(msg)

    @Slot(bool, str)
    def _on_download_finished(self, success: bool, message: str):
        while QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()
        self.hide()
