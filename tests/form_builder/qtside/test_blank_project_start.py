"""A blank project's untouched main.py can become the first form's start screen."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.project.start_screen import apply_start_screen
from app.project.project_service import create_blank_project
from app.qt.QtWidgets import QApplication, QCheckBox, QComboBox
from tests.form_builder.qtside.test_m8_7_followup import _dialog

pytestmark = pytest.mark.unit

_WINDOW = "InvoiceWindow"
_MODULE_FILE = Path("forms") / "invoice_window.py"


def test_blank_project_first_from_table_form_opens_on_start(
    tmp_path: Path, qapp: QApplication
) -> None:
    root = create_blank_project(tmp_path / "blank", project_name="Blank")
    _write_window(root)
    dialog = _dialog(tmp_path, root=root, stem="invoice")
    try:
        make = dialog.findChild(QComboBox, "formBuilder.fromTable.make")
        box = dialog.findChild(QCheckBox, "formBuilder.fromTable.start")
        assert make is not None and box is not None
        assert make.currentData() == "record"
        assert box.isEnabled()
        assert box.isChecked()
        assert dialog.wants_start_screen()
        apply_start_screen(str(root), dialog)
    finally:
        dialog.close()

    source = (root / "main.py").read_text(encoding="utf-8")
    assert "from forms.invoice_window import InvoiceWindow" in source
    assert "window = InvoiceWindow()" in source
    _show(root, source, qapp)


def test_edited_blank_main_stays_and_the_start_box_is_off(
    tmp_path: Path, qapp: QApplication
) -> None:
    del qapp
    root = create_blank_project(tmp_path / "blank", project_name="Blank")
    edited = (root / "main.py").read_text(encoding="utf-8") + "print('mine')\n"
    (root / "main.py").write_text(edited, encoding="utf-8")
    dialog = _dialog(tmp_path, root=root, stem="invoice")
    try:
        box = dialog.findChild(QCheckBox, "formBuilder.fromTable.start")
        assert box is not None
        assert not box.isEnabled()
        assert not box.isChecked()
        assert not dialog.wants_start_screen()
        apply_start_screen(str(root), dialog)
    finally:
        dialog.close()
    assert (root / "main.py").read_text(encoding="utf-8") == edited


def _write_window(root: Path) -> None:
    path = root / _MODULE_FILE
    path.parent.mkdir(parents=True)
    (path.parent / "__init__.py").write_text("", encoding="utf-8")
    path.write_text(
        "from app.qt.QtWidgets import QDialog\n"
        "\n"
        "class %s(QDialog):\n"
        "    def __init__(self) -> None:\n"
        "        super().__init__()\n"
        "        self.setObjectName('invoiceWindow')\n" % _WINDOW,
        encoding="utf-8",
    )


def _show(root: Path, source: str, qapp: QApplication) -> None:
    ext = Path(sys.executable).resolve().parents[1] / "Ext"
    if ext.is_dir():
        sys.path.insert(0, str(ext))
    sys.path.insert(0, str(root))
    stale = [key for key in sys.modules if key == "forms" or key.startswith("forms.")]
    for key in stale:
        del sys.modules[key]
    window = None
    try:
        namespace: Dict[str, Any] = {"__name__": "blank_entry"}
        exec(compile(source, str(root / "main.py"), "exec"), namespace)  # noqa: S102
        window = namespace[_WINDOW]()
        window.show()
        qapp.processEvents()
        visible = [
            item
            for item in qapp.topLevelWidgets()
            if item.isVisible() and type(item).__name__ == _WINDOW
        ]
        assert visible, [type(item).__name__ for item in qapp.topLevelWidgets() if item.isVisible()]
    finally:
        if window is not None:
            window.close()
        if sys.path and sys.path[0] == str(root):
            sys.path.pop(0)
