# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""The form-inspector group slot: a module in the editors package adds a group, nothing shared changes."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

import app.features.form_builder.qtside.inspector._properties as properties
from app.features.form_builder.engine.query.selection import SelectionSource
from app.qt.QtWidgets import QLabel, QWidget
from tests.form_builder.inspector.test_inspector_round2 import _close, _pane
from tests.form_builder.m5_0s_support import forget_package, make_package

pytestmark = [pytest.mark.usefixtures("qapp"), pytest.mark.unit]

_PACKAGE = "m5_form_group_probe"

_LOOK = """
    from app.qt.QtWidgets import QLabel

    SHOWN = []

    class Body:
        def __init__(self, host, parent):
            self.host = host
            self.widget = QLabel("look body", parent)

        def show(self, rows):
            SHOWN.append((rows, self.host.owners, self.host.document.root.object_name))

    def register_form_groups(registry):
        registry.add("look", "Look", Body, order=200)
        registry.add("code", "Code", Body, order=150)
        registry.add("never", "Never", Body, order=300, applies=lambda document: False)

    def register(registrar):
        pass
"""


@pytest.fixture()
def lane(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[object]:
    package = make_package(
        tmp_path, monkeypatch, _PACKAGE, {"look": _LOOK, "plain": "def register(registrar):\n    pass\n"}
    )
    monkeypatch.setattr(properties, "_FORM_GROUPS", properties.load_form_groups(package))
    yield package.look
    forget_package(_PACKAGE)


def test_a_registered_form_group_shows_on_the_form_in_order_and_not_on_a_widget(lane, qapp) -> None:  # type: ignore[no-untyped-def]
    window, pane, session, realizer = _pane(qapp)
    try:
        session.selection.clear(source=SelectionSource.PROGRAM)
        pane.flush()
        look = pane.findChild(QWidget, "formBuilder.formGroup.look")
        code = pane.findChild(QWidget, "formBuilder.formGroup.code")
        never = pane.findChild(QWidget, "formBuilder.formGroup.never")
        assert look.isVisibleTo(pane) and code.isVisibleTo(pane) and not never.isVisibleTo(pane)
        assert code.y() < look.y()
        rows, owners, root = lane.SHOWN[-1]
        assert rows == () and owners == (session.document.root.id,) and root == session.document.root.object_name
        assert pane.findChild(QLabel, "formBuilder.formCaption.files").y() < code.y()
        email = session.document.by_name("okButton")[0]
        session.selection.set((email,), source=SelectionSource.PROGRAM)
        pane.flush()
        assert not look.isVisibleTo(pane)
    finally:
        _close(window, pane, realizer, session, qapp)


def test_form_group_keys_are_unique() -> None:
    registry = properties.FormGroupRegistry()
    registry.add("a", "A", lambda host, parent: None)  # type: ignore[arg-type,return-value]
    with pytest.raises(ValueError):
        registry.add("a", "Again", lambda host, parent: None)  # type: ignore[arg-type,return-value]
