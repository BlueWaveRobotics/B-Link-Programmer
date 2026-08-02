import sys
import logging

from PySide6.QtWidgets import QApplication

from src.gui import MainWindow
logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
