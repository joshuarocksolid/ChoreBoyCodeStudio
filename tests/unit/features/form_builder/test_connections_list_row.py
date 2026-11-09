# pyright: reportAttributeAccessIssue=false
"""Connections list rows show one block, and a default SQLite name follows the file."""

from __future__ import annotations

from typing import Tuple

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtWidgets import QLabel, QLineEdit, QPushButton

from app.features.form_builder.engine.data.connections import Connection
from app.features.form_builder.integration.settings_ext import connections_page
from app.features.form_builder.integration.settings_ext.connections_page import (
    ConnectionsPage,
    connection_detail,
)

pytestmark = pytest.mark.unit


def _choose(page: ConnectionsPage, monkeypatch: pytest.MonkeyPatch, path: str) -> None:
    monkeypatch.setattr(
        connections_page.QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (path, ""),
    )
    button = page.findChild(QPushButton, "formBuilder.connections.choose")
    assert button is not None
    button.click()


def _editor(page: ConnectionsPage) -> Tuple[QLineEdit, QLineEdit]:
    title = page.findChild(QLineEdit, "formBuilder.connections.title")
    code = page.findChild(QLineEdit, "formBuilder.connections.code")
    assert isinstance(title, QLineEdit)
    assert isinstance(code, QLineEdit)
    return title, code


@pytest.mark.parametrize(
    ("connection", "expected"),
    [
        (Connection("sqlite", "SQLite", "sqlite"), ""),
        (Connection("sqlite", "SQLite", "sqlite", file="   "), ""),
        (Connection("shop", "shop", "sqlite", file="data/shop.db"), "data/shop.db"),
        (Connection("office", "Office", "postgres"), ""),
        (
            Connection(
                "office",
                "Office",
                "postgres",
                host="192.168.1.20",
                database="shop",
                user="clerk",
                port=5432,
            ),
            "clerk@192.168.1.20/shop",
        ),
        (
            Connection(
                "office",
                "Office",
                "postgres",
                host="192.168.1.20",
                database="shop",
                user="clerk",
                port=5433,
            ),
            "clerk@192.168.1.20:5433/shop",
        ),
    ],
)
def test_connection_detail_is_the_target_without_a_separator(
    connection: Connection, expected: str
) -> None:
    assert connection_detail(connection) == expected


def test_a_new_sqlite_row_omits_the_empty_detail(qapp: object, tmp_path) -> None:  # type: ignore[no-untyped-def]
    del qapp
    page = ConnectionsPage(None, str(tmp_path))
    added = page.findChild(QPushButton, "formBuilder.connections.addSqlite")
    assert added is not None
    added.click()
    detail = page.findChild(QLabel, "formBuilder.connections.engine")
    assert detail is not None
    assert detail.isHidden()
    assert detail.text() == ""
    titles = page.findChildren(QLabel, "formBuilder.connections.rowTitle")
    assert [label.text() for label in titles] == ["SQLite"]


def test_choosing_a_file_names_a_default_sqlite_connection_from_the_stem(
    qapp: object, tmp_path, monkeypatch: pytest.MonkeyPatch  # type: ignore[no-untyped-def]
) -> None:
    del qapp
    page = ConnectionsPage(None, str(tmp_path))
    added = page.findChild(QPushButton, "formBuilder.connections.addSqlite")
    assert added is not None
    added.click()
    _choose(page, monkeypatch, str(tmp_path / "shop.db"))
    title, code = _editor(page)
    detail = page.findChild(QLabel, "formBuilder.connections.engine")
    assert detail is not None
    assert title.text() == "shop"
    assert code.text() == "shop"
    assert detail.isHidden() is False
    assert detail.text() == "shop.db"


def test_choosing_a_file_keeps_a_name_the_user_typed(
    qapp: object, tmp_path, monkeypatch: pytest.MonkeyPatch  # type: ignore[no-untyped-def]
) -> None:
    del qapp
    page = ConnectionsPage(None, str(tmp_path))
    added = page.findChild(QPushButton, "formBuilder.connections.addSqlite")
    assert added is not None
    added.click()
    title, code = _editor(page)
    title.setText("Ledger")
    title.textEdited.emit("Ledger")
    _choose(page, monkeypatch, str(tmp_path / "shop.db"))
    assert title.text() == "Ledger"
    assert code.text() == "ledger"


def test_choosing_a_file_keeps_a_code_the_user_typed(
    qapp: object, tmp_path, monkeypatch: pytest.MonkeyPatch  # type: ignore[no-untyped-def]
) -> None:
    del qapp
    page = ConnectionsPage(None, str(tmp_path))
    added = page.findChild(QPushButton, "formBuilder.connections.addSqlite")
    assert added is not None
    added.click()
    title, code = _editor(page)
    code.setText("ledger")
    code.textEdited.emit("ledger")
    _choose(page, monkeypatch, str(tmp_path / "shop.db"))
    assert title.text() == "shop"
    assert code.text() == "ledger"


def test_a_second_default_sqlite_file_keeps_the_code_unique(
    qapp: object, tmp_path, monkeypatch: pytest.MonkeyPatch  # type: ignore[no-untyped-def]
) -> None:
    del qapp
    page = ConnectionsPage(None, str(tmp_path))
    added = page.findChild(QPushButton, "formBuilder.connections.addSqlite")
    assert added is not None
    added.click()
    _choose(page, monkeypatch, str(tmp_path / "shop.db"))
    added.click()
    data = tmp_path / "data"
    data.mkdir()
    _choose(page, monkeypatch, str(data / "shop.db"))
    assert page.commit(str(tmp_path)) is None
    written = (tmp_path / "connections.json").read_text(encoding="utf-8")
    assert '"name": "shop"' in written
    assert '"name": "shop_2"' in written
