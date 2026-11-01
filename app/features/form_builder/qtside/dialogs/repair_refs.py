"""One row per widget name a rule still uses after a rename outside Code Studio."""

from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from app.features.form_builder.engine.logic.repair import RepairFix
from app.features.form_builder.engine.ui4.document import UiDocument
from app.qt.QtGui import QFont
from app.qt.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

_RULE_WORDS = {
    "cbcsEnabledWhen": "Enabled when",
    "cbcsVisibleWhen": "Visible when",
    "cbcsReadOnlyWhen": "Read-only when",
    "cbcsValue": "Value",
    "cbcsDefault": "Default",
}

_SENTENCE = "These rules use names that no longer exist. Pick the widget each name should point at."


class RepairDialog(QDialog):
    def __init__(
        self,
        fixes: Sequence[RepairFix],
        parent: Optional[QWidget] = None,
        document: Optional[UiDocument] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.repairRefs")
        self.setWindowTitle("Repair references")
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        title = QLabel("Repair references", self)
        title.setObjectName("formBuilder.repairTitle")
        font = QFont(title.font())
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)
        sentence = QLabel(_SENTENCE, self)
        sentence.setObjectName("formBuilder.repairSentence")
        sentence.setWordWrap(True)
        layout.addWidget(sentence)
        self._uses: List[QLabel] = []
        self._combos: List[Tuple[str, QComboBox]] = []
        order: List[str] = []
        choices: Dict[str, List[str]] = {}
        for fix in fixes:
            bucket = choices.setdefault(fix.missing, [])
            for name in fix.candidates:
                if name not in bucket:
                    bucket.append(name)
            if fix.missing not in order:
                order.append(fix.missing)
        for missing in order:
            row = QHBoxLayout()
            label = QLabel(missing, self)
            label.setObjectName("formBuilder.repairName.%s" % missing)
            arrow = QLabel("\u2192", self)
            arrow.setObjectName("formBuilder.repairArrow.%s" % missing)
            combo = QComboBox(self)
            combo.setObjectName("formBuilder.repairChoice.%s" % missing)
            combo.setMinimumWidth(220)
            names = choices[missing]
            if len(names) != 1:
                combo.addItem("", None)
            for name in names:
                combo.addItem(_choice_label(document, name), name)
            if len(names) == 1:
                combo.setCurrentIndex(0)
            combo.currentIndexChanged.connect(self._sync)
            row.addWidget(label)
            row.addWidget(arrow)
            row.addWidget(combo, 1)
            layout.addLayout(row)
            uses = QLabel(_uses_line(fixes, missing, document), self)
            uses.setObjectName("formBuilder.repairUses.%s" % missing)
            uses.setProperty("repairUses", True)
            uses.setWordWrap(True)
            layout.addWidget(uses)
            self._uses.append(uses)
            self._combos.append((missing, combo))
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        accept = buttons.button(QDialogButtonBox.StandardButton.Ok)
        accept.setText("Repair")
        accept.setObjectName("formBuilder.repairAccept")
        accept.setDefault(True)
        accept.setAutoDefault(True)
        cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel.setText("Cancel")
        cancel.setObjectName("formBuilder.repairCancel")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._accept = accept
        self._sync()

    def apply_chrome(self, chrome: object) -> None:
        panel = getattr(chrome, "panel", "") or getattr(chrome, "window", "")
        text = getattr(chrome, "text", "")
        border = getattr(chrome, "border", "")
        field = getattr(chrome, "input", "")
        muted = getattr(chrome, "muted", "") or text
        accent = getattr(chrome, "accent", "") or text
        on_accent = getattr(chrome, "on_accent", "") or text
        focus = getattr(chrome, "focus_width", 1) or 1
        if not panel or not text or not field or not border:
            return
        self.setStyleSheet(
            "QDialog#formBuilder\\.repairRefs { background: %s; color: %s; }"
            "QLabel { color: %s; background: transparent; }"
            "QLabel[repairUses=\"true\"] { color: %s; }"
            "QComboBox { color: %s; background: %s; border: 1px solid %s; padding: 2px 6px; }"
            "QPushButton { color: %s; background: %s; border: 1px solid %s; padding: 4px 12px; }"
            "QPushButton:default { color: %s; background: %s; }"
            "QPushButton:focus { border: %dpx solid %s; }"
            % (
                panel,
                text,
                text,
                muted,
                text,
                field,
                border,
                text,
                field,
                border,
                on_accent,
                accent,
                int(focus),
                accent,
            )
        )

    def chosen(self) -> Mapping[str, str]:
        picked: Dict[str, str] = {}
        for missing, combo in self._combos:
            name = combo.currentData()
            if isinstance(name, str) and name:
                picked[missing] = name
        return picked

    def _sync(self, *_args: object) -> None:
        ready = True
        for _missing, combo in self._combos:
            name = combo.currentData()
            if not isinstance(name, str) or not name:
                ready = False
        self._accept.setEnabled(ready)


def _choice_label(document: Optional[UiDocument], name: str) -> str:
    if document is None:
        return name
    from app.features.form_builder.engine.query.tab_stops import display_name
    from app.features.form_builder.qtside.inspector.words import class_words

    found = document.by_name(name)
    node = document.get(found[0]) if found else None
    shown = display_name(document, name) or name
    kind = ""
    class_name = getattr(node, "class_name", "") if node is not None else ""
    if isinstance(class_name, str) and class_name:
        kind = class_words(class_name).friendly
    if kind:
        return "%s \u00b7 %s \u00b7 %s" % (name, shown, kind)
    return "%s \u00b7 %s" % (name, shown)


def _uses_line(fixes: Sequence[RepairFix], missing: str, document: Optional[UiDocument]) -> str:
    from app.features.form_builder.engine.query.tab_stops import display_name

    parts: List[str] = []
    for fix in fixes:
        if fix.missing != missing:
            continue
        words = _RULE_WORDS.get(fix.key, fix.key)
        owner = fix.owner
        if document is not None and fix.owner:
            owner = display_name(document, fix.owner) or fix.owner
        parts.append("%s on %s" % (words, owner))
    return ", ".join(parts)
