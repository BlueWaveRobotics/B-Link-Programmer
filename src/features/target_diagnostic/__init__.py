"""
Target Diagnostic feature module exports.
Provides non-intrusive target chip identification and ARM core diagnostics.
"""

from src.features.target_diagnostic.widget import TargetDiagnosticWidget
from src.features.target_diagnostic.firmware_update_service import ProbeFirmwareUpdateService

__all__ = [
    "TargetDiagnosticWidget",
    "ProbeFirmwareUpdateService",
]
