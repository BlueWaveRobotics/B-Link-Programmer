"""
Silent App Update Checker Service
Reads local version.json and compares it with remote app_config.json silently.
"""

import json
import os
import sys
import urllib.request
import ssl
from PySide6.QtCore import QThread, Signal
from src.common import get_logger

logger = get_logger("AppUpdater")

REMOTE_CONFIG_URL = "https://www.bluewaverobotics.ir/app_config.json"


def get_base_path():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class AppUpdateWorker(QThread):
    check_finished = Signal(bool, bool, str, str, str, str)

    def run(self):
        try:
            logger.info("Running silent background update check...")
            local_version = "1.0.0"
            version_file_path = os.path.join(get_base_path(), "version.json")

            if os.path.exists(version_file_path):
                with open(version_file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    local_version = data.get("app_version", "1.0.0")

            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            req = urllib.request.Request(REMOTE_CONFIG_URL, headers={
                                         'User-Agent': 'B-Link-Desktop'})
            with urllib.request.urlopen(req, timeout=3.0, context=ctx) as response:
                remote_data = json.loads(response.read().decode('utf-8'))

            app_info = remote_data.get("BLink_App", {})
            remote_version = app_info.get("latest_version", local_version)
            release_notes = app_info.get(
                "release_notes", "No release notes provided.")
            download_url = app_info.get("download_url", "")

            if self.is_newer_version(local_version, remote_version):
                logger.info(f"New update found: {remote_version}")
                self.check_finished.emit(
                    True, True, remote_version, release_notes, download_url, "")
            else:
                logger.info("App is up to date. (Silent exit)")
                self.check_finished.emit(
                    True, False, local_version, "", "", "")

        except Exception as e:
            logger.warning(
                f"Auto-update check bypassed (No internet or server down): {str(e)}")
            self.check_finished.emit(False, False, "", "", "", str(e))

    def is_newer_version(self, local_ver: str, remote_ver: str) -> bool:
        try:
            l_parts = [int(x) for x in local_ver.replace('v', '').split('.')]
            r_parts = [int(x) for x in remote_ver.replace('v', '').split('.')]
            return r_parts > l_parts
        except Exception:
            return local_ver != remote_ver
