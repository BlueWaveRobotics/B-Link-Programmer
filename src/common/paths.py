# src/common/paths.py
import sys
import os


def get_path(relative_path):
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        base_path = os.path.abspath(os.path.join(current_dir, "..", ".."))
    return os.path.join(base_path, relative_path)


def get_storage_path(filename):
    app_data = os.getenv('APPDATA') or os.path.expanduser('~')
    app_dir = os.path.join(app_data, "B-Link-Suite")

    if not os.path.exists(app_dir):
        os.makedirs(app_dir)

    return os.path.join(app_dir, filename)
