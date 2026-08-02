"""
Abstract base worker class providing standardized Qt signals and thread lifecycle
management for asynchronous background operations.
"""

from typing import Optional
from PySide6.QtCore import QObject, Signal, Slot


class BaseWorker(QObject):
    """
    Base class for feature-level workers running inside dedicated QThreads.
    Standardizes GUI communication signals across the suite.
    """

    # Shared communication signals for UI updates
    log_signal = Signal(str)
    progress_signal = Signal(int)
    error_signal = Signal(str)
    status_signal = Signal(bool, str)
    finished_signal = Signal(bool, str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._is_running = True

    def log(self, message: str) -> None:
        """Emit a formatted log message to the UI console."""
        self.log_signal.emit(message)

    def report_progress(self, percent: int) -> None:
        """Emit progress percentage bounded between 0 and 100."""
        bounded = max(0, min(int(percent), 100))
        self.progress_signal.emit(bounded)

    def report_error(self, error_message: str) -> None:
        """Emit an error notification and log the failure."""
        self.error_signal.emit(error_message)
        self.log_signal.emit(f"[ERROR] {error_message}")

    @Slot()
    def stop_worker(self) -> None:
        """Safely signal the worker to terminate ongoing loops or operations."""
        self._is_running = False
