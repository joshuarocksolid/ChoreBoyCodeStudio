"""The left-pane Data tab. Its body is the registered sections."""

from __future__ import annotations

from typing import Any, Dict

from app.qt.QtCore import QTimer, Signal
from app.qt.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from app.features.form_builder.engine.events import PRIORITY_VIEWS
from app.features.form_builder.qtside.data_panel.chrome import chrome_qss
from app.features.form_builder.qtside.data_panel.host import note_data_tab
from app.features.form_builder.qtside.data_panel.sections_ext import default_registry
from app.qt.qt_compat import wrapper_is_valid


class DataPanel(QWidget):
    """Empty until a form has a source. Add a connection opens Settings › Connections."""

    connect_requested = Signal()
    add_connection_requested = Signal()
    schema_changed = Signal(str)

    def __init__(self, workbench: Any) -> None:
        super().__init__(workbench)
        self.setObjectName("formBuilder.dataPanel")
        self.setAccessibleName("Data")
        self._workbench = workbench
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(12, 12, 12, 12)
        self._built: Dict[str, QWidget] = {}
        self._tokens: object = None
        self._queued = False
        self._sub: object = None
        self.destroyed.connect(self._drop_log)
        self._arm()
        self.reload()

    def reload(self) -> None:
        document = getattr(getattr(self._workbench, "session", None), "document", None)
        for section in default_registry().sections():
            show = document is not None and section.applies(document)
            widget = self._built.get(section.section_id)
            if not show:
                if widget is not None:
                    widget.hide()
                continue
            if widget is None:
                widget = section.create(self)
                self._built[section.section_id] = widget
                self._layout.addWidget(widget)
            widget.show()
            widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
            refresh = getattr(widget, "refresh", None)
            if callable(refresh):
                refresh()
        self._pin_footer()
        self._ask_arrange()

    def section_need(self) -> int:
        """The sentences and buttons. A stretch must not count as content."""

        height = self._layout.contentsMargins().top() + self._layout.contentsMargins().bottom()
        width = max(self.width(), 184)
        for widget in self._built.values():
            if widget.isHidden():
                continue
            if widget.hasHeightForWidth():
                height += widget.heightForWidth(width)
            else:
                height += max(widget.minimumSizeHint().height(), widget.sizeHint().height())
            height += self._layout.spacing()
        return height

    def _ask_arrange(self) -> None:
        if self.minimumHeight() >= self.section_need():
            return
        workbench = self._workbench
        if getattr(workbench, "_arranging_left", False):
            return
        arrange = getattr(workbench, "_arrange_left", None)
        if callable(arrange):
            arrange()

    def _pin_footer(self) -> None:
        """Sections stay at their height. Spare space sits above the footer."""

        layout = self._layout
        index = 0
        while index < layout.count():
            item = layout.itemAt(index)
            if item is not None and item.widget() is None and item.spacerItem() is not None:
                layout.takeAt(index)
                continue
            index += 1
        footer = self._built.get("schema_footer")
        if footer is not None and not footer.isHidden():
            at = layout.indexOf(footer)
            if at >= 0:
                layout.insertStretch(at, 1)
                return
        layout.addStretch(1)

    def showEvent(self, event: object) -> None:  # noqa: N802
        self._arm()
        self.reload()
        note_data_tab(self, "left", True)
        super().showEvent(event)  # type: ignore[arg-type]

    def hideEvent(self, event: object) -> None:  # noqa: N802
        note_data_tab(self, "left", False)
        super().hideEvent(event)  # type: ignore[arg-type]

    def apply_theme(self, tokens: object) -> None:
        self._tokens = tokens
        qss = chrome_qss(tokens, "formBuilder.dataPanel")
        qss += "QLabel#formBuilder\\.data\\.stale { color: %s; background: transparent; }" % (
            tokens.diag_warning_color,  # type: ignore[attr-defined]
        )
        qss += (
            "QLabel#formBuilder\\.data\\.ejectedText { color: %s; }"
            "QLabel#formBuilder\\.data\\.ejectedText a { color: %s; }"
        ) % (
            tokens.text_primary,  # type: ignore[attr-defined]
            tokens.accent,  # type: ignore[attr-defined]
        )
        self.setStyleSheet(qss)
        self.reload()

    def _arm(self) -> None:
        if self._sub is not None:
            return
        session = getattr(self._workbench, "session", None)
        log = getattr(session, "log", None)
        subscribe = getattr(log, "subscribe", None)
        if not callable(subscribe):
            return
        self._sub = subscribe(self._on_log, priority=PRIORITY_VIEWS)

    def _on_log(self, _changeset: object) -> None:
        if self._queued:
            return
        self._queued = True
        QTimer.singleShot(0, self._flush)

    def _flush(self) -> None:
        self._queued = False
        try:
            if not wrapper_is_valid(self):
                return
            self.reload()
        except RuntimeError:
            return

    def _drop_log(self) -> None:
        sub = self._sub
        self._sub = None
        close = getattr(sub, "close", None)
        if callable(close):
            close()
