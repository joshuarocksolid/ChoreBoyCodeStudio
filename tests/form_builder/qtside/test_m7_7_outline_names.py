# pyright: reportAttributeAccessIssue=false
"""The outline leads with the owner's word and keeps the object name beside it."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.qt.QtGui import QImage
from app.qt.QtWidgets import QApplication, QStyleOptionViewItem, QTreeWidgetItem
from tests.form_builder.qtside.test_m7_2b1_shots import _pump
from tests.form_builder.qtside.test_outline_pane import _Recorder

pytestmark = [pytest.mark.unit]


def _item(tree: object, object_name: str) -> QTreeWidgetItem:
    role = int(__import__("app.qt.QtCore", fromlist=["Qt"]).Qt.UserRole) + 1

    def walk(item: QTreeWidgetItem) -> QTreeWidgetItem:
        caption = str(item.data(0, role) or "")
        if item.text(0) == object_name or caption == object_name:
            return item
        for index in range(item.childCount()):
            found = walk(item.child(index))
            if found is not None:
                return found
        return None  # type: ignore[return-value]

    for index in range(tree.topLevelItemCount()):  # type: ignore[attr-defined]
        found = walk(tree.topLevelItem(index))  # type: ignore[attr-defined]
        if found is not None:
            return found
    raise AssertionError(object_name)


def _painted(tree: object, item: QTreeWidgetItem, width: int = 0) -> list:
    tree.setCurrentItem(item)  # type: ignore[attr-defined]
    index = tree.currentIndex()  # type: ignore[attr-defined]
    option = QStyleOptionViewItem()
    option.rect = tree.visualItemRect(item)  # type: ignore[attr-defined]
    if width > 0:
        option.rect.setWidth(width)
    option.font = tree.font()  # type: ignore[attr-defined]
    option.fontMetrics = tree.fontMetrics()  # type: ignore[attr-defined]
    option.palette = tree.palette()  # type: ignore[attr-defined]
    if width <= 0:
        option.widget = tree  # type: ignore[assignment]
    image = QImage(max(tree.viewport().width(), width), tree.viewport().height(), QImage.Format.Format_ARGB32)  # type: ignore[attr-defined]
    painter = _Recorder(image)
    try:
        tree.itemDelegate().paint(painter, option, index)  # type: ignore[attr-defined]
    finally:
        painter.end()
    return [(rect, text) for rect, text in painter.drawn if len(text) > 1]


def _painted_at(tree: object, item: QTreeWidgetItem, width: int) -> list:
    return _painted(tree, item, width)


def test_discount_rate_keeps_both_names_at_the_default_split(qapp: QApplication, tmp_path: Path) -> None:
    from app.qt.QtCore import Qt
    from tests.form_builder.qtside.test_m3_keyboard_scripts import _close
    from tests.form_builder.qtside.test_m7_2b1_k27 import _session

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    window, kb, guard, _path = _session(tmp_path, qapp)
    try:
        window.resize(1400, 900)
        _pump(qapp)
        outline = kb.surface.workbench.outline
        tree = outline.tree
        item = _item(tree, "discountEdit")
        caption_role = int(Qt.UserRole) + 1
        assert item.text(0) == "Discount rate"
        assert str(item.data(0, caption_role) or "") == "discountEdit"
        tip = item.toolTip(0)
        assert "Line edit" in tip
        assert "discountEdit" in tip
        assert "Discount rate" not in tip or tip.index("Line edit") >= 0
        drawn = _painted(tree, item)
        texts = [text for _rect, text in drawn]
        assert texts[0] == "Discount rate", texts
        assert any(text.startswith("disc") for text in texts[1:]), texts
        wide = _painted_at(tree, item, 320)
        wide_texts = [text for _rect, text in wide]
        assert "Discount rate" in wide_texts and "discountEdit" in wide_texts, wide_texts
        node = kb.session.document.by_name("discountEdit")[0]
        outline.begin_rename(node)
        _pump(qapp)
        assert outline._editor.text() == "discountEdit"  # noqa: SLF001
        outline.end_rename()
        outline.apply_filter("Discount rate", False, None)
        _pump(qapp)
        assert not item.isHidden()
        outline.apply_filter("discountEdit", False, None)
        _pump(qapp)
        assert not item.isHidden()
        label = _item(tree, "rateLabel")
        assert label.text(0) == "Discount rate"
    finally:
        _close(window, qapp, guard)
