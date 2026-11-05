"""Rename, move and delete keep cross-form open steps, or Problems names the form."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator, Tuple

import pytest

from app.editors.editor_manager import EditorManager
from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.commands.catalog import SetLogic
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.logic.codec import parse_steps, write_steps
from app.features.form_builder.engine.project.adoption import scope_for
from app.features.form_builder.engine.project.create import create_form
from app.features.form_builder.engine.project.form_refs import missing_form_sentence, retarget_ui_text
from app.features.form_builder.engine.project.fs import OsFileSystem
from app.features.form_builder.engine.project.rename import apply, plan_rename
from app.features.form_builder.engine.project.save import write_generated
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.integration.content_source import open_document_log
from app.shell.project_tree_action_coordinator import ProjectTreeActionCoordinator

pytestmark = pytest.mark.unit


def _arm(path: Path, stem: str) -> None:
    log = open_document_log(path.read_text(encoding="utf-8"))
    read = parse_steps('[{"do": "openForm", "form": "%s", "mode": "dialog"}]' % stem)
    assert read.error is None
    log.execute(SetLogic(log.document.root.id, "cbcsOnClicked", write_steps(read.steps)))
    path.write_text(write_ui_text(log), encoding="utf-8")


def write_ui_text(log: object) -> str:
    from app.features.form_builder.engine.ui4.writer import write_ui

    return write_ui(log.document).text  # type: ignore[attr-defined]


def _regenerate(root: Path, stem: str, fs: OsFileSystem) -> None:
    path = root / "forms" / ("%s.ui" % stem)
    text = path.read_text(encoding="utf-8")
    scope = scope_for(str(path), str(root), fs)
    document = read_ui(text, allocator=IdAllocator()).document
    write_generated(scope, document, text.encode("utf-8"), fs)


def test_rename_follows_an_open_form_step_and_delete_names_it(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    fs = OsFileSystem()
    assert create_form(str(root), "customer", fs).refused is None
    assert create_form(str(root), "sale", fs).refused is None
    sale = root / "forms" / "sale.ui"
    _arm(sale, "customer")
    _regenerate(root, "sale", fs)
    plan = plan_rename(str(root), str(root / "forms" / "customer.ui"), str(root / "forms" / "client.ui"), fs)
    assert plan.reason is None, plan.reason
    apply(plan, fs)
    sale_text = sale.read_text(encoding="utf-8")
    document = read_ui(sale_text, allocator=IdAllocator()).document
    entry = document.root.prop("cbcsOnClicked")
    assert entry is not None
    stored = getattr(entry.value, "text", None)
    assert isinstance(stored, str)
    opened = parse_steps(stored)
    assert opened.error is None
    assert ("form", "client") in opened.steps[0].fields
    generated = (root / "forms" / "ui_sale.py").read_text(encoding="utf-8")
    assert "from forms.client_window import ClientWindow" in generated
    assert (root / "forms" / "ui_client.py").is_file()
    assert not (root / "forms" / "ui_customer.py").exists()
    assert (root / "forms" / "__init__.py").is_file()
    for name in ("client.ui", "ui_client.py", "client_window.py"):
        os.remove(str(root / "forms" / name))
    document = read_ui(sale_text, allocator=IdAllocator()).document
    scope = scope_for(str(sale), str(root), fs)
    result = generate_form_module(document, scope=scope, source_bytes=sale.read_bytes())
    messages = [item.message for item in result.diagnostics if item.code == "FB120"]
    assert messages == [missing_form_sentence("client")]


_COMMENTED = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <!-- keep me -->
 <widget class="QWidget" name="Form">
  <property name="cbcsOnClicked" stdset="0">
   <string>[{"do": "openForm", "form": "x", "mode": "dialog"}]</string>
  </property>
 </widget>
</ui>
"""


def test_retarget_changes_only_the_open_form_name() -> None:
    updated = retarget_ui_text(_COMMENTED, "x", "y")
    assert updated == _COMMENTED.replace('"form": "x"', '"form": "y"')
    assert updated is not None
    assert "<!-- keep me -->" in updated


def test_a_cross_folder_move_leaves_both_reports_and_names_the_form(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    fs = OsFileSystem()
    left = root / "forms" / "a"
    right = root / "forms" / "b"
    assert create_form(str(root), "report", fs, directory=str(left)).refused is None
    assert create_form(str(root), "report", fs, directory=str(right)).refused is None
    assert create_form(str(root), "x", fs, directory=str(left)).refused is None
    opener = left / "report.ui"
    other = right / "report.ui"
    _arm(opener, "x")
    other.write_text(_COMMENTED, encoding="utf-8")
    opener_bytes = opener.read_bytes()
    other_bytes = other.read_bytes()
    generated = (left / "ui_report.py").read_bytes()
    plan = plan_rename(str(root), str(left / "x.ui"), str(right / "y.ui"), fs)
    assert plan.reason is None, plan.reason
    assert [item.message for item in plan.diagnostics if item.code == "FB120"] == [missing_form_sentence("x")]
    apply(plan, fs)
    assert opener.read_bytes() == opener_bytes
    assert other.read_bytes() == other_bytes
    assert (left / "ui_report.py").read_bytes() == generated


def test_deleting_a_form_from_the_tree_names_it_without_rewriting(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from app.features.form_builder.integration.form_removal import install_form_removal
    from app.project.path_removed import set_path_removed_listener
    from app.shell.breakpoint_store import BreakpointStore
    from app.shell.project_tree_controller import ProjectTreeController

    root = tmp_path / "proj"
    fs = OsFileSystem()
    assert create_form(str(root), "customer", fs).refused is None
    assert create_form(str(root), "sale", fs).refused is None
    sale = root / "forms" / "sale.ui"
    _arm(sale, "customer")
    _regenerate(root, "sale", fs)
    sale_bytes = sale.read_bytes()
    generated = (root / "forms" / "ui_sale.py").read_bytes()
    published = []
    window = SimpleNamespace(
        _loaded_project=SimpleNamespace(project_root=str(root)),
        _problems_controller=SimpleNamespace(
            apply_lint_diagnostics_result=lambda path, rows: published.append((path, list(rows)))
        ),
    )
    install_form_removal(window)
    coordinator = ProjectTreeActionCoordinator(
        project_tree_controller=ProjectTreeController(),
        open_tab_paths=lambda: [],
        widget_for_path=lambda _path: None,
        tab_index_for_path=lambda _path: -1,
        remove_tab_at_index=lambda _index: None,
        release_tab_content=lambda _path: None,
        rekey_tab_content=lambda _old, _new: None,
        close_editor_file=lambda _path: None,
        breakpoint_store=BreakpointStore(),
        refresh_breakpoints_list=lambda: None,
        remap_editor_paths=lambda _old, _new: {},
        update_tab_path_and_name=lambda _index, _path: None,
        apply_breakpoints_to_widget=lambda _widget, _bps: None,
        update_widget_language=lambda _widget, _path: None,
        maybe_rewrite_imports=lambda _src, _dst: None,
        refresh_project=lambda _tier: None,
    )
    try:
        assert coordinator.handle_delete(str(root / "forms" / "customer.ui")) is None
    finally:
        set_path_removed_listener(None)
    assert sale.read_bytes() == sale_bytes
    assert (root / "forms" / "ui_sale.py").read_bytes() == generated
    messages = [row.message for _path, rows in published for row in rows if row.code == "FB120"]
    assert messages == [missing_form_sentence("customer")]


@contextmanager
def _armed_tree(root: Path) -> Iterator[Tuple[ProjectTreeActionCoordinator, EditorManager, list]]:
    from app.features.form_builder.integration.form_move import install_form_move
    from app.features.form_builder.integration.form_removal import install_form_removal
    from app.project.path_removed import set_path_removed_listener
    from app.project.path_rename import set_path_move_handler
    from app.shell.breakpoint_store import BreakpointStore
    from app.shell.project_tree_controller import ProjectTreeController

    published: list = []
    window = SimpleNamespace(
        _loaded_project=SimpleNamespace(project_root=str(root)),
        _problems_controller=SimpleNamespace(
            apply_lint_diagnostics_result=lambda path, rows: published.append((path, list(rows)))
        ),
    )
    install_form_removal(window)
    install_form_move(window)
    manager = EditorManager()
    coordinator = ProjectTreeActionCoordinator(
        project_tree_controller=ProjectTreeController(),
        open_tab_paths=manager.open_paths,
        widget_for_path=lambda _path: None,
        tab_index_for_path=lambda _path: -1,
        remove_tab_at_index=lambda _index: None,
        release_tab_content=lambda _path: None,
        rekey_tab_content=lambda _old, _new: None,
        close_editor_file=manager.close_file,
        breakpoint_store=BreakpointStore(),
        refresh_breakpoints_list=lambda: None,
        remap_editor_paths=manager.remap_paths_for_move,
        update_tab_path_and_name=lambda _index, _path: None,
        apply_breakpoints_to_widget=lambda _widget, _bps: None,
        update_widget_language=lambda _widget, _path: None,
        maybe_rewrite_imports=lambda _src, _dst: None,
        refresh_project=lambda _tier: None,
    )
    try:
        yield coordinator, manager, published
    finally:
        set_path_move_handler(None)
        set_path_removed_listener(None)


def _open_form_name(path: Path) -> str:
    document = read_ui(path.read_text(encoding="utf-8"), allocator=IdAllocator()).document
    entry = document.root.prop("cbcsOnClicked")
    assert entry is not None
    stored = getattr(entry.value, "text", None)
    assert isinstance(stored, str)
    opened = parse_steps(stored)
    assert opened.error is None
    for key, value in opened.steps[0].fields:
        if key == "form":
            assert isinstance(value, str)
            return value
    raise AssertionError("openForm has no form")


def test_renaming_a_form_in_the_tree_moves_its_companions_and_the_open_tab(tmp_path: Path) -> None:
    from app.editors.editor_manager import normalized_path

    root = tmp_path / "proj"
    fs = OsFileSystem()
    assert create_form(str(root), "customer", fs).refused is None
    assert create_form(str(root), "sale", fs).refused is None
    forms = root / "forms"
    sale = forms / "sale.ui"
    customer = forms / "customer.ui"
    _arm(sale, "customer")
    _regenerate(root, "sale", fs)
    with _armed_tree(root) as (coordinator, manager, _published):
        manager.open_file_with_content(str(customer), customer.read_text(encoding="utf-8"))
        assert coordinator.handle_rename(str(customer), "client.ui") is None
    client = forms / "client.ui"
    assert not (forms / "ui_customer.py").exists()
    assert (forms / "ui_client.py").is_file()
    assert (forms / "client_window.py").is_file()
    assert not (forms / "customer_window.py").exists()
    assert _open_form_name(sale) == "client"
    generated = (forms / "ui_sale.py").read_text(encoding="utf-8")
    assert "from forms.client_window import ClientWindow" in generated
    assert manager.open_paths() == [normalized_path(str(client))]


def test_cutting_a_form_into_another_folder_moves_companions_and_names_the_form(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    fs = OsFileSystem()
    assert create_form(str(root), "customer", fs).refused is None
    assert create_form(str(root), "sale", fs).refused is None
    forms = root / "forms"
    sale = forms / "sale.ui"
    _arm(sale, "customer")
    sale_bytes = sale.read_bytes()
    generated = (forms / "ui_sale.py").read_bytes()
    archive = forms / "archive"
    archive.mkdir()
    with _armed_tree(root) as (coordinator, _manager, published):
        failed, _paths, _cut = coordinator.handle_paste(
            destination_directory=str(archive),
            clipboard_paths=[str(forms / "customer.ui")],
            clipboard_cut=True,
        )
    assert failed == []
    assert (archive / "customer.ui").is_file()
    assert (archive / "ui_customer.py").is_file()
    assert (archive / "customer_window.py").is_file()
    assert not (forms / "customer.ui").exists()
    assert not (forms / "ui_customer.py").exists()
    assert not (forms / "customer_window.py").exists()
    assert sale.read_bytes() == sale_bytes
    assert (forms / "ui_sale.py").read_bytes() == generated
    messages = [row.message for _path, rows in published for row in rows if row.code == "FB120"]
    assert messages == [missing_form_sentence("customer")]


def test_dropping_a_form_on_a_folder_moves_its_companions(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    fs = OsFileSystem()
    assert create_form(str(root), "customer", fs).refused is None
    forms = root / "forms"
    archive = forms / "archive"
    archive.mkdir()
    with _armed_tree(root) as (coordinator, _manager, _published):
        assert coordinator.handle_drop_move(str(forms / "customer.ui"), str(archive)) is None
    assert (
        (archive / "ui_customer.py").is_file(),
        (archive / "customer_window.py").is_file(),
        (forms / "ui_customer.py").exists(),
        (forms / "customer_window.py").exists(),
    ) == (True, True, False, False)


def test_renaming_a_plain_file_ignores_the_form_plan(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    fs = OsFileSystem()
    assert create_form(str(root), "customer", fs).refused is None
    forms = root / "forms"
    notes = forms / "notes.txt"
    notes.write_text("hello\n", encoding="utf-8")
    with _armed_tree(root) as (coordinator, _manager, _published):
        assert coordinator.handle_rename(str(notes), "readme.txt") is None
    assert (forms / "readme.txt").read_text(encoding="utf-8") == "hello\n"
    assert not notes.exists()
    assert (forms / "customer.ui").is_file()
    assert (forms / "ui_customer.py").is_file()
    assert (forms / "customer_window.py").is_file()


def test_renaming_a_form_off_ui_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    fs = OsFileSystem()
    assert create_form(str(root), "customer", fs).refused is None
    forms = root / "forms"
    customer = forms / "customer.ui"
    before = (
        customer.read_bytes(),
        (forms / "ui_customer.py").read_bytes(),
        (forms / "customer_window.py").read_bytes(),
    )
    with _armed_tree(root) as (coordinator, _manager, _published):
        sentence = coordinator.handle_rename(str(customer), "customer.txt")
    assert sentence == "A form file has to end with .ui."
    assert not (forms / "customer.txt").exists()
    assert (
        customer.read_bytes(),
        (forms / "ui_customer.py").read_bytes(),
        (forms / "customer_window.py").read_bytes(),
    ) == before


def test_renaming_a_form_onto_an_existing_form_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    fs = OsFileSystem()
    assert create_form(str(root), "customer", fs).refused is None
    assert create_form(str(root), "sale", fs).refused is None
    forms = root / "forms"
    customer = forms / "customer.ui"
    sale = forms / "sale.ui"
    before = (
        customer.read_bytes(),
        (forms / "ui_customer.py").read_bytes(),
        (forms / "customer_window.py").read_bytes(),
        sale.read_bytes(),
    )
    with _armed_tree(root) as (coordinator, _manager, _published):
        sentence = coordinator.handle_rename(str(customer), "sale.ui")
    assert sentence == "A file named sale.ui is already in that folder."
    assert (
        customer.read_bytes(),
        (forms / "ui_customer.py").read_bytes(),
        (forms / "customer_window.py").read_bytes(),
        sale.read_bytes(),
    ) == before
