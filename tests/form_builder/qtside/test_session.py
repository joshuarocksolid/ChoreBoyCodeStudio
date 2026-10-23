"""FormSession owns one form and nothing Qt."""

from __future__ import annotations

from app.features.form_builder.engine.project.forms import FormScope
from tests.form_builder.qtside.support import open_session

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form"/>
</ui>
"""


def test_open_exposes_the_form_and_dispose_closes_it() -> None:
    session = open_session(_FORM, "/tmp/forms/invoice.ui")
    assert session.path == "/tmp/forms/invoice.ui"
    assert session.scope.kind == "external"
    assert session.document.root.object_name == "Form"
    assert session.logic_read_only() is False
    assert "Form" in session.text()
    assert session.diagnostics.all() == ()
    session.set_path("/tmp/forms/renamed.ui", FormScope(kind="external", ui_path="/tmp/forms/renamed.ui"))
    assert session.path == "/tmp/forms/renamed.ui"
    session.dispose()
    session.dispose()
    try:
        session.path
    except RuntimeError as exc:
        assert "disposed" in str(exc)
    else:
        raise AssertionError("a disposed session still returned its path")
