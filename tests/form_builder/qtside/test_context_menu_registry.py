"""Context-menu contributors (UX-CONT-020): sorted discovery, groups, and painted submenus."""

from __future__ import annotations

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
    load_menu_contributors,
)
from app.features.form_builder.qtside.theme.chrome import default_chrome
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
    paint_menu(menu, default_chrome())
    submenu = next(child for child in menu.findChildren(QMenu) if child.title() == "Alpha pages")
    assert submenu.styleSheet() == menu.styleSheet() != ""
