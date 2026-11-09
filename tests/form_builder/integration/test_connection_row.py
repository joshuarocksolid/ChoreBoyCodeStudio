# pyright: reportAttributeAccessIssue=false
"""Connections list: one subtitle, and a new SQLite row takes the file stem."""

from __future__ import annotations

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtWidgets import QPushButton

from app.features.form_builder.engine.data.connections import Connection, ConnectionSet
from app.features.form_builder.engine.data.connections_module import save_project_connections
from app.features.form_builder.integration.connection_paths import project_slug
from app.features.form_builder.integration.settings_ext import connections_page
from app.features.form_builder.integration.settings_ext.connections_page import (
    ConnectionsPage,
    connection_subtitle,
)

pytestmark = pytest.mark.unit


def test_connection_subtitle_is_the_target_without_a_separator() -> None:
    cases = (
        (Connection("sqlite", "SQLite", "sqlite"), ""),
        (Connection("sqlite", "SQLite", "sqlite", file="  "), ""),
        (Connection("sqlite", "SQLite", "sqlite", file="data/shop.db"), "data/shop.db"),
        (Connection("pg", "PostgreSQL", "postgres"), ""),
        (
            Connection("pg", "Office", "postgres", user="clerk", host="192.168.1.20", database="shop"),
            "clerk@192.168.1.20/shop",
        ),
        (
            Connection(
                "pg",
                "Office",
                "postgres",
                user="clerk",
                host="192.168.1.20",
                database="shop",
                port=5432,
            ),
            "clerk@192.168.1.20/shop",
        ),
        (
            Connection(
                "pg",
                "Office",
                "postgres",
                user="clerk",
                host="192.168.1.20",
                database="shop",
                port=5433,
            ),
            "clerk@192.168.1.20:5433/shop",
        ),
    )
    for connection, expected in cases:
        text = connection_subtitle(connection)
        assert text == expected
        assert "\u00b7" not in text


def test_empty_file_omits_the_second_line(qapp, tmp_path) -> None:
    del qapp
    page = ConnectionsPage(None, str(tmp_path))
    page.findChild(QPushButton, "formBuilder.connections.addSqlite").click()
    row = page._list.itemWidget(page._list.item(0))
    assert row.engine_label.isHidden() is True
    assert row.engine_label.text() == ""
    page._file.setText("data/shop.db")
    page._on_field()
    assert row.engine_label.isHidden() is False
    assert row.engine_label.text() == "data/shop.db"
    assert "\u00b7" not in row.engine_label.text()


def _choose(page: ConnectionsPage, path: str, monkeypatch) -> None:
    monkeypatch.setattr(
        connections_page.QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (path, ""),
    )
    page._choose.click()


def test_choose_file_names_a_default_connection_from_the_file_stem(qapp, tmp_path, monkeypatch) -> None:
    del qapp
    page = ConnectionsPage(None, str(tmp_path))
    page.findChild(QPushButton, "formBuilder.connections.addSqlite").click()
    _choose(page, str(tmp_path / "data" / "shop.db"), monkeypatch)
    assert page._title.text() == "shop"
    assert page._code.text() == "shop"
    row = page._list.itemWidget(page._list.item(0))
    assert row.title_label.text() == "shop"
    assert row.engine_label.text() == "data/shop.db"

    page._add_connection("sqlite")
    _choose(page, str(tmp_path / "data" / "shop.db"), monkeypatch)
    assert page._title.text() == "shop"
    assert page._code.text() == "shop_2"


def test_choose_file_leaves_a_name_the_user_typed(qapp, tmp_path, monkeypatch) -> None:
    del qapp
    page = ConnectionsPage(None, str(tmp_path))
    page.findChild(QPushButton, "formBuilder.connections.addSqlite").click()
    page._title.setText("Ledger")
    page._on_title("Ledger")
    _choose(page, str(tmp_path / "data" / "shop.db"), monkeypatch)
    assert page._title.text() == "Ledger"
    assert page._code.text() == "ledger"

    page._add_connection("sqlite")
    page._code.setText("custom")
    page._on_code_edited("custom")
    _choose(page, str(tmp_path / "data" / "shop.db"), monkeypatch)
    assert page._title.text() == "shop"
    assert page._code.text() == "custom"


def test_choose_file_leaves_a_saved_sqlite_name(qapp, tmp_path, monkeypatch) -> None:
    del qapp
    save_project_connections(
        str(tmp_path),
        ConnectionSet((Connection("sqlite", "SQLite", "sqlite", file="data/old.db"),)),
        slug=project_slug(str(tmp_path)),
    )
    page = ConnectionsPage(None, str(tmp_path))
    _choose(page, str(tmp_path / "data" / "shop.db"), monkeypatch)
    assert page._title.text() == "SQLite"
    assert page._code.text() == "sqlite"
