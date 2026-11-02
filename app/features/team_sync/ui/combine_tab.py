"""Combine editor tab. Finish stays disabled until every clash is settled."""

from __future__ import annotations

from typing import Callable, Optional

from app.qt.QtCore import Qt, QSize
from app.qt.QtGui import QColor, QFontDatabase, QTextCharFormat, QTextCursor, QTextFormat
from app.qt.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.features.team_sync.api import (
    CLASH_DELETED,
    CLASH_FORM,
    RESOLVE_BOTH,
    RESOLVE_OURS,
    RESOLVE_TEXT_PREFIX,
    RESOLVE_THEIRS,
    Clash,
    CombineState,
)
from app.features.team_sync.ui.form_preview import FormCompare
from app.features.team_sync.ui.ports import SyncPorts
from app.features.team_sync.ui.theme import accent_soft, mine_bg, theirs_bg
from app.features.team_sync.ui.widgets import Avatar
from app.shell.icon_provider import chevron_left_icon, chevron_right_icon, warning_icon
from app.shell.theme_tokens import ShellThemeTokens


def _polish(widget: QWidget) -> None:
    widget.setAttribute(Qt.WA_StyledBackground, True)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class CombineTab(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.teamSync.combineTab")
        self._api = None
        self._ports = SyncPorts()
        self._state: Optional[CombineState] = None
        self._index = 0
        self._on_finished: Optional[Callable[[], None]] = None
        self._on_deleted: Optional[Callable[[Clash], None]] = None
        self._tokens: Optional[ShellThemeTokens] = None
        self._theirs_label = "Theirs"
        self._theirs_id = ""
        self._mine_name = "You"
        self._mine_id = ""
        self._row_ids: list[str] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        header = QWidget(self)
        header.setObjectName("shell.teamSync.combineHeader")
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(12, 8, 12, 8)
        header_row.setSpacing(8)
        self._warning = QLabel(header)
        self._warning.setFixedSize(16, 16)
        self._summary = QLabel("0 of 0 settled", header)
        self._summary.setObjectName("shell.teamSync.combineSummary")
        header_row.addWidget(self._warning)
        header_row.addWidget(self._summary, 1)
        self._prev = QToolButton(header)
        self._prev.setObjectName("shell.teamSync.combinePrev")
        self._prev.setFixedSize(22, 22)
        self._prev.setIconSize(QSize(14, 14))
        self._prev.setToolTip("Previous")
        self._next = QToolButton(header)
        self._next.setObjectName("shell.teamSync.combineNext")
        self._next.setFixedSize(22, 22)
        self._next.setIconSize(QSize(14, 14))
        self._next.setToolTip("Next")
        self._cancel = QPushButton("Cancel", header)
        self._cancel.setObjectName("shell.teamSync.combineCancel")
        self.finish_button = QPushButton("Finish", header)
        self.finish_button.setObjectName("shell.teamSync.combineFinish")
        self.finish_button.setEnabled(False)
        self._prev.clicked.connect(lambda: self._move(-1))
        self._next.clicked.connect(lambda: self._move(1))
        self._cancel.clicked.connect(self._cancel_clicked)
        self.finish_button.clicked.connect(self._finish_clicked)
        header_row.addWidget(self._prev)
        header_row.addWidget(self._next)
        header_row.addWidget(self._cancel)
        header_row.addWidget(self.finish_button)
        root.addWidget(header)

        splitter = QSplitter(Qt.Horizontal, self)
        self._list = QListWidget(splitter)
        self._list.setObjectName("shell.teamSync.combineClashes")
        self._list.currentRowChanged.connect(self._select_row)
        self._detail = QWidget(splitter)
        detail = QVBoxLayout(self._detail)
        detail.setContentsMargins(12, 12, 12, 12)
        detail.setSpacing(10)
        columns = QHBoxLayout()
        columns.setSpacing(10)
        self._ours = self._panel("shell.teamSync.combineOurs", RESOLVE_OURS)
        self._theirs = self._panel("shell.teamSync.combineTheirs", RESOLVE_THEIRS)
        columns.addWidget(self._ours["frame"], 1)
        columns.addWidget(self._theirs["frame"], 1)
        detail.addLayout(columns)
        result = QFrame(self._detail)
        result.setObjectName("shell.teamSync.combineResult")
        result_layout = QVBoxLayout(result)
        result_layout.setContentsMargins(0, 0, 0, 0)
        result_layout.setSpacing(0)
        result_head = QHBoxLayout()
        result_head.setContentsMargins(8, 6, 8, 6)
        result_title = QLabel("Result", result)
        result_title.setObjectName("shell.teamSync.combineSummary")
        result_head.addWidget(result_title)
        result_head.addStretch(1)
        self._both = QPushButton("Both", result)
        self._both.setObjectName("shell.teamSync.combineBoth")
        self._edit = QPushButton("Edit", result)
        self._edit.setObjectName("shell.teamSync.combineEdit")
        self._both.clicked.connect(lambda: self.settle_current(RESOLVE_BOTH))
        self._edit.clicked.connect(self._edit_result)
        result_head.addWidget(self._both)
        result_head.addWidget(self._edit)
        result_layout.addLayout(result_head)
        self._placeholder = QLabel("Choose a version above", result)
        self._placeholder.setObjectName("shell.teamSync.combinePlaceholder")
        self._placeholder.setContentsMargins(10, 8, 10, 8)
        result_layout.addWidget(self._placeholder)
        self._result = QPlainTextEdit(result)
        self._result.setObjectName("shell.teamSync.combineCode")
        self._result.setReadOnly(True)
        self._result.setFrameStyle(QFrame.NoFrame)
        result_layout.addWidget(self._result)
        detail.addWidget(result)
        self._forms = FormCompare(self._detail)
        self._forms.hide()
        detail.addWidget(self._forms)
        splitter.addWidget(self._list)
        splitter.addWidget(self._detail)
        splitter.setSizes([240, 640])
        root.addWidget(splitter, 1)
        self._mono(self._result)

    def _panel(self, object_name: str, resolution: str) -> dict:
        frame = QFrame(self._detail)
        frame.setObjectName(object_name)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        head = QHBoxLayout()
        head.setContentsMargins(8, 6, 8, 6)
        head.setSpacing(6)
        avatar = Avatar("", "", frame, size=18)
        title = QLabel("", frame)
        title.setObjectName("shell.teamSync.combineSummary")
        use = QPushButton("Use This", frame)
        use.setObjectName("shell.teamSync.combineUse")
        use.clicked.connect(lambda _checked=False, choice=resolution: self.settle_current(choice))
        head.addWidget(avatar)
        head.addWidget(title, 1)
        head.addWidget(use)
        layout.addLayout(head)
        body = QPlainTextEdit(frame)
        body.setObjectName("shell.teamSync.combineCode")
        body.setReadOnly(True)
        body.setFrameStyle(QFrame.NoFrame)
        self._mono(body)
        layout.addWidget(body, 1)
        return {"frame": frame, "avatar": avatar, "title": title, "body": body, "use": use}

    def _mono(self, editor: QPlainTextEdit) -> None:
        font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        font.setPixelSize(12)
        editor.setFont(font)
        editor.document().setDefaultFont(font)

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self._tokens = tokens
        color = tokens.text_primary
        self._prev.setIcon(chevron_left_icon(color))
        self._next.setIcon(chevron_right_icon(color))
        self._warning.setPixmap(warning_icon(tokens.diag_warning_color or "#D97706").pixmap(16, 16))
        self._ours["title"].setText("Yours")
        self._theirs["title"].setText(self._theirs_label)
        _polish(self)
        self._paint_current()

    def open_state(
        self,
        api: object,
        ports: object,
        *,
        on_finished: Callable[[], None],
        on_deleted: Callable[[Clash], None],
        tokens: Optional[ShellThemeTokens] = None,
        theirs_label: str = "Theirs",
        theirs_id: str = "",
        mine_name: str = "You",
        mine_id: str = "",
        theirs_name: str = "",
    ) -> None:
        self._api = api
        self._ports = ports
        self._on_finished = on_finished
        self._on_deleted = on_deleted
        self._theirs_label = theirs_label or "Theirs"
        self._theirs_id = theirs_id
        self._mine_name = mine_name or "You"
        self._mine_id = mine_id
        self._ours["title"].setText("Yours")
        self._ours["avatar"].set_person(mine_id, mine_name or "You", 18)
        self._theirs["title"].setText(self._theirs_label)
        shown = theirs_name or self._theirs_label.replace("'s", "")
        self._theirs["avatar"].set_person(theirs_id, shown, 18)
        if tokens is not None:
            self.apply_theme(tokens)
        self.reload()

    def reload(self) -> None:
        if self._api is None:
            return
        self.show_state(self._api.combine_state())  # type: ignore[attr-defined]

    def show_state(self, state: Optional[CombineState]) -> None:
        self._state = state
        self._list.blockSignals(True)
        self._list.clear()
        self._row_ids = []
        if state is None:
            self._list.blockSignals(False)
            self._summary.setText("0 of 0 settled")
            self.finish_button.setEnabled(False)
            return
        total = len(state.clashes)
        self._summary.setText(f"{state.settled} of {total} settled")
        self.finish_button.setEnabled(state.done and total > 0)
        grouped: dict[str, list[Clash]] = {}
        order: list[str] = []
        for clash in state.clashes:
            if clash.path not in grouped:
                grouped[clash.path] = []
                order.append(clash.path)
            grouped[clash.path].append(clash)
        target_row = 0
        for path in order:
            header = QListWidgetItem(path.upper())
            header.setFlags(Qt.NoItemFlags)
            header.setSizeHint(QSize(0, 22))
            self._list.addItem(header)
            self._row_ids.append("")
            for clash in grouped[path]:
                label = f"Line {clash.line}" if clash.line else clash.kind
                mark = "✓  " if clash.resolution is not None else "    "
                item = QListWidgetItem(f"{mark}{label}")
                item.setData(Qt.UserRole, clash.id)
                item.setSizeHint(QSize(0, 26))
                if clash.resolution is not None:
                    item.setForeground(QColor(self._tokens.test_passed_color if self._tokens else "#1A7F37"))
                self._list.addItem(item)
                if state.clashes and clash.id == state.clashes[min(self._index, total - 1)].id:
                    target_row = self._list.count() - 1
                self._row_ids.append(clash.id)
        if state.clashes:
            self._index = min(self._index, len(state.clashes) - 1)
            self._list.setCurrentRow(target_row)
        self._list.blockSignals(False)
        self._paint_current()

    def settle(self, clash_id: str, resolution: str) -> None:
        if self._api is None:
            return

        def task() -> object:
            return self._api.resolve(clash_id, resolution)  # type: ignore[attr-defined]

        self._ports.run("team-sync-resolve", task, self.show_state)  # type: ignore[attr-defined]

    def settle_current(self, resolution: str) -> None:
        clash = self._current()
        if clash is None:
            return
        self.settle(clash.id, resolution)

    def _current(self) -> Optional[Clash]:
        if self._state is None or not self._state.clashes:
            return None
        if self._index < 0 or self._index >= len(self._state.clashes):
            return None
        return self._state.clashes[self._index]

    def _select_row(self, row: int) -> None:
        if row < 0 or row >= len(self._row_ids):
            return
        clash_id = self._row_ids[row]
        if not clash_id or self._state is None:
            return
        for index, clash in enumerate(self._state.clashes):
            if clash.id == clash_id:
                self._index = index
                break
        self._paint_current()

    def _paint_current(self) -> None:
        clash = self._current()
        if clash is None:
            return
        if clash.kind == CLASH_FORM:
            self._forms.show()
            self._forms.set_forms("\n".join(clash.ours), "\n".join(clash.theirs))
            self._result.hide()
            self._placeholder.hide()
        else:
            self._forms.hide()
        ours_pick = clash.resolution == RESOLVE_OURS
        theirs_pick = clash.resolution == RESOLVE_THEIRS
        self._ours["frame"].setProperty("picked", ours_pick)
        self._theirs["frame"].setProperty("picked", theirs_pick)
        _polish(self._ours["frame"])
        _polish(self._theirs["frame"])
        mine = self._tint(mine_bg) if self._tokens is not None else QColor("#FFF4E5")
        other = self._tint(theirs_bg) if self._tokens is not None else QColor("#E6F6F4")
        before = list(clash.context_before[-2:])
        after = list(clash.context_after[:2])
        self._fill(self._ours["body"], before, list(clash.ours), after, mine)
        self._fill(self._theirs["body"], before, list(clash.theirs), after, other)
        if clash.kind == CLASH_DELETED and clash.resolution is None and self._on_deleted is not None:
            self._on_deleted(clash)
        self._paint_result(clash, before, after)

    def _tint(self, fn) -> QColor:  # type: ignore[no-untyped-def]
        assert self._tokens is not None
        return QColor(fn(self._tokens))

    def _fill(self, editor: QPlainTextEdit, before: list[str], mid: list[str], after: list[str], tint: QColor) -> None:
        lines = before + mid + after
        editor.setPlainText("\n".join(lines))
        selections = []
        for number in range(len(before), len(before) + len(mid)):
            block = editor.document().findBlockByNumber(number)
            if not block.isValid():
                continue
            cursor = QTextCursor(block)
            fmt = QTextCharFormat()
            fmt.setBackground(tint)
            fmt.setProperty(QTextFormat.FullWidthSelection, True)
            selection = QTextEdit.ExtraSelection()
            selection.cursor = cursor
            selection.format = fmt
            selections.append(selection)
        editor.setExtraSelections(selections)

    def _paint_result(self, clash: Clash, before: list[str], after: list[str]) -> None:
        text = self._result_lines(clash)
        if text is None:
            self._result.hide()
            self._placeholder.show()
            return
        self._placeholder.hide()
        self._result.show()
        accent = QColor(accent_soft(self._tokens)) if self._tokens is not None else QColor("#E8EEFF")
        self._fill(self._result, before, text, after, accent)

    def _result_lines(self, clash: Clash) -> Optional[list[str]]:
        resolution = clash.resolution
        if resolution == RESOLVE_OURS:
            return list(clash.ours)
        if resolution == RESOLVE_THEIRS:
            return list(clash.theirs)
        if resolution == RESOLVE_BOTH:
            return list(clash.ours) + list(clash.theirs)
        if isinstance(resolution, str) and resolution.startswith(RESOLVE_TEXT_PREFIX):
            return resolution[len(RESOLVE_TEXT_PREFIX) :].splitlines()
        return None

    def _edit_result(self) -> None:
        self._result.setReadOnly(False)
        self._result.show()
        self._placeholder.hide()
        self._result.setFocus()

        def commit() -> None:
            clash = self._current()
            if clash is None:
                return
            self._result.setReadOnly(True)
            self.settle(clash.id, RESOLVE_TEXT_PREFIX + self._result.toPlainText())

        try:
            self._edit.clicked.disconnect()
        except RuntimeError:
            pass
        self._edit.clicked.connect(commit)

    def _move(self, delta: int) -> None:
        if self._state is None or not self._state.clashes:
            return
        self._index = (self._index + delta) % len(self._state.clashes)
        target = self._state.clashes[self._index].id
        for row, clash_id in enumerate(self._row_ids):
            if clash_id == target:
                self._list.setCurrentRow(row)
                return

    def _cancel_clicked(self) -> None:
        if self._api is None:
            return
        self._ports.run(  # type: ignore[attr-defined]
            "team-sync-cancel-combine",
            lambda: self._api.cancel_combine(),  # type: ignore[attr-defined]
            lambda _result: self.show_state(None),
        )

    def _finish_clicked(self) -> None:
        if self._api is None or self._state is None or not self._state.done:
            return
        self._ports.run(  # type: ignore[attr-defined]
            "team-sync-finish",
            lambda: self._api.finish_combine(),  # type: ignore[attr-defined]
            lambda _change: self._finished(),
        )

    def _finished(self) -> None:
        self.show_state(None)
        if self._on_finished is not None:
            self._on_finished()


__all__ = ["CombineTab"]
