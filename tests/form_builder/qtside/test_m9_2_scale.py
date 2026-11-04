"""A 1000-widget form stays editable, and preview sessions do not keep widgets."""

from __future__ import annotations

import gc
from typing import Any, List

import pytest

from app.features.form_builder.engine.commands.catalog import SetProperty
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.integration.content_source import open_document_log
from app.qt.QtWidgets import QWidget
from app.qt.qt_compat import delete_now
from tests.form_builder.perf.reference import reference_form

pytestmark = pytest.mark.unit


def _tooltip(entry: object) -> str:
    value = getattr(entry, "value", None)
    text = getattr(value, "text", None)
    return text if isinstance(text, str) else ""


def _objects() -> int:
    gc.collect()
    return len(gc.get_objects())


def _qt_widgets(app: Any) -> int:
    found = getattr(app, "allWidgets", None)
    if not callable(found):
        return 0
    widgets = found()
    return len(widgets) if isinstance(widgets, list) else 0


@pytest.mark.timeout(180)
def test_a_thousand_widget_form_edits_undoes_saves_and_previews(qapp: Any) -> None:
    del qapp
    form = reference_form(1000)
    log = open_document_log(form.xml)
    found = log.document.by_name(form.edit_name)
    assert found
    node_id = found[0]
    before_text = _tooltip(log.document.node(node_id).prop("toolTip"))
    log.execute(SetProperty(node_id, "toolTip", StringValue("kept-on-a-large-form")))
    assert log.undo()
    assert _tooltip(log.document.node(node_id).prop("toolTip")) == before_text
    assert log.redo()
    text = write_ui(log.document).text
    assert "kept-on-a-large-form" in text
    again = read_ui(text, allocator=IdAllocator())
    assert len(list(again.document.iter_widgets())) == 1000
    from app.features.form_builder.qtside.preview.child.materialize import FormMaterializer

    built = FormMaterializer()._from_xml(text, {}, {})
    assert built.widget is not None
    assert built.failures == ()
    delete_now(built.widget)


def test_thousands_of_edits_return_to_an_object_plateau() -> None:
    text = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ui version="4.0"><widget class="QWidget" name="Form">'
        '<property name="windowTitle"><string>Hello</string></property>'
        "</widget></ui>\n"
    )
    samples: List[int] = []
    for _cycle in range(3):
        log = open_document_log(text)
        root = log.document.root.id
        for index in range(1500):
            log.execute(SetProperty(root, "windowTitle", StringValue("title-%d" % index)))
        while log.undo():
            pass
        del log
        samples.append(_objects())
    print("M9.2 edit-cycle objects %s" % (samples,))
    assert samples[-1] - samples[0] < 8000


def test_closed_previews_drop_the_filter_and_the_window(qapp: Any) -> None:
    from app.features.form_builder.engine.ipc.protocol import CloseView
    from app.features.form_builder.qtside.preview.child.session import ChildSession

    class _Writer:
        def send(self, _message: object) -> None:
            return None

    def filters() -> int:
        gc.collect()
        return sum(1 for obj in gc.get_objects() if type(obj).__name__ == "_UserClose")

    before_filters = filters()
    before_widgets = _qt_widgets(qapp)
    held: List[Any] = []
    for _index in range(4):
        held.append(ChildSession(_Writer(), qapp))  # type: ignore[arg-type]
    during = filters()
    del held
    gc.collect()
    after_filters = filters()
    child = ChildSession(_Writer(), qapp)  # type: ignore[arg-type]
    widget = QWidget()
    widget.setObjectName("m92-preview")
    widget.resize(40, 40)
    child._replace_view("view", widget, 1, 1.0, "")
    child._close(CloseView(request_id="close", view_id="view"))
    qapp.processEvents()
    gc.collect()
    widgets = getattr(qapp, "allWidgets", lambda: [])()
    left = [item for item in widgets if item.objectName() == "m92-preview"]
    child._finish(0)
    del child
    gc.collect()
    end_filters = filters()
    end_widgets = _qt_widgets(qapp)
    line = (
        "M9.2 preview filters before %s during %s after-drop %s end %s widgets before %s end %s\n"
        % (before_filters, during, after_filters, end_filters, before_widgets, end_widgets)
    )
    print(line)
    assert during >= before_filters + 4
    assert after_filters <= before_filters
    assert left == []
    assert end_filters <= before_filters
    assert end_widgets <= before_widgets + 5
