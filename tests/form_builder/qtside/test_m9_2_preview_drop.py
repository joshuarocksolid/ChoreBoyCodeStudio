# pyright: reportAttributeAccessIssue=false
"""Dropping a preview keeps a replacement module and waits out a nested loop."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import pytest

from app.features.form_builder.qtside.preview.child.session import _View, _drop_view
from app.qt.QtCore import QThread
from app.qt.QtWidgets import QWidget

pytestmark = pytest.mark.unit


def _alive(widget: QWidget) -> bool:
    try:
        import shiboken6 as shiboken
    except ImportError:
        import shiboken2 as shiboken  # type: ignore[no-redef]
    return bool(shiboken.isValid(widget))


def test_dropping_a_view_leaves_the_module_that_replaced_it(qapp: object) -> None:
    del qapp
    name = "cbcs_preview_replaced_form"
    old = types.ModuleType(name)
    old.__file__ = "<%s>" % name
    new = types.ModuleType(name)
    new.__file__ = "<%s>" % name
    sys.modules[name] = new
    widget = QWidget()
    try:
        _drop_view(_View(widget, 1, 1.0, name, old))
        assert sys.modules.get(name) is new
    finally:
        sys.modules.pop(name, None)


def test_a_nested_loop_defers_the_preview_delete(qapp: object, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(QThread, "currentThread", staticmethod(lambda: SimpleNamespace(loopLevel=lambda: 2)))
    widget = QWidget()
    _drop_view(_View(widget, 1, 1.0))
    assert _alive(widget)
    widget.deleteLater()
    qapp.processEvents()  # type: ignore[attr-defined]


def test_a_top_loop_deletes_the_preview_now(qapp: object, monkeypatch: pytest.MonkeyPatch) -> None:
    del qapp
    monkeypatch.setattr(QThread, "currentThread", staticmethod(lambda: SimpleNamespace(loopLevel=lambda: 1)))
    widget = QWidget()
    _drop_view(_View(widget, 1, 1.0))
    assert not _alive(widget)
