"""The left-pane Data tab. Its body is the registered sections."""

from __future__ import annotations

from typing import Any, Dict

from app.qt.QtCore import QTimer, Signal
from app.qt.QtWidgets import QVBoxLayout, QWidget

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
            refresh = getattr(widget, "refresh", None)
            if callable(refresh):
                refresh()

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
        self.setStyleSheet(qss)

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
