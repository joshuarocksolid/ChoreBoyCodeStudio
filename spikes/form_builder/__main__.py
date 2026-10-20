"""Launch the form builder."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from spikes.form_builder.theme import apply_theme, detect_theme
    from spikes.form_builder.window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Form builder")
    name = detect_theme(app)
    apply_theme(app, name)
    window = MainWindow(name)
    window.resize(1280, 800)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
