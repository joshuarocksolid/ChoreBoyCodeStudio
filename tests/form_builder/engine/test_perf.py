"""Section 12 budgets for a realistic 300-widget form, measured as CPU time."""
from __future__ import annotations

import os
import time

import pytest

from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.writer import write_ui


def _realistic() -> str:
    items = []
    for index in range(300):
        items.append(
            '<item row="%d" column="0">'
            '<widget class="QLineEdit" name="e%d">'
            '<property name="sizePolicy">'
            '<sizepolicy hsizetype="Expanding" vsizetype="Fixed">'
            "<horstretch>0</horstretch><verstretch>0</verstretch>"
            "</sizepolicy></property>"
            '<property name="minimumSize"><size><width>10</width><height>20</height></size></property>'
            '<property name="font"><font><family>Sans</family><pointsize>10</pointsize>'
            "<bold>true</bold></font></property>"
            '<property name="toolTip"><string>tip %d</string></property>'
            '<property name="text"><string>t</string></property>'
            '<property name="maxLength"><number>32</number></property>'
            "</widget></item>" % (index, index, index)
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ui version="4.0"><class>Form</class>'
        '<widget class="QWidget" name="Form">'
        '<layout class="QGridLayout" name="grid">%s</layout>'
        "</widget><resources/><connections/></ui>" % "".join(items)
    )


def _p95(samples: list) -> float:
    ordered = sorted(samples[2:])
    return ordered[max(0, int(len(ordered) * 0.95) - 1)]


@pytest.mark.perf
def test_realistic_form_meets_the_section_12_budgets() -> None:
    text = _realistic()
    document = read_ui(text, allocator=IdAllocator()).document
    read_samples = []
    write_samples = []
    for _turn in range(17):
        started = time.process_time()
        read_ui(text, allocator=IdAllocator())
        read_samples.append(time.process_time() - started)
        started = time.process_time()
        written = write_ui(document).text
        write_samples.append(time.process_time() - started)
        assert "e299" in written
    read_p95 = _p95(read_samples)
    write_p95 = _p95(write_samples)
    load = os.getloadavg()
    print(
        "realistic-300 read_cpu_p95 %.4fs write_cpu_p95 %.4fs loadavg %s"
        % (read_p95, write_p95, load)
    )
    assert read_p95 < 0.025, "read %.4fs write %.4fs loadavg %s" % (read_p95, write_p95, load)
    assert write_p95 < 0.010, "read %.4fs write %.4fs loadavg %s" % (read_p95, write_p95, load)
