"""Generation of a 300-widget form stays under the 50 ms CPU budget."""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.ui4.reader import read_ui


def _form() -> str:
    rows = []
    for index in range(300):
        rows.append(
            '<item row="%d" column="0">'
            '<widget class="QLineEdit" name="e%d">'
            '<property name="text"><string>t%d</string></property>'
            "</widget></item>" % (index, index, index)
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ui version="4.0"><class>Form</class>'
        '<widget class="QWidget" name="Form">'
        '<layout class="QGridLayout" name="grid">%s</layout>'
        "</widget></ui>" % "".join(rows)
    )


@pytest.mark.perf
def test_generate_300_widget_form_under_50ms(tmp_path: Path) -> None:
    text = _form()
    document = read_ui(text, allocator=IdAllocator()).document
    ui_path = tmp_path / "forms" / "wide.ui"
    scope = FormScope(
        kind="project",
        ui_path=str(ui_path),
        project_root=str(tmp_path),
        generated_path=str(tmp_path / "forms" / "ui_wide.py"),
        window_path=str(tmp_path / "forms" / "wide_window.py"),
        module_name="forms.ui_wide",
    )
    source = text.encode("utf-8")
    samples = []
    for _turn in range(5):
        started = time.process_time()
        result = generate_form_module(document, scope=scope, source_bytes=source)
        samples.append(time.process_time() - started)
        assert result.text is not None
        assert "e299" in result.text
    best = min(samples)
    load = os.getloadavg()
    print("generate-300 cpu_s %.4f samples %s loadavg %s" % (best, ["%.4f" % item for item in samples], load))
    assert best < 0.050, "cpu %.4fs loadavg %s" % (best, load)
