# pyright: reportAttributeAccessIssue=false
"""Exit path for a main window that still has a form open.

The parent test asserts the process status and that each surface released.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from app.features.form_builder.engine.commands.catalog import SetProperty
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.integration.surface import FormSurface
from app.qt.QtCore import QPoint, Qt, QTimer
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QPushButton, QWidget
from app.shell.main_window import MainWindow
from testing.main_window_shutdown import shutdown_main_window_for_test

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>280</height></rect></property>
  <widget class="QPushButton" name="okButton">
   <property name="geometry"><rect><x>40</x><y>40</y><width>80</width><height>28</height></rect></property>
   <property name="text"><string>OK</string></property>
  </widget>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _arm_discard(app: QApplication) -> dict:
    seen = {"clicked": False}
    pending = {"left": 40}

    def click() -> None:
        for widget in app.allWidgets():
            if isinstance(widget, QPushButton) and widget.isVisible() and "Discard" in widget.text():
                seen["clicked"] = True
                widget.click()
                return
        pending["left"] -= 1
        if pending["left"] > 0:
            QTimer.singleShot(50, click)

    QTimer.singleShot(0, click)
    return seen


def _open(window: MainWindow, app: QApplication, path: Path) -> object:
    path.write_text(_FORM, encoding="utf-8")
    assert window._editor_tab_factory.open_file_in_editor(str(path))  # noqa: SLF001
    stack = window._center_stack  # noqa: SLF001
    assert stack is not None
    stack.setCurrentIndex(1)
    window.resize(1400, 900)
    window.show()
    app.processEvents()
    surface = window._tab_content_registry.surface_for_path(str(path))  # noqa: SLF001
    assert surface is not None
    return surface


def _dirty(surface: object) -> None:
    session = surface.session  # type: ignore[attr-defined]
    button = session.document.by_name("okButton")[0]
    session.log.execute(SetProperty(button, "text", StringValue("Changed")))


def _editor(surface: object, app: QApplication) -> None:
    canvas = surface.findChild(QWidget, "formBuilder.canvas")  # type: ignore[attr-defined]
    assert canvas is not None
    root = canvas.page_widget()
    button = root.findChild(QWidget, "okButton")
    assert root is not None and button is not None
    center = button.mapTo(root, button.rect().center())
    proxy = root.graphicsProxyWidget()
    assert proxy is not None
    port = canvas.mapFromScene(proxy.mapToScene(QPoint(center.x(), center.y())))
    QTest.mouseClick(canvas.viewport(), Qt.LeftButton, Qt.NoModifier, port)
    app.processEvents()
    canvas.setFocus()
    QTest.keyClick(canvas, Qt.Key_Return)
    app.processEvents()
    QTest.keyClick(canvas, Qt.Key_D, Qt.ControlModifier)
    app.processEvents()


def _patch_release(log_path: str) -> None:
    original = FormSurface.release

    def release(self: FormSurface) -> None:
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(getattr(self, "_path", "") + "\n")
        original(self)

    FormSurface.release = release  # type: ignore[method-assign]


def main(argv: list[str] | None = None) -> int:
    args = list(argv or sys.argv[1:])
    scenario = args[0]
    root = Path(args[1])
    log_path = args[2]
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("CBCS_DISABLE_BACKGROUND_RUNTIME", "1")
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    _patch_release(log_path)
    window = MainWindow(state_root=str((root / "state").resolve()))
    first = _open(window, app, root / "one.ui")
    if scenario == "discard":
        _open(window, app, root / "two.ui")
        _dirty(first)
    elif scenario == "editor":
        _editor(first, app)
        _dirty(first)
    seen = _arm_discard(app)
    window.close()
    app.processEvents()
    if scenario in ("discard", "editor"):
        text = (root / "one.ui").read_text(encoding="utf-8")
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write("discard-seen\n" if seen["clicked"] else "discard-missed\n")
            handle.write("dirty-gone\n" if "Changed" not in text else "dirty-kept\n")
    shutdown_main_window_for_test(window, app)
    return 0


if __name__ == "__main__":
    sys.exit(main())
