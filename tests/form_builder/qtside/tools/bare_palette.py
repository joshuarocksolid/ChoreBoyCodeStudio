# pyright: reportAttributeAccessIssue=false
"""Print Fusion palette colors for a form realized in a bare QApplication.

The parent test compares a themed shell against this output. The process must
not apply a chrome style sheet.
"""

from __future__ import annotations

import json
import sys

from app.qt.QtWidgets import QApplication, QMainWindow
from app.features.form_builder.qtside.theme.runtime import host_form
from tests.form_builder.qtside.support import opened


def _role(name: str) -> object:
    palette = QApplication.palette()
    owner = getattr(type(palette), "ColorRole", type(palette))
    return getattr(owner, name)


def _color(widget: object, name: str) -> str:
    return widget.palette().color(_role(name)).name()  # type: ignore[attr-defined]


def main(argv: list[str] | None = None) -> int:
    path = (argv or sys.argv[1:])[0]
    text = open(path, encoding="utf-8").read()
    app = QApplication.instance() or QApplication([])
    with opened(text) as (session, realizer):
        root = realizer.root_widget
        label = realizer.widget_for(session.document.by_name("caption")[0])
        view = host_form(root)
        window = QMainWindow()
        window.setCentralWidget(view)
        window.show()
        app.processEvents()
        scene = view.scene()
        payload = {
            "scene_window": scene.palette().color(_role("Window")).name(),
            "scene_text": scene.palette().color(_role("WindowText")).name(),
            "label_window": _color(label, "Window"),
            "label_text": _color(label, "WindowText"),
            "root_window": _color(root, "Window"),
            "root_text": _color(root, "WindowText"),
        }
    json.dump(payload, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
