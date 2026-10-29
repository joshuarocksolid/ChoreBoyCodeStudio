# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""Your own classes, Qt side (M5.4): the popover, the context rows, stand-ins, the corner tag, Insert and FB035.

R3 123 and 194-198; the P-7 pain test (stand-ins at a real size, header round trip) runs here and in the engine tests.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import List

import pytest

from app.features.form_builder.engine.commands.catalog_ext.promote import UseOwnClass
from app.features.form_builder.engine.diagnostics import DiagnosticLocation, FormDiagnostic, Severity
from app.features.form_builder.engine.project import custom_widgets as cw
from app.features.form_builder.engine.project.custom_checks import custom_diagnostics
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.query.selection import SelectionSource, SelectionState
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.integration.custom_registry import ProjectRegistry, registry_for
from app.features.form_builder.integration.menu_ext import MenuContext, MenuRegistry
from app.features.form_builder.integration.menu_ext import promote as menu_promote
from app.features.form_builder.integration.problem_fixes import FixContext, default_registry
from app.features.form_builder.qtside.canvas.core.chips import Obstacle
from app.features.form_builder.qtside.canvas.core.gesture import Idle
from app.features.form_builder.qtside.canvas.core.space import CanvasRect
from app.features.form_builder.qtside.canvas.layers import own_class
from app.features.form_builder.qtside.dialogs.promote import SAVED_NOTE, open_popover
from app.features.form_builder.qtside.insert.catalog._custom import custom_entries
from app.features.form_builder.qtside.realize import Realizer
from app.features.form_builder.qtside.realize.stand_in import StandInWidget
from app.qt.QtCore import QRect
from app.qt.QtWidgets import QLabel, QMenu, QWidget
from tests.form_builder.qtside.support import form

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("qapp")]

_FORM = form(
    'class="QWidget" name="Form"',
    """
  <layout class="QVBoxLayout" name="box">
   <item><widget class="QLabel" name="totalLabel"><property name="text"><string>Total</string></property></widget></item>
   <item><widget class="QLabel" name="noteLabel"/></item>
   <item><widget class="QWidget" name="card"/></item>
   <item><widget class="QPushButton" name="payButton"/></item>
  </layout>
""",
)


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "shop"
    (root / "cbcs").mkdir(parents=True)
    (root / "cbcs" / "project.json").write_text('{"schema_version": 2, "name": "Shop"}\n', encoding="utf-8")
    (root / "forms").mkdir()
    (root / "widgets").mkdir()
    (root / "widgets" / "till_display.py").write_text("class TillDisplay(QLabel):\n    pass\n", encoding="utf-8")
    (root / "widgets" / "card.py").write_text("class Card(QWidget):\n    pass\n", encoding="utf-8")
    return root


def _open(tmp_path: Path, text: str = _FORM, *, in_project: bool = True):  # noqa: ANN202
    root = _project(tmp_path)
    path = str(root / "forms" / "till.ui")
    if in_project:
        scope = FormScope(
            kind="project", ui_path=path, project_root=str(root.resolve()),
            generated_path=str(root / "forms" / "ui_till.py"), window_path=str(root / "forms" / "till_window.py"),
            module_name="forms.ui_till",
        )
    else:
        scope = FormScope(kind="external", ui_path=path)
    session = FormSession.open(text, path=path, scope=scope)
    realizer = Realizer(session)
    realizer.build()
    return root, session, realizer


def _id(session: FormSession, name: str):  # noqa: ANN202
    return session.document.by_name(name)[0]


@pytest.mark.parity("R3-194", "R3-198")
def test_the_popover_lists_the_registry_fills_a_row_and_checks_without_importing(tmp_path: Path) -> None:
    root, session, realizer = _open(tmp_path)
    try:
        registry = registry_for(str(root.resolve()))
        registry.upsert(cw.RegistryEntry("TillDisplay", "widgets.till_display", "QLabel"))
        registry.upsert(cw.RegistryEntry("Card", "widgets.card", "QWidget", container=True))
        host = QWidget()
        pop = open_popover(session, (_id(session, "totalLabel"),), registry, host)
        assert pop is not None
        # Only the entries based on a label (or a compatible class) are listed.
        picks = [b.text() for b in pop.findChildren(__import__("app.qt.QtWidgets", fromlist=["QPushButton"]).QPushButton, "formBuilder.ownClassPick")]
        assert picks == ["TillDisplay · widgets.till_display"]
        assert not pop._holds.isVisibleTo(pop)  # a label holds nothing
        assert not pop.use_enabled()
        pop.findChildren(__import__("app.qt.QtWidgets", fromlist=["QPushButton"]).QPushButton, "formBuilder.ownClassPick")[0].click()
        assert pop._class.text() == "TillDisplay" and pop._module.text() == "widgets.till_display"
        assert pop.state == cw.FOUND and pop.use_enabled()
        assert pop._use.text() == "Use TillDisplay"
        before = set(sys.modules)
        pop.update_check()
        assert not [name for name in set(sys.modules) - before if name.split(".")[0] == "widgets"]
        pop.set_fields("TillDisplay", "widgets.nowhere")
        assert pop.check_text == "There's no widgets/nowhere.py in this project yet. You can still use the name."
        assert pop.use_enabled()
        pop.set_fields("Till Display", "widgets.till_display")
        assert pop.state == cw.BAD_CLASS and not pop.use_enabled()
        pop.set_fields("TillDisplay", "widgets..x")
        assert pop.state == cw.BAD_MODULE and not pop.use_enabled()
        pop.cancel()
        assert write_ui(session.document).text == write_ui(FormSession.open(_FORM, path="/tmp/x.ui", scope=FormScope(kind="external", ui_path="/tmp/x.ui")).document).text
    finally:
        realizer.dispose()
        session.dispose()


def test_use_saves_the_class_for_the_project_and_the_note_shows_only_the_first_time(tmp_path: Path) -> None:
    root, session, realizer = _open(tmp_path)
    try:
        port = registry_for(str(root.resolve()))
        said: List[str] = []
        host = QWidget()
        pop = open_popover(session, (_id(session, "totalLabel"),), port, host, on_done=said.append)
        assert pop._saved.isVisibleTo(pop) and pop._saved.text() == SAVED_NOTE
        pop.set_fields("TillDisplay", "widgets.till_display")
        pop._use.click()
        assert said == ["Used TillDisplay."]
        assert [e.class_name for e in port.entries()] == ["TillDisplay"]
        assert session.log.undo_label() == "Use class TillDisplay for totalLabel"
        second = open_popover(session, (_id(session, "noteLabel"),), port, host)
        assert not second._saved.isVisibleTo(second)
        second.cancel()
        # Undo takes the class off the form; the project's list keeps it (not on the undo stack).
        session.log.undo()
        assert "TillDisplay" not in write_ui(session.document).text
        assert [e.class_name for e in port.entries()] == ["TillDisplay"]
    finally:
        realizer.dispose()
        session.dispose()


def test_a_registry_row_edits_and_removes_without_touching_forms(tmp_path: Path) -> None:
    root, session, realizer = _open(tmp_path)
    try:
        port = registry_for(str(root.resolve()))
        port.upsert(cw.RegistryEntry("TillDisplay", "widgets.till_display", "QLabel"))
        session.log.execute(UseOwnClass((_id(session, "totalLabel"),), "TillDisplay", "widgets.till_display", "QLabel"))
        host = QWidget()
        pop = open_popover(session, (_id(session, "noteLabel"),), port, host)
        pop._edit(port.entries()[0])
        pop._description.setText("Running total")
        pop._width.setValue(220)
        pop._height.setValue(48)
        assert pop._use.text() == "Save"
        pop._use.click()
        found = port.find("TillDisplay")
        assert found.description == "Running total" and found.size == (220, 48)
        again = open_popover(session, (_id(session, "noteLabel"),), port, host)
        again._forget(port.entries()[0])
        assert port.entries() == ()
        assert "<class>TillDisplay</class>" in write_ui(session.document).text
        again.cancel()
    finally:
        realizer.dispose()
        session.dispose()


def test_a_form_outside_a_project_can_still_name_a_class_and_saves_nothing(tmp_path: Path) -> None:
    root, session, realizer = _open(tmp_path, in_project=False)
    try:
        port = registry_for(None)
        host = QWidget()
        pop = open_popover(session, (_id(session, "totalLabel"),), port, host)
        pop.set_fields("TillDisplay", "widgets.till_display")
        assert pop.check_text == "This form isn't in a project, so Preview shows a stand-in."
        assert pop.use_enabled()
        pop._use.click()
        assert '<widget class="TillDisplay"' in write_ui(session.document).text
        assert port.entries() == ()
    finally:
        realizer.dispose()
        session.dispose()


def _menu(session: FormSession, ids, run=None) -> QMenu:  # noqa: ANN001
    registry = MenuRegistry()
    menu_promote.register(registry.scope("test"))
    menu = QMenu()
    ctx = MenuContext(menu, tuple(ids), ids[0], session, lambda _name: None, run=run or (lambda command: session.log.execute(command)))
    registry.run("structure", ctx)
    return menu


def test_the_context_rows_follow_the_selection(tmp_path: Path) -> None:
    root, session, realizer = _open(tmp_path)
    try:
        rows = lambda menu: [a.text() for a in menu.actions()]  # noqa: E731
        label = _id(session, "totalLabel")
        menu = _menu(session, [label])
        assert rows(menu) == ["Use my own class…"]
        assert menu.actions()[0].toolTip() == "Qt Designer calls this Promote to."
        assert rows(_menu(session, [session.document.root.id])) == []
        assert rows(_menu(session, [label, _id(session, "payButton")])) == []
        assert rows(_menu(session, [label, _id(session, "noteLabel")])) == ["Use my own class…"]
        session.log.execute(UseOwnClass((label,), "TillDisplay", "widgets.till_display", "QLabel", names=("totalLabel",)))
        menu = _menu(session, [label])
        assert rows(menu) == ["Use my own class…", "Back to label"]
        menu.actions()[1].trigger()
        assert session.log.undo_label() == "Use label for totalLabel"
        assert "<customwidget>" not in write_ui(session.document).text
    finally:
        realizer.dispose()
        session.dispose()


def test_several_widgets_of_one_class_change_together(tmp_path: Path) -> None:
    root, session, realizer = _open(tmp_path)
    try:
        ids = (_id(session, "totalLabel"), _id(session, "noteLabel"))
        host = QWidget()
        pop = open_popover(session, ids, registry_for(str(root.resolve())), host)
        pop.set_fields("TillDisplay", "widgets.till_display")
        pop._use.click()
        text = write_ui(session.document).text
        assert text.count('class="TillDisplay"') == 2 and text.count("<customwidget>") == 1
        assert session.log.undo_label() == "Use class TillDisplay for 2 widgets"
        assert len(session.log.entries()) == 1
    finally:
        realizer.dispose()
        session.dispose()


@pytest.mark.pain("P-7")
@pytest.mark.parity("R3-123")
def test_a_label_class_draws_as_a_label_and_a_widget_class_as_a_sized_stand_in(tmp_path: Path) -> None:
    root, session, realizer = _open(tmp_path)
    try:
        session.log.execute(UseOwnClass((_id(session, "totalLabel"),), "TillDisplay", "widgets.till_display", "QLabel"))
        session.log.execute(UseOwnClass((_id(session, "card"),), "Card", "widgets.card", "QWidget", container=True))
        label = realizer.widget_for(_id(session, "totalLabel"))
        card = realizer.widget_for(_id(session, "card"))
        assert type(label) is QLabel and label.text() == "Total"
        assert isinstance(card, StandInWidget)
        assert card.text() == "Card · from widgets.card"
        assert (card.sizeHint().width(), card.sizeHint().height()) == cw.DEFAULT_SIZE
        assert not card.grab().isNull()
        # The registry's size wins over the declaration's.
        realizer.own_class_lookup = lambda name: cw.RegistryEntry(name, "widgets.card", "QWidget", size=(200, 90))
        session.log.execute(UseOwnClass((_id(session, "card"),), "Card", "widgets.card", "QWidget", names=("card",)))  # no change
        session.log.undo()
        session.log.undo()
        session.log.execute(UseOwnClass((_id(session, "card"),), "Card", "widgets.card", "QWidget", container=True))
        card = realizer.widget_for(_id(session, "card"))
        assert (card.sizeHint().width(), card.sizeHint().height()) == (200, 90)
        # Nothing of the project was imported to draw them.
        assert not [name for name in sys.modules if name.split(".")[0] in ("widgets",)]
    finally:
        realizer.dispose()
        session.dispose()


def _frame(session: FormSession, selected, rect: CanvasRect, hover=None):  # noqa: ANN001, ANN202
    node = session.document.by_name("totalLabel")[0]
    static = SimpleNamespace(placed=(Obstacle(node, rect),))
    inputs = SimpleNamespace(
        document=session.document,
        selection=SelectionState(tuple(selected), selected[0] if selected else None),
        gesture=Idle(hover=hover),
    )
    return node, static, inputs


def test_the_corner_tag_shows_on_the_selected_widget_and_the_hit_area_is_at_least_80_by_24(tmp_path: Path) -> None:
    root, session, realizer = _open(tmp_path)
    try:
        node = _id(session, "totalLabel")
        _node, static, inputs = _frame(session, [node], CanvasRect(10, 10, 30, 12))
        assert own_class.build(static, inputs, True).items == ()  # a plain label: no tag, no extra target
        session.log.execute(UseOwnClass((node,), "TillDisplay", "widgets.till_display", "QLabel"))
        out = own_class.build(static, inputs, True)
        assert len(out.items) == 1 and out.items[0].layer == "own_class"
        (rect, target), = out.targets
        assert (rect.width, rect.height) == (80, 24) and target.node == node
        _n, static, inputs = _frame(session, [], CanvasRect(10, 10, 30, 12), hover=node)
        assert len(own_class.build(static, inputs, True).items) == 1
        _n, static, inputs = _frame(session, [], CanvasRect(10, 10, 300, 120))
        assert own_class.build(static, inputs, True) == own_class.build(static, inputs, True)
        assert own_class.build(static, inputs, True).items == () and own_class.build(static, inputs, True).targets == ()
    finally:
        realizer.dispose()
        session.dispose()


@pytest.mark.parity("R3-196")
def test_insert_lists_the_registry_with_its_description_and_inserts_one_named_step(tmp_path: Path) -> None:
    root, session, realizer = _open(tmp_path)
    try:
        registry = ProjectRegistry(str(root.resolve()))
        registry.upsert(cw.RegistryEntry("TillDisplay", "widgets.till_display", "QLabel", description="Running total", size=(200, 48)))
        found = custom_entries((), registry.entries())
        assert [e.friendly for e in found] == ["Till display"]
        assert found[0].category == "Your widgets" and found[0].description == "Running total"
        fragment = found[0].build()
        assert fragment.nodes[0].field("class_name") == "TillDisplay"
        declared = fragment.customwidgets[0]
        assert declared.field("header").text == "widgets/till_display.h" and declared.field("header").location == "local"
        from app.features.form_builder.engine.commands.catalog import InsertFragment
        from app.features.form_builder.engine.commands.placement import InBoxLayout

        assert InsertFragment(InBoxLayout(session.document.root.layout.id, 0), fragment).label == "Insert TillDisplay"
        # The form's own declaration comes first, then the project's other classes.
        both = custom_entries([("Card", "QWidget", "widgets/card.h")], registry.entries())
        assert [e.qt_class for e in both] == ["Card", "TillDisplay"]
    finally:
        realizer.dispose()
        session.dispose()


def test_fb035_names_a_module_that_is_not_in_the_project_and_offers_the_popover(tmp_path: Path) -> None:
    root, session, realizer = _open(tmp_path)
    try:
        label = _id(session, "totalLabel")
        session.log.execute(UseOwnClass((label,), "Gone", "widgets.gone", "QLabel", names=("totalLabel",)))
        session.log.execute(UseOwnClass((_id(session, "noteLabel"),), "TillDisplay", "widgets.till_display", "QLabel"))
        found = custom_diagnostics(session.document, str(root.resolve()))
        assert [d.message for d in found] == ["Gone comes from widgets.gone, which isn't in this project."]
        assert found[0].code == "FB035" and found[0].severity is Severity.WARNING
        assert found[0].location.object_name == "totalLabel"
        assert custom_diagnostics(session.document, None) == ()
        fixes = default_registry().for_diagnostic(found[0])
        assert [f.title for f in fixes if f.fix_id == "use-my-own-class"] == ["Use my own class…"]
        opened: List[object] = []
        from app.features.form_builder.integration.problem_fixes import custom as custom_fix

        original = custom_fix.open_popover
        custom_fix.open_popover = lambda *args, **kwargs: opened.append(args) or None
        try:
            fix = next(f for f in fixes if f.fix_id == "use-my-own-class")
            fix.run(FixContext(found[0], session, str(root.resolve()), None))
        finally:
            custom_fix.open_popover = original
        assert opened and opened[0][1] == (label,)
        # A global header (a library) and a C++ name are not project files.
        text = write_ui(session.document).text.replace('location="local">widgets/gone.h', 'location="global">widgets/gone.h')
        other = FormSession.open(text, path=session.path, scope=session.scope)
        assert custom_diagnostics(other.document, str(root.resolve())) == ()
        other.dispose()
    finally:
        realizer.dispose()
        session.dispose()


def test_the_header_names_the_base_in_plain_words(tmp_path: Path) -> None:
    from app.features.form_builder.qtside.inspector.model import project_header

    root, session, realizer = _open(tmp_path)
    try:
        label = _id(session, "totalLabel")
        session.log.execute(UseOwnClass((label,), "TillDisplay", "widgets.till_display", "QLabel"))
        session.selection.set((label,), source=SelectionSource.PROGRAM)
        view = project_header(session)
        assert view.class_line == "TillDisplay · your class, based on Label"
        assert view.qt_line == "TillDisplay (QLabel)"
        session.selection.set((_id(session, "payButton"),), source=SelectionSource.PROGRAM)
        assert project_header(session).class_line == ""
    finally:
        realizer.dispose()
        session.dispose()


@pytest.mark.parity("R3-196")
def test_the_insert_pane_shows_your_widgets_from_the_registry_and_the_form(tmp_path: Path) -> None:
    from app.features.form_builder.qtside.insert.pane import InsertPane
    from app.features.form_builder.qtside.insert.rows import ENTRY, HEADER
    from app.features.form_builder.integration.insert_memory import InMemoryInsertMemory
    from app.features.form_builder.integration.workbench import _PieceOps
    from app.features.form_builder.qtside.insert.delegate import ROW_ROLE

    root, session, realizer = _open(tmp_path)
    host = QWidget()
    pane = InsertPane(lambda _collapsed: None, host, memory=InMemoryInsertMemory(), pieces=_PieceOps())  # type: ignore[arg-type]
    try:
        pane.bind_session(session)

        def rows() -> list:
            return [pane.body.item(i).data(int(ROW_ROLE)) for i in range(pane.body.count())]

        assert not any(r.kind == HEADER and r.category == "Your widgets" for r in rows())
        registry = registry_for(str(root.resolve()))
        registry.upsert(cw.RegistryEntry("TillDisplay", "widgets.till_display", "QLabel", description="Running total"))
        pane.bind_registry(registry)
        pane.filter.setText("till")
        found = [r for r in rows() if r.kind == ENTRY]
        assert [r.title for r in found] == ["Till display"] and found[0].category == "Your widgets"
        assert "Running total" in pane._tooltip(found[0]) or found[0].key == "custom:TillDisplay"
        pane.filter.setText("")
        assert any(r.kind == HEADER and r.category == "Your widgets" for r in rows())
        registry.remove("TillDisplay")
        pane.refresh_custom()
        assert not any(r.kind == HEADER and r.category == "Your widgets" for r in rows())
    finally:
        pane.deleteLater()
        realizer.dispose()
        session.dispose()
