"""Launch the form builder. The chrome follows the system light or dark setting."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from spikes.form_builder.theme import ensure_style, system_theme
    from spikes.form_builder.window import MainWindow
    from spikes.form_builder.xmlio import load_path

    app = QApplication(sys.argv)
    app.setApplicationName("Form Builder")
    app.setOrganizationName("ChoreBoy")
    ensure_style(app)
    window = MainWindow(system_theme(app), follow_system=True)
    window.resize(1360, 860)
    window.show()
    paths = [arg for arg in sys.argv[1:] if arg.endswith(".ui")]
    if paths:
        window.load_document(load_path(paths[0]), paths[0])
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
