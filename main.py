"""
main.py

Entry point for EZCV. Run this file to launch the application:
    python main.py
"""

import sys
from PySide6.QtWidgets import QApplication 
from PySide6.QtGui import QIcon
from gui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("EZCV")

    app.setWindowIcon(QIcon("assets/ezcv_icon.ico"))

    window = MainWindow()
    window.setWindowIcon(QIcon("assets/ezcv_icon.ico"))
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
