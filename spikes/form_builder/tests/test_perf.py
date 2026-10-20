"""Budgets for a 300-widget form. Numbers are written even when a budget misses."""

from __future__ import annotations

import os
import resource
import statistics
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FORM = Path(__file__).resolve().parents[1] / "samples" / "big_form.ui"
REPORT = Path(__file__).resolve().parents[1] / "perf_report.txt"


def _median(values):
    return statistics.median(values)


class PerfBudgetTest(unittest.TestCase):
    def test_big_form_budgets(self):
        from PySide6.QtWidgets import QApplication

        from spikes.form_builder.canvas import content_for, item_for
        from spikes.form_builder.catalog import CATALOG
        from spikes.form_builder.commands import InsertItem, SetProperty
        from spikes.form_builder.model import iter_widgets, prop_string, widget_layout
        from spikes.form_builder.perf import log_sample
        from spikes.form_builder.window import MainWindow
        from spikes.form_builder.xmlio import load_path

        app = QApplication.instance() or QApplication([])
        window = MainWindow("light")
        window.resize(900, 700)
        window.show()
        app.processEvents()
        self.assertTrue(FORM.exists(), "run samples/make_samples.py first")
        rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

        opens = []
        open_cpu = []
        for _index in range(5):
            started = time.perf_counter()
            cpu_started = time.process_time()
            doc = load_path(str(FORM))
            window.load_document(doc, str(FORM))
            app.processEvents()
            opens.append((time.perf_counter() - started) * 1000)
            open_cpu.append((time.process_time() - cpu_started) * 1000)
        widget_count = sum(1 for _widget in iter_widgets(window.doc))
        rss_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss_delta = rss_after - rss_before
        if sys.platform != "darwin":
            rss_delta *= 1024

        entry = next(item for item in CATALOG if item.class_name == "QPushButton")
        layout = widget_layout(window.doc.root)
        inserts = []
        undos = []
        for _index in range(5):
            window.history.execute(InsertItem(layout.id, 1, item_for(window.doc, content_for(window.doc, entry), {})))
            inserts.append(window.last_edit)
            window.history.undo()
            undos.append(window.last_edit)
        field = next(widget for widget in iter_widgets(window.doc) if widget.class_name == "QLineEdit")
        props = []
        for index in range(5):
            window.history.execute(SetProperty(field.id, "text", prop_string("text", f"n{index}")))
            props.append(window.last_edit)

        saves = []
        folder = Path(tempfile.mkdtemp(prefix="cbcs_perf_"))
        for index in range(5):
            target = folder / f"big{index}.ui"
            started = time.perf_counter()
            window._write(str(target))
            saves.append((time.perf_counter() - started) * 1000)

        import shutil

        shutil.rmtree(folder, ignore_errors=True)
        numbers = {
            "widgets": widget_count,
            "open_ms": opens,
            "open_cpu_ms": open_cpu,
            "load": os.getloadavg()[0],
            "insert_ms": inserts,
            "undo_ms": undos,
            "property_ms": props,
            "save_ms": saves,
            "rss_extra_bytes": rss_delta,
        }
        text = _render(numbers)
        REPORT.write_text(text, encoding="utf-8")
        print(text)
        for kind, values in (("open", opens), ("insert", inserts), ("undo", undos), ("property", props), ("save", saves)):
            log_sample(kind, _median(values), f"widgets={widget_count}")
        log_sample("rss_extra", rss_delta / (1024 * 1024), "MB")

        misses = []
        if _median(opens) >= 150:
            misses.append(f"open median {_median(opens):.1f} ms")
        if _median(inserts) >= 16 or _median(props) >= 16:
            misses.append(f"edit median insert {_median(inserts):.1f} property {_median(props):.1f} ms")
        if _median(undos) >= 16:
            misses.append(f"undo median {_median(undos):.1f} ms")
        if _median(saves) >= 50:
            misses.append(f"save median {_median(saves):.1f} ms")
        if rss_delta >= 30 * 1024 * 1024:
            misses.append(f"rss extra {rss_delta / (1024 * 1024):.1f} MB")
        self.assertFalse(misses, text + "\n" + "\n".join(misses))


def _render(numbers) -> str:
    def span(values):
        return f"median {_median(values):.2f} ms  min {min(values):.2f}  max {max(values):.2f}  n={len(values)}  {['%.2f' % value for value in values]}"

    return "\n".join(
        [
            f"widgets {numbers['widgets']}",
            "open " + span(numbers["open_ms"]) + "  budget 150",
            "open cpu " + span(numbers["open_cpu_ms"]) + "  (process time; wall time above includes waiting for a busy machine)",
            "insert " + span(numbers["insert_ms"]) + "  budget 16",
            "property " + span(numbers["property_ms"]) + "  budget 16",
            "undo " + span(numbers["undo_ms"]) + "  budget 16",
            "save " + span(numbers["save_ms"]) + "  budget 50",
            f"rss extra {numbers['rss_extra_bytes'] / (1024 * 1024):.2f} MB  budget 30",
            "open times load plus the workbench, after QApplication already exists.",
            "edit times are command apply plus the canvas patch. The geometry index refreshes on the next pointer event.",
            f"machine load average at the run: {numbers['load']:.1f}",
            "rss extra is ru_maxrss after five opens minus ru_maxrss of the empty window. It is a high-water mark, so it can include caches from the repeats. On macOS the unit is bytes.",
            "",
        ]
    )


if __name__ == "__main__":
    unittest.main()
