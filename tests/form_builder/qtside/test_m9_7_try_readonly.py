"""Would-run starts read-only, and a rolled-back save puts the form key back."""

from __future__ import annotations

import types
from typing import Any, List, Optional

import pytest

from app.features.form_builder.engine.ipc.protocol import TryConnectionSpec, TryDataPlan, TryStart
from app.features.form_builder.qtside.preview.child.try_connections import (
    _begin_read_only,
    begin_try,
    bind_form_class,
    end_all,
)


class _Cell:
    def __init__(self, text: str) -> None:
        self.text = text

    def clone(self) -> "_Cell":
        return _Cell(self.text)


class _Model:
    def __init__(self, text: str) -> None:
        self.rows: List[List[_Cell]] = [[_Cell(text)]]
        self.blocked: List[bool] = []

    def rowCount(self) -> int:
        return len(self.rows)

    def columnCount(self) -> int:
        return 1 if self.rows else 0

    def item(self, row: int, column: int) -> _Cell:
        return self.rows[row][column]

    def removeRows(self, start: int, count: int) -> None:
        del self.rows[start : start + count]

    def appendRow(self, cells: List[_Cell]) -> None:
        self.rows.append(list(cells))

    def blockSignals(self, blocked: bool) -> None:
        self.blocked.append(blocked)


class _View:
    def __init__(self, model: _Model) -> None:
        self._model = model

    def model(self) -> _Model:
        return self._model


def _driver_type(module_name: str) -> type:
    module = types.ModuleType(module_name)
    source = (
        "class Driver:\n"
        "    def __init__(self):\n"
        "        self.statements = []\n"
        "        self._in_transaction = False\n"
        "        self.autocommit = False\n"
        "        self.simple = []\n"
        "    def execute_simple(self, sql):\n"
        "        self.simple.append(sql)\n"
        "        self.statements.append(sql)\n"
        "    def cursor(self):\n"
        "        return self\n"
        "    def execute(self, sql, params=None):\n"
        "        if not self._in_transaction and not self.autocommit:\n"
        "            self.statements.append('BEGIN')\n"
        "            self._in_transaction = True\n"
        "        self.statements.append(sql)\n"
    )
    exec(source, module.__dict__)  # noqa: S102
    return module.Driver  # type: ignore[attr-defined]


@pytest.mark.unit
def test_begin_read_only_is_the_first_statement_after_the_driver_begin() -> None:
    driver = _driver_type("psycopg.connection")()
    _begin_read_only(driver)
    assert driver.statements == ["BEGIN", "SET TRANSACTION READ ONLY"]
    assert driver.simple == []


@pytest.mark.unit
def test_pg8000_already_in_a_transaction_still_sets_read_only() -> None:
    driver = _driver_type("pg8000.dbapi")()
    driver._in_transaction = True
    _begin_read_only(driver)
    assert driver.statements == ["SET TRANSACTION READ ONLY"]
    assert driver.simple == []


def _save(self: Any) -> bool:
    self._cbcs_new = False
    self._cbcs_keys = [1, 7]
    self._cbcs_index = 1
    self._cbcs_key = 7
    self._cbcs_line_snapshot = ({"id": 7, "note": "phantom"},)
    self._cbcs_deleted_line_keys = []
    model = self.lines.model()
    model.removeRows(0, model.rowCount())
    model.appendRow([_Cell("phantom")])
    return self._result


def _record_class() -> type:
    """A new class each test. bind_form_class wraps methods defined on that class."""

    class Record:
        def __init__(self) -> None:
            self._cbcs_new = True
            self._cbcs_keys = [1]
            self._cbcs_index = -1
            self._cbcs_loaded = {"note": "old"}
            self._cbcs_saved_fields = {"note": "old"}
            self._cbcs_key = None  # type: Optional[int]
            self._cbcs_line_snapshot = ({"id": 1, "note": "old"},)
            self._cbcs_deleted_line_keys = [4]
            self._cbcs_line_view = "lines"
            self.lines = _View(_Model("old"))
            self._result = True

        cbcs_save = _save

    return Record


def _rollback(view: str) -> None:
    spec = TryConnectionSpec(name="shop", mode="rollback", engine="sqlite", title="Shop")
    begin_try(
        TryStart(
            request_id="t",
            view_id=view,
            module_name="ui_form",
            module_source="pass\n",
            window_class_name="Window",
            base_class="QDialog",
            window_values=(),
            data=TryDataPlan(specs=(spec,)),
        )
    )


def _saved(form: Any) -> str:
    return form.lines.model().item(0, 0).text


@pytest.mark.unit
def test_rolled_back_save_puts_back_the_key_snapshot_and_line_model() -> None:
    _rollback("m97-rollback")
    try:
        record_cls = _record_class()
        bind_form_class(record_cls, "m97-rollback")
        form = record_cls()
        assert form.cbcs_save() is True
        assert form._cbcs_new is True
        assert form._cbcs_keys == [1]
        assert form._cbcs_index == -1
        assert form._cbcs_key is None
        assert form._cbcs_line_snapshot == ({"id": 1, "note": "old"},)
        assert form._cbcs_deleted_line_keys == [4]
        assert _saved(form) == "old"
    finally:
        end_all()


@pytest.mark.unit
def test_failed_save_puts_back_a_key_it_already_wrote() -> None:
    record_cls = _record_class()
    bind_form_class(record_cls, "m97-failed")
    form = record_cls()
    form._result = False
    assert form.cbcs_save() is False
    assert form._cbcs_key is None
    assert form._cbcs_line_snapshot == ({"id": 1, "note": "old"},)
    assert form._cbcs_deleted_line_keys == [4]
    assert _saved(form) == "old"


@pytest.mark.unit
def test_sticking_save_keeps_the_new_key() -> None:
    record_cls = _record_class()
    bind_form_class(record_cls, "m97-stick")
    form = record_cls()
    assert form.cbcs_save() is True
    assert form._cbcs_key == 7
    assert form._cbcs_line_snapshot == ({"id": 7, "note": "phantom"},)
    assert _saved(form) == "phantom"
