# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false
"""M5.6 overlays: clicks and drags, the marks, the banner, closing rules and the one-editing-mode claim.

The keys-only path is K23 (``test_m5_6_keyboard_k23.py``). These tests use the mouse the
way the spec does (UX-OVL-005, UX-OVL-008) and read the marks the canvas layers draw.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Tuple

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.commands.catalog import InsertFragment  # noqa: E402
from app.features.form_builder.engine.commands.placement import InFormRow  # noqa: E402
from app.features.form_builder.engine.query import tab_stops as q  # noqa: E402
from app.features.form_builder.engine.query.tree import effective_tab_order  # noqa: E402
from app.features.form_builder.engine.ui4.spec import Fragment  # noqa: E402
from app.features.form_builder.qtside.canvas.core.frame import Chip  # noqa: E402
from app.features.form_builder.qtside.canvas.core.overlay import LayerItem  # noqa: E402
from app.qt.QtCore import QPoint, Qt  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import QApplication, QPushButton  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import Kb, _close, _session  # noqa: E402
from tests.form_builder.qtside.test_m5_6_keyboard_k23 import K23_FORM  # noqa: E402
from tests.support.form_builder.command_fixtures import button_spec  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.timeout(300)]


def _canvas(kb: Kb) -> Any:
    return kb.surface.workbench.canvas


def _center(kb: Kb, name: str) -> QPoint:
    document = kb.session.document
    rect = _canvas(kb).viewport_rect((document.by_name(name)[0],))
    assert rect is not None, name
    return rect.center()


def _click(kb: Kb, name: str, *mods: Any) -> None:
    viewport = _canvas(kb).viewport()
    flags = Qt.KeyboardModifier.NoModifier
    for mod in mods:
        flags |= mod
    QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, flags, _center(kb, name))
    kb.pump()


def _drag(kb: Kb, start: QPoint, end: QPoint) -> None:
    viewport = _canvas(kb).viewport()
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(viewport, QPoint((start.x() + end.x()) // 2, (start.y() + end.y()) // 2))
    QTest.mouseMove(viewport, end)
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
    kb.pump()


def _layer_items(kb: Kb, layer: str) -> List[Any]:
    kb.pump()
    return [item for item in _canvas(kb).overlay().items if isinstance(item, LayerItem) and item.layer == layer]


def _open(tmp_path: Path, qapp: QApplication) -> Tuple[Any, Kb, Any]:
    window, kb, guard = _session(tmp_path, qapp, K23_FORM)
    return window, kb, guard


@pytest.mark.parity("R3-10")
def test_clicking_fields_numbers_them_and_shift_click_continues(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _open(tmp_path, qapp)
    try:
        modes = kb.surface.modes
        original = kb.text()
        modes.open("tab_order")
        kb.pump()
        _click(kb, "phoneEdit")
        _click(kb, "nameEdit")
        document = kb.session.document
        assert modes.picked == ("phoneEdit", "nameEdit")
        assert document.tabstops() == ("phoneEdit", "nameEdit", "emailEdit")
        # Shift+click phoneEdit: numbering goes on after it.
        _click(kb, "phoneEdit", Qt.KeyboardModifier.ShiftModifier)
        assert modes.picked == ("phoneEdit",)
        _click(kb, "emailEdit")
        assert document.tabstops() == ("phoneEdit", "emailEdit", "nameEdit")
        # Each click was folded into one undo step while the overlay stayed open.
        kb.session.log.undo()
        assert kb.text() == original
    finally:
        _close(window, qapp, guard)


def test_each_tab_order_badge_sits_on_its_own_widget_with_a_flow_line(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _open(tmp_path, qapp)
    try:
        modes = kb.surface.modes
        modes.open("tab_order")
        items = _layer_items(kb, "tab_order")
        badges = [item for item in items if item.data[0] == "badge"]
        flows = [item for item in items if item.data[0] == "flow"]
        assert sorted(item.data[1] for item in badges) == [1, 2, 3]
        assert len(flows) == 1 and len(flows[0].data[1]) == 2
        document = kb.session.document
        canvas = _canvas(kb)
        frame = canvas.overlay()
        order = effective_tab_order(document)
        boxes = {}
        for name in ("nameEdit", "emailEdit", "phoneEdit"):
            box = canvas.viewport_rect((document.by_name(name)[0],))
            top_left = canvas.mapToScene(box.topLeft())
            bottom_right = canvas.mapToScene(box.bottomRight())
            boxes[name] = (top_left.x(), top_left.y(), bottom_right.x(), bottom_right.y())
        for item in badges:
            assert item.rect.width == 16 and item.rect.height == 16
            own = order[item.data[1] - 1]
            centre_x, centre_y = item.rect.x + 8, item.rect.y + 8
            left, top, right, bottom = boxes[own]
            # Packed rows: every badge sits just inside its own field's top-left corner.
            assert left <= item.rect.x <= left + 4 and top <= item.rect.y <= top + 4, own
            for name, (left, top, right, bottom) in boxes.items():
                if name == own:
                    continue
                overlaps = left < item.rect.x + 16 and item.rect.x < right and top < item.rect.y + 16 and item.rect.y < bottom
                assert not overlaps, "badge %s sits over %s" % (item.data[1], name)
        assert frame is not None
        # The hover chip says which number a click would give.
        modes._hover = "phoneEdit"
        modes._push()
        kb.pump()
        chips = [item for item in _canvas(kb).overlay().items if isinstance(item, Chip) and item.text.startswith("Click to make it")]
        assert [chip.text for chip in chips] == ["Click to make it 1"]
    finally:
        _close(window, qapp, guard)


def test_the_banner_names_the_overlay_pushes_the_page_down_and_offers_reset(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _open(tmp_path, qapp)
    try:
        modes = kb.surface.modes
        canvas = _canvas(kb)
        before = canvas.viewport().y()
        modes.open("tab_order")
        kb.pump()
        banner = canvas.banner
        assert banner.isVisible() and banner.name() == "Tab order"
        assert canvas.viewport().y() >= before + banner.height()
        assert [b.text() for b in banner.findChildren(QPushButton)] == ["Reset to reading order", "Done · Esc"]
        modes.assign("phoneEdit")
        assert kb.session.document.tabstops() is not None
        reset = banner.findChild(QPushButton, "formBuilder.overlayBannerExtra")
        reset.click()
        assert kb.session.document.tabstops() is None
        banner.findChild(QPushButton, "formBuilder.overlayBannerDone").click()
        kb.pump()
        assert modes.active == "" and not banner.isVisible() and canvas.viewport().y() == before
    finally:
        _close(window, qapp, guard)


def test_one_overlay_at_a_time_and_a_tab_switch_closes_it(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _open(tmp_path, qapp)
    try:
        modes = kb.surface.modes
        modes.open("tab_order")
        modes.open("buddies")
        assert modes.active == "buddies"
        assert not kb.surface._toolbar.tab_order.isChecked() and kb.surface._toolbar.buddies.isChecked()
        # Clicking the toggle again closes it.
        kb.surface._toolbar.buddies.click()
        assert modes.active == ""
        modes.open("buddies")
        kb.surface.hide()
        assert modes.active == ""
    finally:
        _close(window, qapp, guard)


@pytest.mark.parity("R3-1")
@pytest.mark.pain("P-13")
def test_a_structural_command_closes_the_overlay_and_the_canvas_has_no_mode(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _open(tmp_path, qapp)
    try:
        modes = kb.surface.modes
        controller = _canvas(kb)._controller
        modes.open("buddies")
        document = kb.session.document
        layout = document.by_name("formLayout")[0]
        kb.session.log.execute(
            InsertFragment(InFormRow(layout, 3, "field", insert_row=True), Fragment(nodes=(button_spec("extra"),)))
        )
        kb.pump()
        assert modes.active == "", "an insert closes the overlay first"
        # P-13: a connection added with a button selected leaves the canvas's state object as it was.
        before = controller._gesture
        extra = document.by_name("extra")[0]
        kb.session.selection.set((extra,), current=extra, source=__import__("app.features.form_builder.engine.query.selection", fromlist=["SelectionSource"]).SelectionSource.PROGRAM)
        from app.features.form_builder.engine.commands.catalog import AddConnection

        kb.session.log.execute(AddConnection("extra", "clicked()", "Contact", "close()"))
        kb.pump()
        assert controller._gesture == before
        assert modes.active == ""
        assert not hasattr(controller, "tool") and not hasattr(controller, "mode")
    finally:
        _close(window, qapp, guard)


@pytest.mark.parity("R3-8")
def test_drag_from_a_label_to_a_field_sets_the_buddy_and_a_link_end_dragged_to_space_clears_it(
    tmp_path: Path, qapp: QApplication
) -> None:
    window, kb, guard = _open(tmp_path, qapp)
    try:
        modes = kb.surface.modes
        document = kb.session.document
        original = kb.text()
        modes.open("buddies")
        kb.pump()
        label = document.by_name("emailLabel")[0]
        _drag(kb, _center(kb, "emailLabel"), _center(kb, "emailEdit"))
        assert q.buddy_of(document, label) == "emailEdit"
        assert kb.session.log.undo_label() == "Set buddy of Email"
        # Click a label, then click a field.
        _click(kb, "phoneLabel")
        assert modes.linking == "phoneLabel"
        _click(kb, "phoneEdit")
        assert q.buddy_of(document, document.by_name("phoneLabel")[0]) == "phoneEdit"
        # Drag the field end of a link to empty space.
        empty = _canvas(kb).viewport_rect((document.root.id,)).bottomRight() - QPoint(6, 6)
        _drag(kb, _center(kb, "emailEdit"), empty)
        assert q.buddy_of(document, label) is None
        modes.escape()
        assert modes.active == ""
        while kb.session.log.can_undo():
            kb.session.log.undo()
        assert kb.text() == original
    finally:
        _close(window, qapp, guard)


def test_buddy_marks_links_start_right_of_the_words_and_unpaired_labels_get_a_ring(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _open(tmp_path, qapp)
    try:
        modes = kb.surface.modes
        document = kb.session.document
        modes.open("buddies")
        modes.set_buddy(document.by_name("emailLabel")[0], "emailEdit")
        items = _layer_items(kb, "buddies")
        links = [item for item in items if item.data[0] == "link"]
        rings = [item for item in items if item.data[0] == "ring"]
        assert len(links) == 1 and len(rings) == 2
        canvas = _canvas(kb)
        label_box = canvas.viewport_rect((document.by_name("emailLabel")[0],))
        label_right = canvas.mapToScene(label_box.topRight()).x()
        field_left = canvas.mapToScene(canvas.viewport_rect((document.by_name("emailEdit")[0],)).topLeft()).x()
        start, end = links[0].data[1][0], links[0].data[1][-1]
        assert start[0] > canvas.mapToScene(label_box.topLeft()).x(), "the link starts after the label's left edge"
        assert start[0] <= label_right + 3 and end[0] <= field_left, "it ends 2 px left of the field: %r" % (end,)
        for ring in rings:
            assert ring.rect.width == 8 and ring.rect.height == 8
        label_left = canvas.mapToScene(canvas.viewport_rect((document.by_name("nameLabel")[0],)).topLeft()).x()
        assert min(ring.rect.x for ring in rings) + 8 <= label_left, "rings sit outside the label"
    finally:
        _close(window, qapp, guard)


def test_pair_labels_pairs_each_form_row_in_one_step_and_says_how_many(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _open(tmp_path, qapp)
    try:
        modes = kb.surface.modes
        original = kb.text()
        modes.open("buddies")
        count = modes.pair_labels()
        assert count == 3
        assert "Paired 3 labels" in kb.surface.editor_status_sentence()
        assert kb.session.log.undo_label() == "Pair labels"
        document = kb.session.document
        assert q.buddy_of(document, document.by_name("nameLabel")[0]) == "nameEdit"
        kb.session.log.undo()
        assert kb.text() == original
    finally:
        _close(window, qapp, guard)


def test_undo_with_the_overlay_open_starts_the_numbering_again(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _open(tmp_path, qapp)
    try:
        modes = kb.surface.modes
        modes.open("tab_order")
        modes.assign("phoneEdit")
        assert kb.session.document.tabstops() == ("phoneEdit", "nameEdit", "emailEdit")
        kb.session.log.undo()
        assert kb.session.document.tabstops() is None
        assert modes.picked == ()
        modes.assign("emailEdit")
        assert kb.session.document.tabstops() == ("emailEdit", "nameEdit", "phoneEdit")
        kb.surface._toolbar.xml.click()
        kb.pump()
        assert modes.active == "", "View XML closes the overlay"
    finally:
        _close(window, qapp, guard)
