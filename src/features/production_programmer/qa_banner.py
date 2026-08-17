# """
# Industrial Visual QA Banner Widget.
# Provides high-visibility PASS/FAIL status indication for production line operators.
# """

# from PySide6.QtCore import Qt
# from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel


# class QABannerWidget(QFrame):
#     """
#     Dynamic color-coded banner displaying programming state and cycle results.
#     """

#     def __init__(self, parent=None):
#         super().__init__(parent)
#         self._setup_ui()
#         self.set_ready_state()

#     def _setup_ui(self) -> None:
#         self.setFrameShape(QFrame.StyledPanel)
#         self.setFrameShadow(QFrame.Raised)
#         self.setFixedHeight(105)

#         layout = QVBoxLayout(self)
#         layout.setContentsMargins(16, 10, 16, 10)
#         layout.setSpacing(4)

#         self.status_label = QLabel("READY", self)
#         self.status_label.setAlignment(Qt.AlignCenter)
#         self.status_label.setStyleSheet(
#             "font-size: 30px; font-weight: 800; letter-spacing: 2px;")

#         self.detail_label = QLabel(
#             "Waiting for production cycle to start...", self
#         )
#         self.detail_label.setAlignment(Qt.AlignCenter)
#         self.detail_label.setStyleSheet("font-size: 13px; font-weight: 600;")

#         layout.addWidget(self.status_label)
#         layout.addWidget(self.detail_label)

#     def set_ready_state(self) -> None:
#         """Sets banner to neutral ready appearance."""
#         self.setStyleSheet(
#             """
#             QFrame {
#                 background-color: #1E222A;
#                 border: 2px solid #3A3F4B;
#                 border-radius: 8px;
#             }
#             QLabel {
#                 color: #E0E0E0;
#                 border: none;
#                 background: transparent;
#             }
#         """
#         )
#         self.status_label.setText("READY")
#         self.detail_label.setText(
#             "Insert STM32 board and press Start Programming")

#     def set_busy_state(self, message: str = "Programming in progress...") -> None:
#         """Sets banner to active processing appearance."""
#         self.setStyleSheet(
#             """
#             QFrame {
#                 background-color: #2B220B;
#                 border: 2px solid #D4AC0D;
#                 border-radius: 8px;
#             }
#             QLabel {
#                 color: #F4D03F;
#                 border: none;
#                 background: transparent;
#             }
#         """
#         )
#         self.status_label.setText("IN PROGRESS")
#         self.detail_label.setText(message)

#     def set_pass_state(self, cycle_time: float, message: str = "VERIFIED PASS") -> None:
#         """Sets banner to high-visibility PASS appearance."""
#         self.setStyleSheet(
#             """
#             QFrame {
#                 background-color: #0E2B1A;
#                 border: 2px solid #28A745;
#                 border-radius: 8px;
#             }
#             QLabel {
#                 color: #58D68D;
#                 border: none;
#                 background: transparent;
#             }
#         """
#         )
#         self.status_label.setText("PASS")
#         self.detail_label.setText(
#             f"{message} | Total Cycle Time: {cycle_time:.2f} s"
#         )

#     def set_fail_state(self, reason: str, cycle_time: float = 0.0) -> None:
#         """Sets banner to high-visibility FAIL appearance."""
#         self.setStyleSheet(
#             """
#             QFrame {
#                 background-color: #331212;
#                 border: 2px solid #DC3545;
#                 border-radius: 8px;
#             }
#             QLabel {
#                 color: #EC7063;
#                 border: none;
#                 background: transparent;
#             }
#         """
#         )
#         self.status_label.setText("FAIL")
#         time_str = f" | Cycle Time: {cycle_time:.2f} s" if cycle_time > 0 else ""
#         self.detail_label.setText(f"{reason}{time_str}")
"""
Industrial Visual QA Banner Widget for BlueWave.
Provides high-visibility PASS/FAIL status indication for production line operators.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel


class QABannerWidget(QFrame):
    """
    Dynamic color-coded banner displaying programming state and cycle results.
    Tailored for the BlueWave Dark Industrial Theme.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self.set_ready_state()

    def _setup_ui(self) -> None:
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Raised)
        self.setFixedHeight(85)  # کمی فشرده‌تر برای هماهنگی با UI مینیمال

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(2)

        self.status_label = QLabel("READY", self)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet(
            "font-size: 26px; font-weight: 900; letter-spacing: 2px;")

        self.detail_label = QLabel(
            "Waiting for production cycle to start...", self
        )
        self.detail_label.setAlignment(Qt.AlignCenter)
        self.detail_label.setStyleSheet("font-size: 13px; font-weight: 600;")

        layout.addWidget(self.status_label)
        layout.addWidget(self.detail_label)

    def set_ready_state(self) -> None:
        """Sets banner to neutral ready appearance (BlueWave Deep Navy)."""
        self.setStyleSheet(
            """
            QFrame {
                background-color: #0C1327;
                border: 2px solid #1A2642;
                border-radius: 6px;
            }
            QLabel {
                color: #94A3B8;
                border: none;
                background: transparent;
            }
        """
        )
        self.status_label.setStyleSheet(
            "font-size: 26px; font-weight: 900; letter-spacing: 2px; color: #F8FAFC;")
        self.status_label.setText("READY")
        self.detail_label.setText(
            "Insert STM32 board and press Start Programming")

    def set_busy_state(self, message: str = "Programming in progress...") -> None:
        """Sets banner to active processing appearance (BlueWave Neon Cyan)."""
        self.setStyleSheet(
            """
            QFrame {
                background-color: #03060E;
                border: 2px solid #00E5FF;
                border-radius: 6px;
            }
            QLabel {
                color: #00E5FF;
                border: none;
                background: transparent;
            }
        """
        )
        self.status_label.setStyleSheet(
            "font-size: 26px; font-weight: 900; letter-spacing: 2px; color: #00E5FF;")
        self.status_label.setText("IN PROGRESS")
        self.detail_label.setText(message)

    def set_pass_state(self, cycle_time: float, message: str = "VERIFIED PASS") -> None:
        """Sets banner to high-visibility PASS appearance (BlueWave Emerald Green)."""
        self.setStyleSheet(
            """
            QFrame {
                background-color: rgba(16, 185, 129, 0.08); /* پس‌زمینه شیشه‌ای سبز */
                border: 2px solid #10B981;
                border-radius: 6px;
            }
            QLabel {
                color: #10B981;
                border: none;
                background: transparent;
            }
        """
        )
        self.status_label.setStyleSheet(
            "font-size: 26px; font-weight: 900; letter-spacing: 2px; color: #10B981;")
        self.status_label.setText("PASS")
        self.detail_label.setText(
            f"{message} | Total Cycle Time: {cycle_time:.2f} s"
        )

    def set_fail_state(self, reason: str, cycle_time: float = 0.0) -> None:
        """Sets banner to high-visibility FAIL appearance (BlueWave Red)."""
        self.setStyleSheet(
            """
            QFrame {
                background-color: rgba(239, 68, 68, 0.08); /* پس‌زمینه شیشه‌ای قرمز */
                border: 2px solid #EF4444;
                border-radius: 6px;
            }
            QLabel {
                color: #EF4444;
                border: none;
                background: transparent;
            }
        """
        )
        self.status_label.setStyleSheet(
            "font-size: 26px; font-weight: 900; letter-spacing: 2px; color: #EF4444;")
        self.status_label.setText("FAIL")
        time_str = f" | Cycle Time: {cycle_time:.2f} s" if cycle_time > 0 else ""
        self.detail_label.setText(f"{reason}{time_str}")
