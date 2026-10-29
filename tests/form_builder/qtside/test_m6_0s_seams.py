# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""M6.0s seams with Qt: Behavior sections, the double-click hook, overlay kinds and their link gesture, the toolbar toggle."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

import pytest

from app.features.form_builder.engine.query.selection import SelectionSource, SelectionState
from app.features.form_builder.integration import overlays
from app.features.form_builder.integration.activate_ext import ActivateRegistry, load_activators
from app.features.form_builder.integration.overlay_ext import (
    LinkGesture,
    OverlayKind,
    OverlayRegistry,
    ToggleSpec,
    load_overlay_kinds,
)
from app.features.form_builder.qtside.canvas.core.gesture import (
    Activate,
    Idle,
    Key,
    Mods,
    OpenEditor,
    Press,
    Select,
    World,
    step,
)
from app.features.form_builder.qtside.canvas.core.space import PortPoint
from app.features.form_builder.qtside.canvas.core.words import hover_sentence
from app.features.form_builder.qtside.inspector import behavior_ext
from app.features.form_builder.qtside.inspector.pane import TabId
from app.qt.QtCore import QEvent, QPoint, QPointF, Qt
from app.qt.QtGui import QKeyEvent, QMouseEvent
from app.qt.QtWidgets import QApplication, QPushButton, QWidget
from tests.form_builder.inspector.test_inspector_round2 import _close, _pane, _select
from tests.form_builder.m5_0s_support import forget_package, make_package
from tests.form_builder.qtside.support import realize
from tests.form_builder.qtside.test_canvas_core import (
    BARE,
    LAID,
    _bare_index,
    _canvas,
    _nid,
    _opened,
    _view,
    _world,
)

pytestmark = [pytest.mark.unit]


# ------------------------------------------------------------ Behavior sections

_SECTIONS = {
    "a_late": """
        from app.qt.QtWidgets import QLabel
        from app.features.form_builder.qtside.inspector.behavior_ext import BehaviorSection

        def make(host):
            label = QLabel("form only", host.parent)
            label.setObjectName("probe.formOnly")
            return label

        def register(registry):
            registry.add(BehaviorSection("probe.form_only", 50, make, lambda inputs: inputs.is_form))
    """,
    "b_early": """
        from app.qt.QtWidgets import QLabel
        from app.features.form_builder.qtside.inspector.behavior_ext import BehaviorSection

        class Top(QLabel):
            def __init__(self, host):
                super().__init__("top", host.parent)
                self.painted = 0

            def paint(self, inputs):
                self.painted += 1

        def register(registry):
            registry.add(BehaviorSection("probe.top", 5, Top))
    """,
    "c_broken": """
        from app.features.form_builder.qtside.inspector.behavior_ext import BehaviorSection

        def boom(host):
            raise RuntimeError("section bug")

        def register(registry):
            registry.add(BehaviorSection("probe.broken", 20, boom))
    """,
}


def test_a_section_added_from_a_new_file_shows_in_order_with_its_predicate_and_the_m3_list_still_works(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = make_package(tmp_path, monkeypatch, "m6_behavior_probe", _SECTIONS)
    registry = behavior_ext.load_sections(package)
    monkeypatch.setattr("app.features.form_builder.qtside.inspector._behavior.default_registry", lambda: registry)
    window, pane, session, realizer = _pane(qapp)
    try:
        assert [s.section_id for s in registry.sections()] == ["probe.top", "probe.broken", "probe.form_only"]
        _select(session, "okButton")
        pane.focus_tab(TabId.BEHAVIOR)
        pane.flush()
        qapp.processEvents()
        host = pane.behavior
        # Order 5, then the M3 list standing in for Events at 30; the form-only section is hidden, the broken one never shown.
        assert host.shown_sections() == ["probe.top", "connections"]
        top = host.section_widget("probe.top")
        assert top is not None and top.painted >= 1
        add = next(button for button in pane.findChildren(QPushButton) if "Add connection" in button.text())
        assert add.isVisibleTo(window)
        layout = host.layout()
        order = [layout.itemAt(i).widget() for i in range(layout.count()) if layout.itemAt(i).widget() is not None]
        assert order[0] is host.section_widget("probe.top") and order[1] is host.section_widget("connections")
        _select(session, "Invoice")
        pane.flush()
        qapp.processEvents()
        assert host.shown_sections() == ["probe.top", "connections", "probe.form_only"]
        _select(session, "okButton")
        pane.flush()
        assert host.shown_sections() == ["probe.top", "connections"]
    finally:
        _close(window, pane, realizer, session, qapp)
        forget_package("m6_behavior_probe")


# ------------------------------------------------------------ double-click hook


def _claims(*names: str):  # type: ignore[no-untyped-def]
    def claims(document, node):  # type: ignore[no-untyped-def]
        found = document.get(node)
        return "double-click to write code" if getattr(found, "object_name", "") in names else None

    return claims


def test_a_claimed_double_click_activates_and_leaves_text_editing_to_widgets_nobody_claims() -> None:
    with _opened(BARE) as session:
        view = _view()
        index = _bare_index(session)
        ok = _nid(session, "ok")
        email = _nid(session, "email")
        world = _world(session, index, view)
        world = replace(world, claims=_claims("ok"))
        double = lambda x, y: Press(_canvas(view, x, y), PortPoint(0, 0), "left", Mods(), True)  # noqa: E731
        claimed = step(Idle(), double(40, 50), world)
        assert Activate(ok) in claimed.effects and Select((ok,), ok) in claimed.effects
        assert not any(isinstance(effect, OpenEditor) for effect in claimed.effects)
        # Not claimed: the M3 double-click on a line edit still opens its text editor.
        other = step(Idle(), double(40, 90), world)
        assert Activate(email) not in other.effects
        assert any(isinstance(effect, OpenEditor) for effect in other.effects)
        # A single press never activates, and Enter never asks the contributors.
        single = step(Idle(), Press(_canvas(view, 40, 50), PortPoint(0, 0), "left", Mods(), False), world)
        assert not any(isinstance(effect, Activate) for effect in single.effects)
        entered = step(Idle(), Key("enter", Mods()), replace(world, selection=SelectionState((ok,), ok)))
        assert not any(isinstance(effect, Activate) for effect in entered.effects)


def test_a_claimed_widget_says_what_double_click_does_in_the_status_bar() -> None:
    with _opened(BARE) as session:
        ok = _nid(session, "ok")
        plain = hover_sentence(session.document, ok, False)
        assert plain.endswith("· click to select")
        claimed = hover_sentence(session.document, ok, True, "double-click to write code")
        assert claimed == plain + " · double-click to write code"


def test_activators_are_found_by_module_the_first_claim_wins_and_a_broken_one_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = make_package(
        tmp_path,
        monkeypatch,
        "m6_activate_probe",
        {
            "b_second": """
                from app.features.form_builder.integration.activate_ext import Activator
                RAN = []
                def register(registry):
                    registry.add(Activator("second", lambda doc, node: "second words", lambda s, n: RAN.append(("second", n))))
            """,
            "a_first": """
                from app.features.form_builder.integration.activate_ext import Activator
                RAN = []
                def boom(doc, node):
                    raise RuntimeError("claims bug")
                def register(registry):
                    registry.add(Activator("broken", boom, lambda s, n: None))
                    registry.add(Activator("first", lambda doc, node: "first words" if node == 1 else None, lambda s, n: RAN.append(("first", n))))
            """,
        },
    )
    try:
        registry = load_activators(package)
        assert [a.activator_id for a in registry.activators()] == ["broken", "first", "second"]
        with _opened(BARE) as session:
            surface = SimpleNamespace(session=session)
            assert registry.claim(session.document, 1) == "first words"
            assert registry.claim(session.document, 2) == "second words"
            assert registry.activate(surface, 2) is True
            assert package.a_first.RAN == [] and package.b_second.RAN == [("second", 2)]
            assert ActivateRegistry().activate(surface, 2) is False
    finally:
        forget_package("m6_activate_probe")


# --------------------------------------------------------------- overlay kinds


class _Canvas:
    def __init__(self, at: Dict[int, Optional[int]]) -> None:
        self.at = at
        self.layers: Dict[str, object] = {}
        self.banner: Optional[tuple] = None
        self.claimer: Any = None

    def show_banner(self, glyph, name, sentence, extra, on_extra, on_done):  # type: ignore[no-untyped-def]
        self.banner = (glyph, name, sentence, extra)

    def hide_banner(self) -> None:
        self.banner = None

    def show_layer(self, name: str, state: object = True) -> None:
        self.layers[name] = state

    def hide_layer(self, name: str) -> None:
        self.layers.pop(name, None)

    def set_claimer(self, claimer: Any) -> None:
        self.claimer = claimer

    def setFocus(self) -> None:  # noqa: N802
        return None

    def node_at(self, pos: QPoint) -> Optional[int]:
        return self.at.get(pos.x())

    def mapToScene(self, pos: QPoint) -> QPointF:  # noqa: N802
        return QPointF(pos)

    def viewport_rect(self, ids: Any) -> None:
        return None


def _key(key: Qt.Key) -> QKeyEvent:
    return QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)


def _mouse(kind: QEvent.Type, x: int) -> QMouseEvent:
    button = Qt.MouseButton.LeftButton if kind != QEvent.Type.MouseMove else Qt.MouseButton.NoButton
    held = Qt.MouseButton.LeftButton if kind != QEvent.Type.MouseButtonRelease else Qt.MouseButton.NoButton
    return QMouseEvent(kind, QPointF(x, 5), QPointF(x, 5), button, held, Qt.KeyboardModifier.NoModifier)


def _modes(monkeypatch: pytest.MonkeyPatch, text: str, at: Dict[str, Optional[str]], tmp_path: Path):  # type: ignore[no-untyped-def]
    session, realizer = realize(text)
    canvas = _Canvas({})
    links: List[Tuple[int, int]] = []
    status: List[str] = []
    kind = OverlayKind(
        "probe",
        "Probe",
        "Drag from a widget to the widget it should act on.",
        "probe_layer",
        glyph="buddy",
        toggle=ToggleSpec("Probe", "Probe overlay"),
        link=LinkGesture(lambda surface, source, target: links.append((source, target)), start_status=lambda n: "from " + n),
    )
    registry = OverlayRegistry()
    registry.add(kind)
    monkeypatch.setattr(overlays, "overlay_kinds", lambda: registry)
    synced: List[str] = []
    surface = SimpleNamespace(
        session=session,
        realizer=realizer,
        workbench=SimpleNamespace(canvas=canvas),
        can_use_overlays=lambda: True,
        style_banner=lambda: None,
        sync_overlay_toggles=synced.append,
        set_overlay_status=status.append,
        show_plain=lambda text: None,
    )
    canvas.at = {x: (session.document.by_name(name)[0] if name else None) for x, name in at.items()}
    return overlays.OverlayModes(surface), session, realizer, canvas, links, status, synced


def test_a_registered_overlay_opens_like_the_built_in_ones_and_one_is_open_at_a_time(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    del qapp
    modes, session, realizer, canvas, links, status, synced = _modes(monkeypatch, BARE, {}, tmp_path)
    try:
        assert modes.open("nonsense") is False
        assert modes.open("probe") is True and modes.active == "probe"
        assert canvas.banner is not None and canvas.banner[:3] == ("buddy", "Probe", "Drag from a widget to the widget it should act on.")
        assert "probe_layer" in canvas.layers and canvas.claimer == modes.claim and synced[-1] == "probe"
        assert modes.open("buddies") is True and modes.active == "buddies"
        assert "probe_layer" not in canvas.layers
        modes.toggle("buddies")
        assert modes.active == "" and canvas.banner is None
    finally:
        modes.dispose()
        realizer.dispose()
        session.dispose()


def test_link_by_keyboard_start_pick_receiver_home_for_the_form_and_esc_cancels_in_two_steps(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    del qapp
    modes, session, realizer, canvas, links, status, _synced = _modes(monkeypatch, BARE, {}, tmp_path)
    try:
        document = session.document
        ok, email, root = document.by_name("ok")[0], document.by_name("email")[0], document.root.id
        modes.open("probe")
        session.selection.set((ok,), current=ok, source=SelectionSource.CANVAS)
        assert modes.claim(_key(Qt.Key.Key_Return)) is True and modes.link_source == ok
        assert status[-1] == "from ok" and links == []
        session.selection.set((email,), current=email, source=SelectionSource.CANVAS)
        assert canvas.layers["probe_layer"].candidate == email  # type: ignore[attr-defined]  # the selected widget is the receiver
        assert modes.claim(_key(Qt.Key.Key_Return)) is True
        assert links == [(ok, email)] and modes.link_source is None
        # Home picks the form.
        session.selection.set((ok,), current=ok, source=SelectionSource.CANVAS)
        modes.claim(_key(Qt.Key.Key_Return))
        modes.claim(_key(Qt.Key.Key_Home))
        modes.claim(_key(Qt.Key.Key_Return))
        assert links[-1] == (ok, root)
        # Esc: the first cancels the link, the second closes the overlay. Nothing was linked.
        session.selection.set((ok,), current=ok, source=SelectionSource.CANVAS)
        modes.claim(_key(Qt.Key.Key_Return))
        modes.claim(_key(Qt.Key.Key_Escape))
        assert modes.link_source is None and modes.active == "probe" and len(links) == 2
        modes.claim(_key(Qt.Key.Key_Escape))
        assert modes.active == ""
    finally:
        modes.dispose()
        realizer.dispose()
        session.dispose()


def test_link_by_drag_ends_on_widget_form_or_owner_and_a_press_on_nothing_starts_nothing(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    del qapp
    modes, session, realizer, canvas, links, _status, _synced = _modes(
        monkeypatch, LAID, {10: "ok", 40: "ok", 60: None, 90: "verticalLayout", 120: "Form"}, tmp_path
    )
    try:
        ok = session.document.by_name("ok")[0]
        root = session.document.root.id
        layout = session.document.by_name("verticalLayout")[0]
        canvas.at[90] = layout
        modes.open("probe")

        def drag(start: int, end: int, cancel: bool = False) -> None:
            modes.claim(_mouse(QEvent.Type.MouseButtonPress, start))
            modes.claim(_mouse(QEvent.Type.MouseMove, start + 2))
            modes.claim(_mouse(QEvent.Type.MouseMove, end))
            if cancel:
                modes.escape()
            modes.claim(_mouse(QEvent.Type.MouseButtonRelease, end))

        drag(10, 60)  # the page background: the form
        drag(10, 90)  # a layout: the widget that owns it
        drag(10, 40)  # the sender itself, after leaving it
        assert links == [(ok, root), (ok, root), (ok, ok)]
        drag(10, 60, cancel=True)  # Esc during the drag cancels
        assert len(links) == 3
        drag(60, 10)  # nothing under the press starts nothing
        modes.claim(_mouse(QEvent.Type.MouseButtonPress, 120))  # the form itself is not a sender
        modes.claim(_mouse(QEvent.Type.MouseButtonRelease, 120))
        assert len(links) == 3 and modes.link_source is None
    finally:
        modes.dispose()
        realizer.dispose()
        session.dispose()


def test_a_kind_added_from_a_new_file_gets_a_toolbar_toggle(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del qapp
    package = make_package(
        tmp_path,
        monkeypatch,
        "m6_overlay_probe",
        {
            "link": """
                from app.features.form_builder.integration.overlay_ext import OverlayKind, ToggleSpec
                def register(registry):
                    registry.add(OverlayKind("probe", "Probe", "Text", "probe_layer", toggle=ToggleSpec("Probe", "Probe overlay")))
            """
        },
    )
    try:
        registry = load_overlay_kinds(package)
        monkeypatch.setattr("app.features.form_builder.integration.workbench.overlay_kinds", lambda: registry)
        from app.features.form_builder.integration.workbench import FormToolbar

        parent = QWidget()
        toolbar = FormToolbar(parent, on_design=lambda: None, on_xml=lambda on: None, on_undo=lambda: None, on_redo=lambda: None)
        toggle = toolbar.overlay_toggles["probe"]
        assert toggle.isCheckable() and toggle.text() == "Probe" and toggle.objectName() == "formBuilder.overlay.probe"
        row = toolbar.layout()
        positions = [row.indexOf(w) for w in (toolbar.buddies, toggle, toolbar.undo)]
        assert positions == sorted(positions)
        parent.deleteLater()
    finally:
        forget_package("m6_overlay_probe")
