"""
SQLite Traceability Database Service for industrial production line logging.
Provides zero-configuration local storage and instant Excel/CSV export capabilities.
"""

import sqlite3
import csv
from datetime import datetime
from typing import Optional
from src.common import get_logger

logger = get_logger("TraceabilityDB")


class TraceabilityDatabase:
    """
    Manages local SQLite database for device programming records and CSV export.
    """

    def __init__(self, db_path: str = "production_logs.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Creates the production traceability table if it does not exist."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS production_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        firmware_name TEXT NOT NULL,
                        uid_96bit TEXT NOT NULL,
                        serial_number TEXT,
                        status TEXT NOT NULL,
                        message TEXT
                    )
                    """
                )
                conn.commit()
            logger.info("Traceability SQLite database initialized.")
        except sqlite3.Error as err:
            logger.error(f"Failed to initialize SQLite DB: {err}")

    def log_operation(
        self,
        firmware_name: str,
        uid_96bit: str,
        serial_number: Optional[str],
        status: str,
        message: str = "",
    ) -> None:
        """Inserts a new production record into the local SQLite database."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO production_history 
                    (timestamp, firmware_name, uid_96bit, serial_number, status, message)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (timestamp, firmware_name, uid_96bit,
                     serial_number, status, message),
                )
                conn.commit()
            logger.info(f"Traceability record saved: {status} [{uid_96bit}]")
        except sqlite3.Error as err:
            logger.error(f"Failed to write record to SQLite DB: {err}")

    def export_to_csv(self, file_path: str) -> bool:
        """
        Exports the entire SQLite production history into a CSV/Excel-compatible file.
        Returns True if successful, False otherwise.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM production_history ORDER BY id DESC")
                rows = cursor.fetchall()
                headers = [description[0]
                           for description in cursor.description]

            with open(file_path, mode="w", newline="", encoding="utf-8-sig") as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow(headers)
                writer.writerows(rows)

            logger.info(
                f"Production logs successfully exported to: {file_path}")
            return True
        except Exception as err:
            logger.error(f"Export to CSV failed: {err}")
            return False
