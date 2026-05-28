"""
gui_app.py — Launch the Voice-to-Macro GUI.

Usage:
    python gui_app.py
"""

import sys

from PyQt6.QtWidgets import QApplication

from gui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Voice-to-Macro")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
