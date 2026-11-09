"""Ctrl+R: a feature tab can claim Go to Symbol; a code tab still gets it."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, List

from app.shell.symbol_navigation_workflow import SymbolNavigationWorkflow


class _Host:
    def __init__(self, parent: Any, path: str) -> None:
        self._parent = parent
        self._tab = SimpleNamespace(file_path=path, current_content="def f():\n    pass\n")
        self.outline_requests: List[str] = []

    def dialog_parent(self) -> Any:
        return self._parent

    def editor_manager(self) -> Any:
        return SimpleNamespace(active_tab=lambda: self._tab)

    def editor_widget_for_path(self, _path: str) -> None:
        return None

    def request_flat_outline_symbols_async(self, file_path: str, **_kwargs: Any) -> None:
        self.outline_requests.append(file_path)


def test_a_code_tab_still_reaches_go_to_symbol(tmp_path: Path) -> None:
    path = str(tmp_path / "mod.py")
    host = _Host(SimpleNamespace(_form_builder_go_to_widget=lambda: False), path)
    SymbolNavigationWorkflow(host).handle_goto_symbol_in_file_action()  # type: ignore[arg-type]
    assert host.outline_requests == [path]


def test_a_form_tab_takes_the_key_before_go_to_symbol(tmp_path: Path) -> None:
    host = _Host(SimpleNamespace(_form_builder_go_to_widget=lambda: True), str(tmp_path / "a.ui"))
    SymbolNavigationWorkflow(host).handle_goto_symbol_in_file_action()  # type: ignore[arg-type]
    assert host.outline_requests == []
