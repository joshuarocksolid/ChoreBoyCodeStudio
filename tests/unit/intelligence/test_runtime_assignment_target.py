"""Receiver types from simple assignments, for modules Jedi cannot read (PySide6 on FreeCAD 1.1)."""

from __future__ import annotations

import pytest

from app.intelligence.runtime_introspection import target_from_simple_assignment

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("from PySide import QtWidgets\nbtn = QtWidgets.QPushButton()\nbtn.", "PySide.QtWidgets.QPushButton"),
        ("from PySide.QtWidgets import QPushButton\nbtn = QPushButton('Go')\nbtn.", "PySide.QtWidgets.QPushButton"),
        ("import PySide6.QtWidgets as W\nbtn = W.QLabel()\nbtn.", "PySide6.QtWidgets.QLabel"),
        ("from PySide import QtWidgets\nbtn = QtWidgets.QPushButton()\nbtn = make()\nbtn.", ""),
        ("import os\nbtn = os.path.join('a')\nbtn.", ""),
    ],
)
def test_assignment_resolves_through_imports(source: str, expected: str) -> None:
    assert target_from_simple_assignment(source, "btn", len(source)) == expected
