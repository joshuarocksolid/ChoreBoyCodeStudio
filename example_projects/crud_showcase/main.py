"""CRUD Showcase — ChoreBoy Example Project.

Entry point that launches the task-manager GUI.
Run this file with F5 inside ChoreBoy Code Studio.
"""

import sys

from PySide2.QtWidgets import QApplication

from app.main_window import MainWindow


def main():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
