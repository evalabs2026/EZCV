"""
main.py

Entry point for EZCV. Run this file to launch the application:
    python main.py
"""

import os
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from gui.main_window import MainWindow


def resource_path(relative_path):
    """
    Get absolute path to resource.
    Works both in development and in a PyInstaller executable.
    """
    if getattr(sys, "frozen", False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("EZCV")

    icon = QIcon(resource_path("assets/ezcv_icon.ico"))

    app.setWindowIcon(icon)

    window = MainWindow()
    window.setWindowIcon(icon)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()