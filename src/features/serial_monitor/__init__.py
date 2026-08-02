"""
CDC Serial Monitor feature module exports.
Provides real-time asynchronous serial communication, HEX/ASCII formatting,
and COM port diagnostics.
"""

from src.features.serial_monitor.serial_worker import SerialWorker
from src.features.serial_monitor.widget import SerialMonitorWidget

__all__ = [
    "SerialWorker",
    "SerialMonitorWidget",
]
