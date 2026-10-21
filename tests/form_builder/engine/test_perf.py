"""Read plus write of a 1000-widget form stays under 50 ms."""
from __future__ import annotations

import os
import time

import pytest

from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.writer import write_ui


def _thousand() -> str:
    children = []
    for index in range(1000):
        children.append(
            '<widget class="QPushButton" name="button%s">'
            '<property name="text"><string>Button %s</string></property>'
            "</widget>" % (index, index)
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ui version="4.0">\n'
        ' <class>Form</class>\n'
        ' <widget class="QWidget" name="Form">\n'
        "%s\n"
        " </widget>\n"
        "</ui>\n" % "\n".join(children)
    )


@pytest.mark.perf
def test_thousand_widget_round_trip_is_under_50ms() -> None:
    text = _thousand()
    cpu_samples = []
    wall_samples = []
    for _turn in range(17):
        wall_started = time.perf_counter()
        cpu_started = time.process_time()
        document = read_ui(text, allocator=IdAllocator()).document
        written = write_ui(document).text
        cpu_samples.append(time.process_time() - cpu_started)
        wall_samples.append(time.perf_counter() - wall_started)
        assert "button999" in written
    cpu = sorted(cpu_samples[2:])
    wall = sorted(wall_samples[2:])
    cpu_p95 = cpu[max(0, int(len(cpu) * 0.95) - 1)]
    wall_p95 = wall[max(0, int(len(wall) * 0.95) - 1)]
    load = os.getloadavg()
    print(
        "thousand-widget cpu_p95 %.4fs wall_p95 %.4fs loadavg %s"
        % (cpu_p95, wall_p95, load)
    )
    assert cpu_p95 < 0.050, "cpu_p95 %.4fs wall_p95 %.4fs loadavg %s" % (cpu_p95, wall_p95, load)
