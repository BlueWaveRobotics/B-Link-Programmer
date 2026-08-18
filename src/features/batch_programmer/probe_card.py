"""
Industrial UI Card Widget for a single DAPLink probe slot.
Displays independent progress, 96-bit chip UID, cycle time,
and PASS/FAIL visual states for parallel batch programming.
"""

from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QCheckBox,
)

from src.features.batch_programmer.probe_manager import ProbeInfo


class ProbeSlotCard(QFrame):
    """
    Visual UI component representing one physical programming slot/probe.
    """

    # Signal emitted when operator toggles the slot checkbox: (unique_id, is_enabled)
    toggled_signal = Signal(str, bool)

    def __init__(self, probe_info: ProbeInfo, parent: Optional[QFrame] = None):
        super().__init__(parent)
        self.probe_info = probe_info
        self._is_enabled = True
        self.setObjectName("ProbeSlotCard")
        self._setup_ui()
        self.set_ready_state()

    def _setup_ui(self) -> None:
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Raised)
        self.setFixedHeight(120)
        self.setMinimumWidth(260)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # -------------------------------------------------------------
        # Row 1: Enable Checkbox + Probe Display Name + Status badge
        # -------------------------------------------------------------
        top_layout = QHBoxLayout()
        self.chk_enable = QCheckBox(self.probe_info.display_name, self)
        self.chk_enable.setChecked(True)
        self.chk_enable.setStyleSheet(
            "font-weight: bold; font-size: 13px; color: #FFFFFF;"
        )
        self.chk_enable.toggled.connect(self._on_toggled)

        self.lbl_status = QLabel("READY", self)
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setFixedWidth(75)
        self.lbl_status.setStyleSheet(
            "background-color: #34495E; color: white; font-weight: bold; "
            "border-radius: 4px; padding: 2px;"
        )

        top_layout.addWidget(self.chk_enable)
        top_layout.addStretch()
        top_layout.addWidget(self.lbl_status)
        layout.addLayout(top_layout)

        # -------------------------------------------------------------
        # Row 2: Target Hardware UID Display
        # -------------------------------------------------------------
        uid_layout = QHBoxLayout()
        uid_layout.addWidget(QLabel("Chip UID:", self))
        self.lbl_uid = QLabel("---", self)
        self.lbl_uid.setStyleSheet(
            "font-family: Consolas, monospace; color: #4EC9B0; font-weight: bold;"
        )
        uid_layout.addWidget(self.lbl_uid)
        uid_layout.addStretch()
        layout.addLayout(uid_layout)

        # -------------------------------------------------------------
        # Row 3: Dedicated Progress Bar
        # -------------------------------------------------------------
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(14)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        # -------------------------------------------------------------
        # Row 4: Cycle Time & Message Footer
        # -------------------------------------------------------------
        self.lbl_footer = QLabel("Slot ready for production cycle.", self)
        self.lbl_footer.setStyleSheet("font-size: 11px; color: #BDC3C7;")
        layout.addWidget(self.lbl_footer)

    def _on_toggled(self, checked: bool) -> None:
        self._is_enabled = checked
        self.setEnabled(checked)
        self.toggled_signal.emit(self.probe_info.unique_id, checked)
        if not checked:
            self.lbl_status.setText("DISABLED")
            self.lbl_status.setStyleSheet(
                "background-color: #555555; color: #AAAAAA; font-weight: bold; border-radius: 4px; padding: 2px;"
            )
            self.setStyleSheet(
                "QFrame#ProbeSlotCard { background-color: #21252B; border: 2px solid #333333; border-radius: 8px; }"
            )
        else:
            self.set_ready_state()

    def set_ready_state(self) -> None:
        """Sets the card to neutral ready state."""
        self.lbl_status.setText("READY")
        self.lbl_status.setStyleSheet(
            "background-color: #34495E; color: white; font-weight: bold; border-radius: 4px; padding: 2px;"
        )
        self.lbl_footer.setText("Slot ready for production cycle.")
        self.progress_bar.setValue(0)
        self.setStyleSheet(
            "QFrame#ProbeSlotCard { background-color: #21252B; border: 2px solid #3E4451; border-radius: 8px; }"
        )

    def set_busy_state(self, message: str = "Programming...") -> None:
        """Sets the card to active programming state."""
        self.lbl_status.setText("BUSY")
        self.lbl_status.setStyleSheet(
            "background-color: #D68910; color: white; font-weight: bold; border-radius: 4px; padding: 2px;"
        )
        self.lbl_footer.setText(message)
        self.setStyleSheet(
            "QFrame#ProbeSlotCard { background-color: #21252B; border: 2px solid #F39C12; border-radius: 8px; }"
        )

    def set_pass_state(self, cycle_time: float, uid_str: str) -> None:
        """Sets the card to successful PASS state."""
        self.lbl_status.setText("PASS")
        self.lbl_status.setStyleSheet(
            "background-color: #1E8449; color: white; font-weight: bold; border-radius: 4px; padding: 2px;"
        )
        self.lbl_uid.setText(uid_str)
        self.lbl_footer.setText(
            f"Verified PASS | Cycle Time: {cycle_time:.2f} s"
        )
        self.progress_bar.setValue(100)
        self.setStyleSheet(
            "QFrame#ProbeSlotCard { background-color: #21252B; border: 2px solid #28A745; border-radius: 8px; }"
        )

    def set_fail_state(self, error_msg: str, cycle_time: float = 0.0) -> None:
        """Sets the card to failed FAIL state."""
        self.lbl_status.setText("FAIL")
        self.lbl_status.setStyleSheet(
            "background-color: #922B21; color: white; font-weight: bold; border-radius: 4px; padding: 2px;"
        )
        time_text = f" ({cycle_time:.2f} s)" if cycle_time > 0 else ""
        self.lbl_footer.setText(f"FAIL{time_text}: {error_msg}")
        self.setStyleSheet(
            "QFrame#ProbeSlotCard { background-color: #21252B; border: 2px solid #DC3545; border-radius: 8px; }"
        )

    def update_progress(self, percent: int) -> None:
        """Updates the slot-specific progress bar."""
        self.progress_bar.setValue(max(0, min(percent, 100)))

    @property
    def is_slot_enabled(self) -> bool:
        """Returns True if operator has enabled this probe slot."""
        return self._is_enabled
