"""Combine editor tab. Finish stays disabled until every clash is settled."""

from __future__ import annotations

from typing import Callable, Optional

from app.qt.QtCore import Qt
from app.qt.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
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
from app.features.team_sync.ui.theme import button_qss, field_qss, primary_button_qss, surface_qss
from app.shell.theme_tokens import ShellThemeTokens


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

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        header = QWidget(self)
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(12, 8, 12, 8)
        self._warning = QLabel("!", header)
        self._summary = QLabel("0 of 0 settled", header)
        self._summary.setObjectName("shell.teamSync.combineSummary")
        header_row.addWidget(self._warning)
        header_row.addWidget(self._summary, 1)
        self._prev = QPushButton("Previous", header)
        self._prev.setObjectName("shell.teamSync.combinePrev")
        self._next = QPushButton("Next", header)
        self._next.setObjectName("shell.teamSync.combineNext")
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
        self._list.currentRowChanged.connect(self._select)
        self._detail = QWidget(splitter)
        detail = QVBoxLayout(self._detail)
        detail.setContentsMargins(8, 8, 8, 8)
        columns = QHBoxLayout()
        self._ours = self._column("Yours")
        self._theirs = self._column("Theirs")
        columns.addWidget(self._ours[0], 1)
        columns.addWidget(self._theirs[0], 1)
        detail.addLayout(columns)
        result_row = QHBoxLayout()
        result_row.addWidget(QLabel("Result", self._detail))
        result_row.addStretch(1)
        self._both = QPushButton("Both", self._detail)
        self._both.setObjectName("shell.teamSync.combineBoth")
        self._edit = QPushButton("Edit", self._detail)
        self._edit.setObjectName("shell.teamSync.combineEdit")
        self._both.clicked.connect(lambda: self.settle_current(RESOLVE_BOTH))
        self._edit.clicked.connect(self._edit_result)
        result_row.addWidget(self._both)
        result_row.addWidget(self._edit)
        detail.addLayout(result_row)
        self._result = QPlainTextEdit(self._detail)
        self._result.setObjectName("shell.teamSync.combineResult")
        self._result.setReadOnly(True)
        detail.addWidget(self._result)
        self._forms = FormCompare(self._detail)
        self._forms.hide()
        detail.addWidget(self._forms)
        splitter.addWidget(self._list)
        splitter.addWidget(self._detail)
        splitter.setSizes([240, 640])
        root.addWidget(splitter, 1)

    def _column(self, title: str) -> tuple[QWidget, QLabel, QPushButton]:
        host = QWidget(self._detail)
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(title, host))
        body = QLabel("", host)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(body, 1)
        button = QPushButton("Use This", host)
        layout.addWidget(button, 0, Qt.AlignLeft)
        if title == "Yours":
            button.clicked.connect(lambda: self.settle_current(RESOLVE_OURS))
        else:
            button.clicked.connect(lambda: self.settle_current(RESOLVE_THEIRS))
        return host, body, button

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self.setStyleSheet(surface_qss(tokens))
        self.finish_button.setStyleSheet(primary_button_qss(tokens))
        for button in (self._prev, self._next, self._cancel, self._both, self._edit):
            button.setStyleSheet(button_qss(tokens))
        self._result.setStyleSheet(field_qss(tokens))
        self._warning.setStyleSheet(f"color: {tokens.diag_warning_color or '#B45309'}; font-weight: 700;")

    def open_state(
        self,
        api: object,
        ports: object,
        *,
        on_finished: Callable[[], None],
        on_deleted: Callable[[Clash], None],
        tokens: Optional[ShellThemeTokens] = None,
    ) -> None:
        self._api = api
        self._ports = ports
        self._on_finished = on_finished
        self._on_deleted = on_deleted
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
        self._list.blockSignals(False)
        if state is None:
            self._summary.setText("0 of 0 settled")
            self.finish_button.setEnabled(False)
            return
        total = len(state.clashes)
        self._summary.setText(f"{state.settled} of {total} settled")
        self.finish_button.setEnabled(state.done and total > 0)
        for clash in state.clashes:
            mark = "✓" if clash.resolution is not None else "·"
            self._list.addItem(QListWidgetItem(f"{mark}  {clash.path}"))
        if state.clashes:
            self._index = min(self._index, len(state.clashes) - 1)
            self._list.setCurrentRow(self._index)

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

    def _select(self, row: int) -> None:
        if self._state is None or row < 0 or row >= len(self._state.clashes):
            return
        self._index = row
        clash = self._current()
        if clash is None:
            return
        if clash.kind == CLASH_FORM:
            self._forms.show()
            self._forms.set_forms("\n".join(clash.ours), "\n".join(clash.theirs))
            self._result.hide()
        else:
            self._forms.hide()
            self._result.show()
        self._ours[1].setText(self._block(clash.context_before, clash.ours, clash.context_after))
        self._theirs[1].setText(self._block(clash.context_before, clash.theirs, clash.context_after))
        self._result.setPlainText(self._result_text(clash))
        if clash.kind == CLASH_DELETED and clash.resolution is None and self._on_deleted is not None:
            self._on_deleted(clash)

    def _block(self, before: tuple[str, ...], lines: tuple[str, ...], after: tuple[str, ...]) -> str:
        body = list(before[-2:]) + list(lines) + list(after[:2])
        return "\n".join(body)

    def _result_text(self, clash: Clash) -> str:
        resolution = clash.resolution
        if resolution == RESOLVE_OURS:
            return "\n".join(clash.ours)
        if resolution == RESOLVE_THEIRS:
            return "\n".join(clash.theirs)
        if resolution == RESOLVE_BOTH:
            return "\n".join(tuple(clash.ours) + tuple(clash.theirs))
        if isinstance(resolution, str) and resolution.startswith(RESOLVE_TEXT_PREFIX):
            return resolution[len(RESOLVE_TEXT_PREFIX) :]
        return ""

    def _edit_result(self) -> None:
        self._result.setReadOnly(False)
        self._result.setFocus()

        def commit() -> None:
            clash = self._current()
            if clash is None:
                return
            self._result.setReadOnly(True)
            self.settle(clash.id, RESOLVE_TEXT_PREFIX + self._result.toPlainText())

        self._result.textChanged.connect(lambda: None)
        commit_button = self._edit
        try:
            commit_button.clicked.disconnect()
        except RuntimeError:
            pass
        commit_button.clicked.connect(commit)

    def _move(self, delta: int) -> None:
        if self._state is None or not self._state.clashes:
            return
        self._index = (self._index + delta) % len(self._state.clashes)
        self._list.setCurrentRow(self._index)

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
