# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""Context-menu contributors (UX-CONT-020): sorted discovery, groups, and painted submenus."""

from __future__ import annotations

import logging
import sys
import textwrap
from pathlib import Path
from typing import List

import pytest

from app.features.form_builder.engine.layout_actions import OfferSheet
from app.features.form_builder.integration.context_menu import build_context_menu, paint_menu
from app.features.form_builder.integration.menu_ext import (
    FIRST,
    GROUPS,
    LAST,
    STRUCTURE,
    MenuContext,
    MenuRegistry,
    load_menu_contributors,
)
from app.features.form_builder.qtside.theme.chrome import default_chrome
from app.qt.QtCore import QPoint  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtWidgets import QMenu

pytestmark = [pytest.mark.usefixtures("qapp"), pytest.mark.unit]

_PACKAGE = "cm_probe_pkg"


def _module(name: str, body: str) -> str:
    return textwrap.dedent(body).replace("__NAME__", name)


@pytest.fixture()
def probe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """A temporary package with contributors. The file names decide the order, not the write order."""
    root = tmp_path / _PACKAGE
    root.mkdir()
    (root / "__init__.py").write_text("", encoding="utf-8")
    (root / "zeta_last.py").write_text(
        _module(
            "zeta",
            """
            def register(registry):
                registry.add("last", lambda ctx: ctx.menu.addAction("Zeta last row"))
            """,
        ),
        encoding="utf-8",
    )
    (root / "alpha_first.py").write_text(
        _module(
            "alpha",
            """
            def register(registry):
                registry.add("first", lambda ctx: ctx.menu.addAction("Alpha first row"))
                registry.add("structure", _submenu)

            def _submenu(ctx):
                sub = ctx.menu.addMenu("Alpha pages")
                sub.addAction("Alpha page row")
            """,
        ),
        encoding="utf-8",
    )
    (root / "beta_first.py").write_text(
        _module(
            "beta",
            """
            def register(registry):
                registry.add("first", lambda ctx: ctx.menu.addAction("Beta first row"))
            """,
        ),
        encoding="utf-8",
    )
    (root / "_helper.py").write_text("raise RuntimeError('helpers are not imported')\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    module = __import__(_PACKAGE)
    yield module
    for name in list(sys.modules):
        if name == _PACKAGE or name.startswith(_PACKAGE + "."):
            del sys.modules[name]


def _texts(menu: QMenu) -> List[str]:
    return [action.text().split("\t")[0] for action in menu.actions() if not action.isSeparator()]


def _empty_sheet() -> OfferSheet:
    return OfferSheet(offers={}, current_kind=None, morphs=())


def test_groups_are_the_three_documented_ones() -> None:
    assert GROUPS == (FIRST, STRUCTURE, LAST)


def test_modules_register_in_sorted_name_order_into_their_groups(probe: object) -> None:
    registry = load_menu_contributors(probe)  # type: ignore[arg-type]
    menu = QMenu()
    context = MenuContext(menu=menu, ids=(), current=None, session=None, dispatch=lambda _id: None)  # type: ignore[arg-type]
    assert registry.run(FIRST, context) == 2
    assert _texts(menu) == ["Alpha first row", "Beta first row"]
    assert registry.run(LAST, context) == 1
    assert _texts(menu)[-1] == "Zeta last row"


def test_a_contributor_outside_a_known_group_is_refused(probe: object) -> None:
    registry = load_menu_contributors(probe)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        registry.add("middle", lambda ctx: None)


def test_full_menu_orders_groups_and_paints_the_contributed_submenu(probe: object) -> None:
    registry = load_menu_contributors(probe)  # type: ignore[arg-type]
    menu = QMenu()
    seen: List[str] = []
    build_context_menu(
        menu,
        contributors=registry,
        ids=(),
        current=None,
        session=None,  # type: ignore[arg-type]
        dispatch=seen.append,
        enabled=None,
        sheet=_empty_sheet(),
        run=lambda request: None,
    )
    texts = _texts(menu)
    first = texts.index("Alpha first row")
    clipboard = texts.index("Copy")
    structure = texts.index("Alpha pages")
    layout = texts.index("Remove layout…")
    assert first < texts.index("Beta first row") < clipboard < structure < layout
    assert texts[-1] == "Zeta last row"
    actions = menu.actions()
    follow = actions[actions.index(next(action for action in actions if action.text() == "Alpha pages")) + 1]
    assert not follow.isSeparator()
    assert follow.text().split("\t")[0] == "Remove layout…"
    paint_menu(menu, default_chrome())
    submenu = next(child for child in menu.findChildren(QMenu) if child.title() == "Alpha pages")
    assert submenu.styleSheet() == menu.styleSheet() != ""


def test_a_failing_contributor_does_not_drop_the_rest(caplog: pytest.LogCaptureFixture) -> None:
    registry = MenuRegistry()

    def bad(ctx: MenuContext) -> None:
        del ctx
        raise RuntimeError("bad contributor")

    def good(ctx: MenuContext) -> None:
        ctx.menu.addAction("Still here")

    registry.add(FIRST, bad)
    registry.add(FIRST, good)
    menu = QMenu()
    context = MenuContext(menu=menu, ids=(), current=None, session=None, dispatch=lambda _command: None)  # type: ignore[arg-type]
    with caplog.at_level(logging.ERROR):
        assert registry.run(FIRST, context) == 1
    assert _texts(menu) == ["Still here"]
    assert "bad contributor" in caplog.text


def test_context_carries_the_click_the_source_the_widget_and_the_command() -> None:
    seen: dict = {}
    registry = MenuRegistry()

    def build(ctx: MenuContext) -> None:
        seen["at"] = ctx.at
        seen["source"] = ctx.source
        seen["live"] = ctx.live(1)  # type: ignore[arg-type]
        ctx.run("layout-command")
        ctx.menu.addAction("Pages")

    registry.add(STRUCTURE, build)
    menu = QMenu()
    point = QPoint(3, 4)
    build_context_menu(
        menu,
        contributors=registry,
        ids=(),
        current=None,
        session=None,  # type: ignore[arg-type]
        dispatch=lambda _command: None,
        enabled=None,
        sheet=_empty_sheet(),
        run=lambda command: seen.setdefault("ran", command),
        at=point,
        source="outline",
        live=lambda node_id: node_id,  # type: ignore[arg-type, return-value]
    )
    assert seen["source"] == "outline"
    assert seen["at"] == point
    assert seen["live"] == 1
    assert seen["ran"] == "layout-command"
