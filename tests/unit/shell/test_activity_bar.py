"""Unit tests for the ActivityBar widget."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.shell.activity_bar import ActivityBar


@pytest.fixture
def _ensure_qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


@pytest.mark.unit
class TestActivityBar:
    def test_add_view_creates_button(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        bar = ActivityBar()
        bar.add_view("explorer", "E", "Explorer")
        assert "explorer" in bar._buttons
        assert bar._buttons["explorer"].text() == "E"

    def test_first_view_is_active(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        bar = ActivityBar()
        bar.add_view("explorer", "E", "Explorer")
        bar.add_view("search", "S", "Search")
        assert bar.active_view() == "explorer"
        assert bar._buttons["explorer"].isChecked()
        assert not bar._buttons["search"].isChecked()

    def test_set_active_view(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        bar = ActivityBar()
        bar.add_view("explorer", "E", "Explorer")
        bar.add_view("search", "S", "Search")
        bar.set_active_view("search")
        assert bar.active_view() == "search"
        assert not bar._buttons["explorer"].isChecked()
        assert bar._buttons["search"].isChecked()

    def test_view_changed_signal(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        bar = ActivityBar()
        bar.add_view("explorer", "E", "Explorer")
        bar.add_view("search", "S", "Search")
        changes: list[str] = []
        bar.view_changed.connect(lambda vid: changes.append(vid))
        bar._on_button_clicked("search")
        assert changes == ["search"]
        assert bar.active_view() == "search"

    def test_clicking_same_view_still_emits(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        bar = ActivityBar()
        bar.add_view("explorer", "E", "Explorer")
        changes: list[str] = []
        bar.view_changed.connect(lambda vid: changes.append(vid))
        bar._on_button_clicked("explorer")
        assert changes == ["explorer"]

    def test_button_click_triggers_view_changed(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        """Simulate an actual QToolButton click to exercise the signal→lambda→handler chain.

        This guards against the PySide2 clicked() zero-arg overload issue where a
        lambda with a required 'checked' parameter would raise TypeError at runtime.
        """
        bar = ActivityBar()
        bar.add_view("explorer", "E", "Explorer")
        bar.add_view("search", "S", "Search")
        changes: list[str] = []
        bar.view_changed.connect(lambda vid: changes.append(vid))
        bar._buttons["search"].click()
        assert changes == ["search"]
        assert bar.active_view() == "search"

    def test_add_view_with_icon_sets_icon(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from PySide2.QtGui import QIcon, QPixmap

        bar = ActivityBar()
        icon = QIcon(QPixmap(20, 20))
        bar.add_view("explorer", "E", "Explorer", icon=icon)
        btn = bar._buttons["explorer"]
        assert not btn.icon().isNull()
        assert btn.text() == ""

    def test_add_view_without_icon_uses_text(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        bar = ActivityBar()
        bar.add_view("explorer", "E", "Explorer")
        btn = bar._buttons["explorer"]
        assert btn.icon().isNull()
        assert btn.text() == "E"

    def test_set_view_icon_updates_existing_button_icon(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from PySide2.QtGui import QIcon, QPixmap

        bar = ActivityBar()
        bar.add_view("explorer", "E", "Explorer")
        icon = QIcon(QPixmap(20, 20))

        bar.set_view_icon("explorer", icon)

        assert not bar._buttons["explorer"].icon().isNull()

    def test_set_view_icon_ignores_missing_view_id(self, _ensure_qapp) -> None:  # type: ignore[no-untyped-def]
        from PySide2.QtGui import QIcon, QPixmap

        bar = ActivityBar()
        bar.add_view("explorer", "E", "Explorer")
        icon = QIcon(QPixmap(20, 20))

        bar.set_view_icon("search", icon)

        assert "search" not in bar._buttons
