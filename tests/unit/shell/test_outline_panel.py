"""Unit tests for the OutlinePanel widget."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtCore import QRect  # noqa: E402
from PySide2.QtGui import QPainter, QPixmap  # noqa: E402

from app.intelligence.outline_service import OutlineSymbol  # noqa: E402
from app.shell.outline_panel import (  # noqa: E402
    SORT_CATEGORY,
    SORT_NAME,
    SORT_POSITION,
    OutlinePanel,
    _OutlineHeaderBar,
    _OutlineTreeWidget,
)

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def _ensure_qapp(qapp):  # type: ignore[no-untyped-def]
    yield qapp


def _class_with_two_methods() -> tuple[OutlineSymbol, ...]:
    method_a = OutlineSymbol(
        name="alpha",
        qualified_name="Thing.alpha",
        kind="method",
        line_number=2,
        end_line_number=3,
        detail="(self)",
    )
    method_b = OutlineSymbol(
        name="beta",
        qualified_name="Thing.beta",
        kind="method",
        line_number=4,
        end_line_number=5,
        detail="(self)",
    )
    klass = OutlineSymbol(
        name="Thing",
        qualified_name="Thing",
        kind="class",
        line_number=1,
        end_line_number=5,
        children=(method_a, method_b),
    )
    return (klass,)


def test_set_outline_renders_hierarchy(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = OutlinePanel()
    panel.set_outline(_class_with_two_methods(), "/project/thing.py")

    tree = panel.tree_widget()
    assert tree.topLevelItemCount() == 1
    top = tree.topLevelItem(0)
    assert top.text(0).startswith("Thing")
    assert top.childCount() == 2
    assert top.child(0).text(0).startswith("alpha")
    assert top.child(1).text(0).startswith("beta")


def test_set_outline_preserves_expansion_state_on_same_file(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = OutlinePanel()
    panel.set_outline(_class_with_two_methods(), "/project/thing.py")
    panel.tree_widget().topLevelItem(0).setExpanded(True)

    method_c = OutlineSymbol(
        name="gamma",
        qualified_name="Thing.gamma",
        kind="method",
        line_number=6,
        end_line_number=7,
    )
    original_children = panel.symbols()[0].children
    klass = OutlineSymbol(
        name="Thing",
        qualified_name="Thing",
        kind="class",
        line_number=1,
        end_line_number=7,
        children=(*original_children, method_c),
    )
    panel.set_outline((klass,), "/project/thing.py")

    assert panel.tree_widget().topLevelItem(0).isExpanded()
    assert panel.tree_widget().topLevelItem(0).childCount() == 3


def test_set_outline_resets_expansion_when_file_changes(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = OutlinePanel()
    panel.set_outline(_class_with_two_methods(), "/project/thing.py")
    panel.tree_widget().topLevelItem(0).setExpanded(True)

    panel.set_outline(_class_with_two_methods(), "/project/other.py")

    assert not panel.tree_widget().topLevelItem(0).isExpanded()


def test_highlight_symbol_at_line_selects_innermost(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = OutlinePanel()
    panel.set_outline(_class_with_two_methods(), "/project/thing.py")
    panel.tree_widget().topLevelItem(0).setExpanded(True)

    panel.highlight_symbol_at_line(4)

    current = panel.tree_widget().currentItem()
    assert current is not None
    assert current.text(0).startswith("beta")


def test_highlight_symbol_at_line_clears_when_outside(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = OutlinePanel()
    panel.set_outline(_class_with_two_methods(), "/project/thing.py")
    panel.tree_widget().topLevelItem(0).setExpanded(True)
    panel.tree_widget().setCurrentItem(panel.tree_widget().topLevelItem(0).child(0))

    panel.highlight_symbol_at_line(999)

    assert panel.tree_widget().selectedItems() == []


def test_symbol_activated_emits_file_and_line_on_click(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = OutlinePanel()
    panel.set_outline(_class_with_two_methods(), "/project/thing.py")

    received: list[tuple[str, int]] = []
    panel.symbol_activated.connect(lambda fp, ln: received.append((fp, ln)))

    tree = panel.tree_widget()
    top = tree.topLevelItem(0)
    tree.itemClicked.emit(top, 0)

    assert received == [("/project/thing.py", 1)]


def test_set_unsupported_language_shows_placeholder(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = OutlinePanel()
    panel.set_outline(_class_with_two_methods(), "/project/thing.py")

    panel.set_unsupported_language("javascript")

    assert panel._stack_layout.currentWidget() == panel.empty_label()
    assert "javascript" in panel.empty_label().text().lower()


def test_clear_resets_state(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = OutlinePanel()
    panel.set_outline(_class_with_two_methods(), "/project/thing.py")

    panel.clear()

    assert panel.tree_widget().topLevelItemCount() == 0
    assert panel.symbols() == ()
    assert panel.current_file_path() is None
    assert panel._stack_layout.currentWidget() == panel.empty_label()


def test_set_outline_with_no_symbols_shows_empty_state(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = OutlinePanel()
    panel.set_outline((), "/project/empty.py")

    assert panel._stack_layout.currentWidget() == panel.empty_label()
    assert "No symbols" in panel.empty_label().text()


def _mixed_top_level_symbols() -> tuple[OutlineSymbol, ...]:
    func = OutlineSymbol(
        name="zeta",
        qualified_name="zeta",
        kind="function",
        line_number=1,
        end_line_number=2,
    )
    klass = OutlineSymbol(
        name="Apple",
        qualified_name="Apple",
        kind="class",
        line_number=4,
        end_line_number=10,
    )
    constant = OutlineSymbol(
        name="MAX",
        qualified_name="MAX",
        kind="constant",
        line_number=12,
        end_line_number=12,
    )
    helper = OutlineSymbol(
        name="alpha_helper",
        qualified_name="alpha_helper",
        kind="function",
        line_number=14,
        end_line_number=15,
    )
    return (func, klass, constant, helper)


def test_set_collapsed_constrains_height_and_emits_signal(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = OutlinePanel()
    panel.set_outline(_class_with_two_methods(), "/project/thing.py")
    received: list[bool] = []
    panel.collapsed_changed.connect(lambda v: received.append(v))

    panel.set_collapsed(True)

    assert panel.is_collapsed() is True
    assert panel._stack_container.isHidden() is True
    header_h = panel._collapsed_header_height()
    assert header_h >= _OutlineHeaderBar.MIN_HEADER_HEIGHT
    assert panel.maximumHeight() == header_h
    assert panel.minimumHeight() == header_h
    assert received == [True]

    # Calling again must be a no-op and not emit.
    panel.set_collapsed(True)
    assert received == [True]


def test_collapsed_header_property_set_for_styling(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = OutlinePanel()
    header = panel.header_bar()

    assert bool(header.property("collapsed")) is False

    panel.set_collapsed(True)
    assert bool(header.property("collapsed")) is True

    panel.set_collapsed(False)
    assert bool(header.property("collapsed")) is False


def test_set_collapsed_false_restores_body(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = OutlinePanel()
    panel.set_outline(_class_with_two_methods(), "/project/thing.py")
    panel.set_collapsed(True)

    panel.set_collapsed(False)

    assert panel.is_collapsed() is False
    assert panel._stack_container.isHidden() is False
    assert panel.maximumHeight() == 16777215


def test_set_sort_mode_name_orders_top_level_alphabetically(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = OutlinePanel()
    panel.set_outline(_mixed_top_level_symbols(), "/project/sorted.py")

    panel.set_sort_mode(SORT_NAME)

    tree = panel.tree_widget()
    names = [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]
    assert names == ["alpha_helper", "Apple", "MAX", "zeta"]


def test_set_sort_mode_category_groups_by_kind(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = OutlinePanel()
    panel.set_outline(_mixed_top_level_symbols(), "/project/sorted.py")

    panel.set_sort_mode(SORT_CATEGORY)

    tree = panel.tree_widget()
    names = [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]
    # Class first, then constant, then functions (alphabetical within a group).
    assert names == ["Apple", "MAX", "alpha_helper", "zeta"]


def test_set_sort_mode_position_restores_source_order(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = OutlinePanel()
    panel.set_outline(_mixed_top_level_symbols(), "/project/sorted.py")
    panel.set_sort_mode(SORT_NAME)

    panel.set_sort_mode(SORT_POSITION)

    tree = panel.tree_widget()
    names = [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]
    assert names == ["zeta", "Apple", "MAX", "alpha_helper"]


def test_set_sort_mode_emits_signal_only_on_change(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = OutlinePanel()
    panel.set_outline(_mixed_top_level_symbols(), "/project/sorted.py")
    received: list[str] = []
    panel.sort_mode_changed.connect(lambda mode: received.append(mode))

    panel.set_sort_mode(SORT_NAME)
    panel.set_sort_mode(SORT_NAME)

    assert received == [SORT_NAME]


def test_set_sort_mode_invalid_falls_back_to_position(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = OutlinePanel()
    panel.set_outline(_mixed_top_level_symbols(), "/project/sorted.py")

    panel.set_sort_mode("nonsense")

    assert panel.sort_mode() == SORT_POSITION


def test_set_filter_text_hides_non_matching_and_expands_parents(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = OutlinePanel()
    panel.set_outline(_class_with_two_methods(), "/project/thing.py")

    panel.set_filter_text("alpha")

    tree = panel.tree_widget()
    top = tree.topLevelItem(0)
    assert top.isHidden() is False
    assert top.isExpanded() is True
    assert top.child(0).isHidden() is False
    assert top.child(1).isHidden() is True


def test_clearing_filter_restores_prior_visibility_and_expansion(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = OutlinePanel()
    panel.set_outline(_class_with_two_methods(), "/project/thing.py")
    tree = panel.tree_widget()
    top = tree.topLevelItem(0)
    top.setExpanded(False)

    panel.set_filter_text("beta")
    assert top.isExpanded() is True

    panel.set_filter_text("")

    assert top.isHidden() is False
    assert top.child(0).isHidden() is False
    assert top.child(1).isHidden() is False
    assert top.isExpanded() is False


def test_collapse_all_and_expand_all(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = OutlinePanel()
    panel.set_outline(_class_with_two_methods(), "/project/thing.py")
    panel.expand_all()
    assert panel.tree_widget().topLevelItem(0).isExpanded() is True

    panel.collapse_all()
    assert panel.tree_widget().topLevelItem(0).isExpanded() is False


def test_tree_widget_is_outline_tree_with_chevrons(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = OutlinePanel()
    panel.set_outline(_class_with_two_methods(), "/project/thing.py")
    tree = panel.tree_widget()
    assert isinstance(tree, _OutlineTreeWidget)

    parent_item = tree.topLevelItem(0)
    parent_item.setExpanded(True)
    parent_index = tree.indexFromItem(parent_item)
    leaf_index = tree.indexFromItem(parent_item.child(0))

    pixmap = QPixmap(64, 64)
    pixmap.fill()
    painter = QPainter(pixmap)
    try:
        # Should not raise for either branch (with-children or leaf).
        tree.drawBranches(painter, QRect(0, 0, 32, 16), parent_index)
        tree.drawBranches(painter, QRect(0, 16, 32, 16), leaf_index)
    finally:
        painter.end()

    # Theme color hook updates the cached chevron color.
    tree.set_chevron_color("#123456")
    assert tree.chevron_color() == "#123456"


def test_set_follow_cursor_emits_signal(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = OutlinePanel()
    received: list[bool] = []
    panel.follow_cursor_changed.connect(lambda v: received.append(v))

    panel.set_follow_cursor(False)
    assert panel.is_follow_cursor_enabled() is False
    assert received == [False]

    panel.set_follow_cursor(False)
    assert received == [False]

    panel.set_follow_cursor(True)
    assert received == [False, True]


def test_set_filter_visible_shows_filter_row_when_expanded(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = OutlinePanel()

    panel.set_filter_visible(True)

    assert panel.is_filter_visible() is True
    assert panel.filter_row().isHidden() is False


def test_set_filter_visible_does_not_show_row_while_collapsed(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = OutlinePanel()
    panel.set_collapsed(True)

    panel.set_filter_visible(True)

    assert panel.is_filter_visible() is True
    # Hidden because the whole body is collapsed.
    assert panel.filter_row().isHidden() is True


def test_header_chevron_click_toggles_collapsed(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = OutlinePanel()
    received: list[bool] = []
    panel.collapsed_changed.connect(lambda v: received.append(v))

    panel.header_bar().chevron_button().click()

    assert received == [True]
    assert panel.is_collapsed() is True

    panel.header_bar().chevron_button().click()
    assert received == [True, False]


def test_hide_requested_emitted_from_more_menu(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = OutlinePanel()
    received: list[bool] = []
    panel.hide_requested.connect(lambda: received.append(True))

    panel.header_bar().hide_clicked.emit()

    assert received == [True]
