from pathlib import Path

import pytest

from tools.dune.qt_portability import find_qt_portability_violations
from tools.qt_codemod import rewrite_source

pytestmark = pytest.mark.unit


def _violations(tmp_path: Path, relative_path: str, source: str) -> list[str]:
    path = tmp_path / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return find_qt_portability_violations(tmp_path, [relative_path])


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("from PySide2.QtWidgets import QLabel\n", "import PySide2.QtWidgets through app.qt"),
        ("import PySide6.QtGui as gui\n", "import PySide6.QtGui through app.qt"),
        ("dialog.exec_()\n", "call exec_qt(obj, ...) instead of .exec_()"),
        (
            "key | int(event.modifiers())\n",
            "int() on this Qt enum raises TypeError on PySide6; use enum_value()",
        ),
        (
            "int(Qt.ControlModifier)\n",
            "int() on this Qt enum raises TypeError on PySide6; use enum_value()",
        ),
        ("combo.activated[str].connect(f)\n", "activated[str] is gone in Qt 6; use the text* signal or [int]"),
        ("from app.qt.QtCore import QRegExp\n", "QRegExp is gone in Qt 6; use QRegularExpression"),
        ("QPalette.Background\n", "QPalette.Background is gone in Qt 6; use Window/WindowText"),
        (
            "fmt.setFontWeight(75)\n",
            "numeric font weights differ between Qt 5 (0-99) and Qt 6 (1-1000); use QFont.Bold etc.",
        ),
    ],
)
def test_qt_portability_flags_planted_hazard(tmp_path: Path, source: str, expected: str) -> None:
    assert _violations(tmp_path, "app/shell/widget.py", source) == [
        "qt-portability: app/shell/widget.py:1: " + expected
    ]


def test_qt_portability_allows_portable_code_and_the_qt_package(tmp_path: Path) -> None:
    portable = (
        "from app.qt.QtCore import Qt\n"
        "from app.qt.qt_compat import enum_value, exec_qt\n"
        "flags = int(Qt.AlignCenter)\n"
        "combo.activated[int].connect(f)\n"
        "exec_qt(dialog)\n"
    )
    assert _violations(tmp_path, "app/shell/widget.py", portable) == []
    assert _violations(tmp_path, "app/qt/QtCore.py", "from PySide2.QtCore import *\n") == []


def test_qt_codemod_rewrites_imports_and_exec_calls() -> None:
    source = (
        '"""Doc."""\n'
        "from __future__ import annotations\n"
        "\n"
        "import importlib\n"
        "from PySide2.QtWidgets import (\n"
        "    QDialog,  # dialog\n"
        "    QMenu,\n"
        ")\n"
        "import PySide2.QtGui as qt_gui  # noqa: E402\n"
        "\n"
        "\n"
        "def run(menu, point):\n"
        '    widgets = importlib.import_module("PySide2.QtWidgets")\n'
        "    menu.exec_(point)\n"
        "    return QDialog().exec_()\n"
    )

    rewritten, notes = rewrite_source(source)

    assert notes == []
    assert rewritten == (
        '"""Doc."""\n'
        "from __future__ import annotations\n"
        "\n"
        "import importlib\n"
        "from app.qt.QtWidgets import (\n"
        "    QDialog,  # dialog\n"
        "    QMenu,\n"
        ")\n"
        "from app.qt import QtGui as qt_gui  # noqa: E402\n"
        "from app.qt.qt_compat import exec_qt\n"
        "\n"
        "\n"
        "def run(menu, point):\n"
        '    widgets = importlib.import_module("app.qt.QtWidgets")\n'
        "    exec_qt(menu, point)\n"
        "    return exec_qt(QDialog())\n"
    )
    assert rewrite_source(rewritten)[0] == rewritten
