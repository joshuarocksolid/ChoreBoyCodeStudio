"""CRUD Showcase — ChoreBoy Example Project.

Entry point that launches the task-manager GUI.
Run this file with F5 inside ChoreBoy Code Studio.
"""

import sys

from PySide2.QtGui import QFont
from PySide2.QtWidgets import QApplication

from app.theme import build_stylesheet, detect_dark_mode, get_tokens


def main():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    is_dark = detect_dark_mode()
    tokens = get_tokens(is_dark)
    app.setStyleSheet(build_stylesheet(tokens))

    font = app.font()
    font.setPointSize(12)
    app.setFont(font)

    from app.main_window import MainWindow

    window = MainWindow(tokens=tokens)
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
