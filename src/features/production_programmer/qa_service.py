"""
Quality Assurance and Production Statistics Service.
Tracks shift yield metrics, pass/fail counters, and hardware UID validity rules.
"""

from typing import Tuple


class QAService:
    """
    Manages real-time production statistics and automated QA validation rules.
    """

    def __init__(self) -> None:
        self.total_pass: int = 0
        self.total_fail: int = 0

    def record_result(self, success: bool) -> None:
        """Increments the appropriate production counter based on result."""
        if success:
            self.total_pass += 1
        else:
            self.total_fail += 1

    def reset_statistics(self) -> None:
        """Resets all production shift counters to zero."""
        self.total_pass = 0
        self.total_fail = 0

    @property
    def total_cycles(self) -> int:
        """Returns total number of programming cycles attempted."""
        return self.total_pass + self.total_fail

    @property
    def yield_percentage(self) -> float:
        """Calculates manufacturing pass yield percentage (0.0 to 100.0)."""
        if self.total_cycles == 0:
            return 100.0
        return round((self.total_pass / self.total_cycles) * 100.0, 1)

    def get_statistics(self) -> Tuple[int, int, int, float]:
        """Returns tuple: (total_pass, total_fail, total_cycles, yield_pct)."""
        return (
            self.total_pass,
            self.total_fail,
            self.total_cycles,
            self.yield_percentage,
        )

    @staticmethod
    def is_valid_uid(uid_string: str) -> bool:
        """
        Validates 96-bit STM32 hardware UID against corrupted/blank patterns.
        """
        clean_uid = uid_string.replace(
            "-", "").replace(" ", "").strip().upper()
        if not clean_uid or "ERROR" in clean_uid:
            return False
        if len(clean_uid) != 24:
            return False
        if clean_uid == "0" * 24 or clean_uid == "F" * 24:
            return False
        return True
