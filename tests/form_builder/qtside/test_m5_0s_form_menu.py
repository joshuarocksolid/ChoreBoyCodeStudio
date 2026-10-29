# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""UX-M5-010: the Form menu order comes from the contributor registry."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator, List

import pytest

from app.features.form_builder.integration.form_menu import register_form_menu
from app.features.form_builder.integration.form_menu_ext import (
    FormMenuItem,
    FormMenuRegistry,
    MenuEntry,
    load_form_menu_contributors,
    plan_menu,
)
from app.qt.QtWidgets import QMenu, QMenuBar, QWidget
from app.shell.menus import build_menu_stubs, clear_menu_contributors
from tests.form_builder.m5_0s_support import forget_package, make_package
from tests.unit.features.form_builder.test_workbench import _FORM, _open

pytestmark = [pytest.mark.usefixtures("qapp"), pytest.mark.unit]

_PACKAGE = "m5_form_menu_probe"

#: The lanes' items as UX-M5-010 names them, one stand-in file each.
_LANES = {
    "main_window": """
        from app.features.form_builder.integration.form_menu_ext import FormMenuItem
        SHOWN = [False]
        def register(registry):
            registry.add(FormMenuItem("probe.addToolbar", ("Main window", "Add toolbar"), lambda s: None,
                                      offered=lambda s: SHOWN[0]))
    """,
    "modes": """
        from app.features.form_builder.integration.form_menu_ext import FormMenuItem
        def register(registry):
            registry.add(FormMenuItem("probe.tabOrderList", ("Overlays", "Tab order list…"), lambda s: None))
            registry.add(FormMenuItem("probe.designerKeys", ("Form designer keys",), lambda s: None, target="help"))
    """,
    "preview": """
        from app.features.form_builder.integration.form_menu_ext import FormMenuItem
        def register(registry):
            for title, path in (("Python", ("View Python code",)), ("Image", ("Save image…",)),
                                ("Print", ("Print…",)),
                                ("Style", ("Preview options", "Style", "Fusion")),
                                ("Screen", ("Preview options", "Screen", "Small"))):
                registry.add(FormMenuItem("probe." + title, path, lambda s: None))
    """,
    "style": """
        from app.features.form_builder.integration.form_menu_ext import FormMenuItem
        def register(registry):
            registry.add(FormMenuItem("probe.style", ("Style sheet of the form…",), lambda s: None))
    """,
    "form_settings": """
        from app.features.form_builder.integration.form_menu_ext import FormMenuItem
        def register(registry):
            registry.add(FormMenuItem("form.action.formSettings", ("Form settings…",), lambda s: None))
    """,
    "templates": """
        from app.features.form_builder.integration.form_menu_ext import FormMenuItem
        def register(registry):
            registry.add(FormMenuItem("probe.template", ("Save as template…",), lambda s: None))
    """,
}


@pytest.fixture()
def lanes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[object]:
    yield make_package(tmp_path, monkeypatch, _PACKAGE, _LANES)
    forget_package(_PACKAGE)


def _entry(path: tuple, rank: int = 1000, module: str = "") -> MenuEntry:
    return MenuEntry(path, rank, module, None)


def test_plan_orders_the_titles_whatever_order_they_were_added_in() -> None:
    titles = [
        "Create window class…", "Print…", "Save image…", "Save as template…",
        "Form settings…", "Style sheet of the form…", "View XML", "View Python code",
        "Preview options", "Preview", "Overlays", "Main window", "Size", "Layout", "Go to widget…",
        "Insert widget…",
    ]
    nodes = plan_menu([_entry((title,)) for title in titles])
    assert [node.title or "-" for node in nodes] == [
        "Insert widget…", "Go to widget…", "Layout", "Size", "Main window", "Overlays",
        "-", "Preview", "Preview options", "View Python code", "View XML",
        "-", "Style sheet of the form…", "Form settings…", "Save as template…",
        "Save image…", "Print…", "Create window class…",
    ]


def test_plan_sorts_a_submenu_by_rank_then_module_then_registration() -> None:
    nodes = plan_menu(
        [
            _entry(("Overlays", "late"), module="b"),
            _entry(("Overlays", "early"), rank=5, module="z"),
            _entry(("Overlays", "tie second"), module="b"),
            _entry(("Overlays", "tie first"), module="a"),
        ]
    )
    assert [child.title for child in nodes[0].children] == ["early", "tie first", "late", "tie second"]


def test_the_form_menu_has_the_m5_order_and_leaves_out_what_the_runtime_cannot_offer(  # type: ignore[no-untyped-def]
    lanes, tmp_path: Path, qapp
) -> None:
    surface = _open(QWidget(), _FORM, tmp_path / "invoice.ui")

    class _Tab:
        file_path = surface.form_path()

    class _Manager:
        def active_tab(self) -> _Tab:
            return _Tab()

    class _Registry:
        def surface_for_path(self, _path: str) -> object:
            return surface

    window = QWidget()
    window._editor_manager = _Manager()
    window._tab_content_registry = _Registry()
    registry = load_form_menu_contributors(lanes)
    register_form_menu(window, registry)
    bar = QMenuBar(window)
    try:
        stubs = build_menu_stubs(bar)
        form = stubs.menus["formBuilder.menu"]

        def shown(menu: QMenu) -> List[str]:
            return [
                "-" if action.isSeparator() else action.text().split("\t")[0].replace("&", "")
                for action in menu.actions()
                if action.isVisible()
            ]

        top = shown(form)
        wanted = [
            "Insert widget…", "Go to widget…", "Layout", "Size", "Overlays", "-",
            "Preview", "Preview options", "View Python code", "View XML", "-",
            "Style sheet of the form…", "Form settings…", "Save as template…",
            "Save image…", "Print…", "Create window class…",
        ]
        assert top[: len(wanted)] == wanted
        assert "Main window" not in top
        overlays = form.findChild(QMenu, "formBuilder.menu.Overlays")
        assert shown(overlays)[-1] == "Tab order list…"
        options = form.findChild(QMenu, "formBuilder.menu.Preview options")
        assert shown(options)[-2:] == ["Style", "Screen"]
        # The table's Form settings row is replaced, not doubled.
        assert top.count("Form settings…") == 1
        assert stubs.actions["form.action.formSettings"].isEnabled()
        # Help gains its item once the shell has built Help.
        qapp.processEvents()
        help_menu = stubs.menus["shell.menu.help"]
        assert "Form designer keys" in shown(help_menu)

        lanes.main_window.SHOWN[0] = True
        form.aboutToShow.emit()
        assert shown(form).index("Main window") == shown(form).index("Size") + 1
    finally:
        clear_menu_contributors()
        surface.release()
        window.deleteLater()


def test_a_broken_contributor_is_skipped_and_a_repeated_id_is_refused(  # type: ignore[no-untyped-def]
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = make_package(
        tmp_path, monkeypatch, "m5_form_menu_broken", {"a_bad": "raise RuntimeError('lane bug')\n", "b_ok": _LANES["style"]}
    )
    try:
        registry = load_form_menu_contributors(package)
        assert [item.command_id for _module, item in registry.items()] == ["probe.style"]
        with pytest.raises(ValueError):
            registry.add(FormMenuItem("probe.style", ("X",), lambda s: None))
    finally:
        forget_package("m5_form_menu_broken")
