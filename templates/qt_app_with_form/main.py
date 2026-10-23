"""Show the generated main window.

``CBCS_QUIT_AFTER_SHOW=1`` leaves the event loop immediately so a headless
check can reach ``app.exec`` and return.
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from forms.main_window_window import MainWindowWindow


def main() -> int:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    window = MainWindowWindow()
    window.show()
    if os.environ.get("CBCS_QUIT_AFTER_SHOW") == "1":
        QTimer.singleShot(0, app.quit)
    return int(app.exec())


if __name__ == "__main__":
    raise SystemExit(main())
