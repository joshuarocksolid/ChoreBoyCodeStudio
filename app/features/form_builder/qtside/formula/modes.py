"""Builder and formula, one stored string. The editor remains the text."""

from __future__ import annotations

from typing import Optional

from app.qt.QtCore import Qt
from app.qt.QtGui import QKeySequence
from app.qt.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QShortcut,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.features.form_builder.engine.logic.formula.env import SlotKind
from app.features.form_builder.qtside.formula.builder.model import BLOCKED, load_formula
from app.features.form_builder.qtside.formula.builder.view import FormulaBuilder
from app.features.form_builder.qtside.formula.editor import FormulaEditor
from app.features.form_builder.qtside.theme.chrome import FormChrome, link_ink

_VALUE = frozenset({"value", "default"})


def attach_builder(editor: FormulaEditor, layout: QVBoxLayout) -> None:
    """The one hook State uses. Verb pages never call it, so they stay formula fields."""

    if getattr(editor, "_modes", None) is not None:
        layout.addWidget(editor)
        return
    modes = _Modes(editor)
    editor._modes = modes  # type: ignore[attr-defined]
    editor._present_hook = modes.present  # type: ignore[attr-defined]
    editor._reveal_formula = modes.reveal_formula  # type: ignore[attr-defined]
    editor._chrome_hook = modes.apply_chrome  # type: ignore[attr-defined]
    editor._show_hook = modes.on_show_text  # type: ignore[attr-defined]
    layout.addWidget(modes.bar)
    layout.addWidget(modes.builder)
    layout.addWidget(editor)
    editor.textChanged.connect(modes.on_editor_text)


class _Modes:
    def __init__(self, editor: FormulaEditor) -> None:
        self.editor = editor
        self._builder_on = False
        self._fits = True
        self._pushing = False
        self._showing = False
        self.bar = QWidget(editor.parentWidget())
        self.bar.setObjectName("formBuilder.formula.bar")
        self.bar.setMinimumWidth(0)
        column = QVBoxLayout(self.bar)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)
        self._row = QHBoxLayout()
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(4)
        self._row.addStretch(1)
        self.switch = QPushButton("Formula ›", self.bar)
        self.switch.setObjectName("formBuilder.formula.switch")
        self.switch.setProperty("fbLink", True)
        self.switch.setFlat(True)
        self.switch.setCursor(getattr(getattr(Qt, "CursorShape", Qt), "PointingHandCursor"))
        names = getattr(QSizePolicy, "Policy", QSizePolicy)
        self.switch.setSizePolicy(getattr(names, "Maximum"), getattr(names, "Fixed"))
        self.switch.clicked.connect(self._toggle)
        self._row.addWidget(self.switch)
        self.note = QLabel(self.bar)
        self.note.setObjectName("formBuilder.builder.blocked")
        self.note.setWordWrap(True)
        self.note.setMinimumWidth(0)
        self.note.setText(BLOCKED)
        self.note.hide()
        self.note.setSizePolicy(getattr(names, "Ignored"), getattr(names, "Minimum"))
        fitted = self.note.sizePolicy()
        fitted.setHeightForWidth(True)
        self.note.setSizePolicy(fitted)
        column.addLayout(self._row)
        column.addWidget(self.note)
        self.builder = FormulaBuilder(self._on_builder, editor.parentWidget() or self.bar)
        context = getattr(Qt, "WidgetWithChildrenShortcut")
        self._commit = QShortcut(QKeySequence("Ctrl+Return"), self.builder)
        self._commit.setContext(context)
        self._commit.activated.connect(editor.commit_requested)
        self._commit_pad = QShortcut(QKeySequence("Ctrl+Enter"), self.builder)
        self._commit_pad.setContext(context)
        self._commit_pad.activated.connect(editor.commit_requested)
        self._escape = QShortcut(QKeySequence("Esc"), self.builder)
        self._escape.setContext(context)
        self._escape.activated.connect(self._on_escape)

    def present(self) -> None:
        self._paint(take_focus=True)

    def reveal_formula(self) -> None:
        """A key sent at the hidden formula field means the test, or the user, wants that field."""

        self._builder_on = False
        self._paint(take_focus=False)

    def apply_chrome(self, chrome: FormChrome) -> None:
        self.builder.apply_chrome(chrome)
        self.note.setStyleSheet("color: %s; background: transparent;" % chrome.text)
        focus = chrome.focus_width if chrome.focus_width > 0 else 1
        ink = link_ink(chrome)
        self.switch.setStyleSheet(
            "QPushButton { color: %s; background: transparent; border: none; padding: 0;"
            " text-decoration: underline; }"
            "QPushButton:focus { border: %dpx solid %s; }"
            "QPushButton:disabled { color: %s; text-decoration: none; }"
            % (ink, focus, chrome.accent or ink, chrome.muted)
        )

    def on_show_text(self, text: str) -> None:
        self._showing = True
        try:
            self._load(text)
            self._paint(take_focus=True)
        finally:
            self._showing = False

    def on_editor_text(self) -> None:
        if self._pushing or self._showing or self._builder_on:
            return
        if getattr(self.editor, "_mode_silent", False):
            return
        self._fits = self._model_fits(self.editor.toPlainText())
        self._paint(take_focus=False)

    def _toggle(self) -> None:
        if self._builder_on:
            self._builder_on = False
            self._paint(take_focus=True)
            return
        if not self._fits:
            return
        self._load(self.editor.toPlainText())
        self._builder_on = True
        self._paint(take_focus=True)

    def _on_builder(self) -> None:
        if self._showing:
            return
        text = self.builder.draft()
        self._push(text)

    def _on_escape(self) -> None:
        if self.builder.close_popups():
            return
        self.editor.cancel_requested()

    def _load(self, text: str) -> None:
        kind = _kind(self.editor._slot)  # type: ignore[attr-defined]
        env = self.editor._env  # type: ignore[attr-defined]
        self.builder.set_env(env)
        if not kind or env is None:
            self._fits = False
            self._builder_on = False
            return
        model = load_formula(text, env, kind)
        self._fits = model is not None
        if model is None:
            self._builder_on = False
            return
        self._builder_on = True
        self.builder.load(model, kind)

    def _model_fits(self, text: str) -> bool:
        kind = _kind(self.editor._slot)  # type: ignore[attr-defined]
        env = self.editor._env  # type: ignore[attr-defined]
        if not kind or env is None:
            return False
        return load_formula(text, env, kind) is not None

    def _push(self, text: Optional[str]) -> None:
        incomplete = text is None
        self._pushing = True
        try:
            self.editor._builder_incomplete = incomplete  # type: ignore[attr-defined]
            if text is None:
                self.editor._reanalyze()
                return
            if self.editor.toPlainText() != text:
                self.editor.setPlainText(text)
            else:
                self.editor._reanalyze()
            self._fits = True
        finally:
            self._pushing = False
        self._speak()

    def _speak(self) -> None:
        if not self._builder_on:
            return
        spoken = self.builder.spoken()
        if not spoken:
            return
        self.editor._words = spoken  # type: ignore[attr-defined]
        self.editor._publish_status()

    def _home_switch(self) -> None:
        self.builder.release_switch(self.switch)
        self._row.removeWidget(self.switch)
        self.switch.setParent(self.bar)
        self._row.addWidget(self.switch)

    def _paint(self, *, take_focus: bool) -> None:
        self._commit.setEnabled(self._builder_on)
        self._commit_pad.setEnabled(self._builder_on)
        self._escape.setEnabled(self._builder_on)
        focus = QApplication.focusWidget()
        if self._builder_on:
            self.builder.show()
            self.builder.adopt_switch(self.switch)
            # Hide the text field only after focus sits inside the builder.
            # Hiding a focused field moves focus out of State, and State then
            # commits and closes the row. The link moves first, for the same reason.
            in_editor = focus is self.editor or (
                focus is not None and self.editor.isAncestorOf(focus)
            )
            in_bar = focus is self.switch or (focus is not None and self.bar.isAncestorOf(focus))
            if take_focus or in_editor or in_bar:
                self.builder.focus_first()
            self.bar.hide()
            self.editor.hide()
            self.switch.setText("Formula ›")
            self.switch.setEnabled(True)
            self.switch.setToolTip("")
            self.note.hide()
            self._speak()
        else:
            self._home_switch()
            self.bar.show()
            self.editor.show()
            in_builder = focus is self.builder or (
                focus is not None and self.builder.isAncestorOf(focus)
            )
            if take_focus or in_builder:
                self.editor.setFocus()
            self.builder.hide()
            self.switch.setText("‹ Builder")
            self.switch.setEnabled(self._fits)
            self.editor._reanalyze()
            if self._fits:
                self.switch.setToolTip("")
                self.note.hide()
            else:
                self.switch.setToolTip(BLOCKED)
                self.switch.setAccessibleDescription(BLOCKED)
                self.note.show()
                self.editor._words = BLOCKED  # type: ignore[attr-defined]
                self.editor._publish_status()
        self.switch.setAccessibleName(self.switch.text())


def _kind(slot: SlotKind) -> str:
    if slot.name in _VALUE:
        return "value"
    if slot.name == "condition":
        return "condition"
    return ""
