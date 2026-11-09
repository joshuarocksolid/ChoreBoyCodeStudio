# pyright: reportAttributeAccessIssue=false
"""CPU time for the M4.3b visual popovers on the 300-widget reference form.

UX-M4-007: opening a popover is 50 ms, and one live change (a colour-square
drag, a gradient-stop drag, a font size step) is 16 ms. Run it with FreeCAD's
Python. ``--json`` stores one sample set so a later run can print the
interleaved before/after table.

This file is the lane's own measurement. It does not edit the speed harness.
"""

from __future__ import annotations

import argparse
import cProfile
import json
import pstats
import time
from typing import Callable, Dict, List, Optional, Sequence

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.qtside.inspector import InspectorPane
from app.features.form_builder.qtside.inspector.api import GroupId
from app.qt.QtCore import QPoint, Qt
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QWidget
from tests.form_builder.perf.reference import DEFAULT_SEED, reference_form
from tests.form_builder.qtside.support import realize

_OPEN_BUDGET_MS = 50.0
_LIVE_BUDGET_MS = 16.0
_BANNER_PROPS = """
     <property name="color">
      <color><red>255</red><green>0</green><blue>0</blue></color>
     </property>
     <property name="brush">
      <brush brushstyle="LinearGradientPattern">
       <gradient type="LinearGradient" spread="PadSpread" coordinatemode="ObjectBoundingMode" startx="0" starty="0" endx="1" endy="0">
        <gradientstop position="0"><color><red>0</red><green>0</green><blue>0</blue></color></gradientstop>
        <gradientstop position="1"><color><red>255</red><green>255</green><blue>255</blue></color></gradientstop>
       </gradient>
      </brush>
     </property>
"""


def _form_xml() -> str:
    xml = reference_form(300, DEFAULT_SEED).xml
    needle = '<widget class="QLabel" name="banner">'
    if needle not in xml:
        raise RuntimeError("reference form has no banner label")
    return xml.replace(needle, needle + _BANNER_PROPS, 1)


def _percentile(samples: Sequence[float], fraction: float) -> float:
    ordered = sorted(samples)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, int(round(fraction * (len(ordered) - 1)))))
    return ordered[index]


def _visible(name: str) -> QWidget:
    found = [
        widget
        for widget in QApplication.allWidgets()
        if widget.objectName() == name and widget.isVisible()
    ]
    if not found:
        raise RuntimeError("missing %s" % name)
    return found[-1]


def _open(pane: InspectorPane, name: str, app: QApplication) -> None:
    row = pane.findChild(QWidget, name)
    if row is None:
        raise RuntimeError("missing row %s" % name)
    summary = row.findChild(QWidget, "formBuilder.summary")
    if summary is None:
        raise RuntimeError("missing summary %s" % name)
    summary.click()  # type: ignore[attr-defined]
    app.processEvents()


def _close(app: QApplication) -> None:
    done = [
        widget
        for widget in QApplication.allWidgets()
        if widget.objectName() == "formBuilder.popoverDone" and widget.isVisible()
    ]
    if done:
        done[-1].click()  # type: ignore[attr-defined]
        app.processEvents()


def _cpu(action: Callable[[], None]) -> float:
    started = time.process_time()
    action()
    return (time.process_time() - started) * 1000.0


def _drag(widget: QWidget, app: QApplication, steps: int = 1) -> List[float]:
    """One press, then one timed move per step, then a release."""
    center = widget.rect().center()
    QTest.mousePress(widget, Qt.MouseButton.LeftButton, pos=center)
    app.processEvents()
    samples: List[float] = []
    point = center
    for step in range(steps):
        point = QPoint(min(widget.width() - 2, 12 + step * 8), center.y())

        def move(target: QPoint = point) -> None:
            QTest.mouseMove(widget, target)
            app.processEvents()

        samples.append(_cpu(move))
    QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=point)
    app.processEvents()
    return samples


class _Bench:
    def __init__(self, samples: int, warmup: int) -> None:
        xml = _form_xml()
        self.app = QApplication.instance() or QApplication([])
        self.session, self.realizer = realize(xml)
        window = QWidget()
        self.window = window
        pane = InspectorPane(self.session, self.realizer, data_tab=False, on_leave=lambda: None, parent=window)
        self.pane = pane
        window.resize(360, 800)
        window.show()
        banner = self.session.document.by_name("banner")[0]
        self.session.selection.set((banner,), source=SelectionSource.PROGRAM)
        pane.set_group_expanded(GroupId.ALL, True)
        pane.set_group_expanded(GroupId.APPEARANCE, True)
        pane.flush()
        self.app.processEvents()
        self.samples = samples
        self.warmup = warmup
        self.rows: Dict[str, List[float]] = {}

    def close(self) -> None:
        _close(self.app)
        self.pane.dispose()
        self.realizer.dispose()
        self.session.dispose()
        self.window.close()

    def _repeat(self, name: str, action: Callable[[], None], budget: float) -> None:
        taken: List[float] = []
        for index in range(self.warmup + self.samples):
            value = _cpu(action)
            if index >= self.warmup:
                taken.append(value)
        self.rows[name] = taken
        del budget

    def measure(self) -> None:
        def open_colour() -> None:
            _close(self.app)
            _open(self.pane, "formBuilder.row.color", self.app)

        def open_brush() -> None:
            _close(self.app)
            _open(self.pane, "formBuilder.row.brush", self.app)

        def open_font() -> None:
            _close(self.app)
            _open(self.pane, "formBuilder.row.font", self.app)

        def open_palette() -> None:
            _close(self.app)
            _open(self.pane, "formBuilder.row.palette", self.app)

        self._repeat("open colour", open_colour, _OPEN_BUDGET_MS)
        self._repeat("open brush/gradient", open_brush, _OPEN_BUDGET_MS)
        self._repeat("open font", open_font, _OPEN_BUDGET_MS)
        self._repeat("open palette", open_palette, _OPEN_BUDGET_MS)

        _close(self.app)
        _open(self.pane, "formBuilder.row.color", self.app)
        square = _visible("formBuilder.colorSquare")
        drags: List[float] = []
        for _index in range(self.warmup):
            _drag(square, self.app, 1)
        for _index in range(self.samples):
            drags.extend(_drag(square, self.app, 1))
        self.rows["colour drag"] = drags
        _close(self.app)

        _open(self.pane, "formBuilder.row.brush", self.app)
        bar = _visible("formBuilder.gradientBar")
        stops: List[float] = []
        for _index in range(self.warmup):
            _drag(bar, self.app, 1)
        for _index in range(self.samples):
            stops.extend(_drag(bar, self.app, 1))
        self.rows["gradient stop drag"] = stops
        _close(self.app)

        _open(self.pane, "formBuilder.row.font", self.app)
        size = _visible("formBuilder.fontSize")
        steps: List[float] = []

        def step() -> None:
            QTest.keyClick(size, Qt.Key.Key_Up)
            self.app.processEvents()

        for index in range(self.warmup + self.samples):
            value = _cpu(step)
            if index >= self.warmup:
                steps.append(value)
        self.rows["font size step"] = steps
        _close(self.app)

    def profile(self, path_name: str) -> str:
        """One cProfile pass of a named path. Returns the top cumulative rows."""
        if path_name == "open colour":
            action = lambda: _open(self.pane, "formBuilder.row.color", self.app)
        elif path_name == "open brush/gradient":
            action = lambda: _open(self.pane, "formBuilder.row.brush", self.app)
        elif path_name == "open font":
            action = lambda: _open(self.pane, "formBuilder.row.font", self.app)
        elif path_name == "open palette":
            action = lambda: _open(self.pane, "formBuilder.row.palette", self.app)
        elif path_name == "colour drag":
            _open(self.pane, "formBuilder.row.color", self.app)
            square = _visible("formBuilder.colorSquare")

            def action() -> None:
                _drag(square, self.app, 1)

        elif path_name == "gradient stop drag":
            _open(self.pane, "formBuilder.row.brush", self.app)
            bar = _visible("formBuilder.gradientBar")

            def action() -> None:
                _drag(bar, self.app, 1)

        else:
            raise RuntimeError("no profile for %s" % path_name)
        _close(self.app)
        profiler = cProfile.Profile()
        profiler.enable()
        action()
        profiler.disable()
        _close(self.app)
        stats = pstats.Stats(profiler)
        stats.sort_stats("cumulative")
        import io

        buffer = io.StringIO()
        stats.stream = buffer
        stats.print_stats(12)
        return buffer.getvalue()


def _payload(rows: Dict[str, List[float]]) -> dict:
    body = {}
    for name, samples in rows.items():
        budget = _OPEN_BUDGET_MS if name.startswith("open ") else _LIVE_BUDGET_MS
        body[name] = {
            "n": len(samples),
            "p50": _percentile(samples, 0.50),
            "p95": _percentile(samples, 0.95),
            "budget": budget,
        }
    return body


def format_table(rows: Dict[str, List[float]]) -> str:
    lines = ["path                      n   p50 ms   p95 ms   budget   verdict"]
    for name, item in _payload(rows).items():
        verdict = "pass" if item["p95"] <= item["budget"] else "FAIL"
        lines.append(
            "%-24s  %2d  %7.2f  %7.2f  %7.0f   %s"
            % (name, item["n"], item["p50"], item["p95"], item["budget"], verdict)
        )
    return "\n".join(lines)


def format_compare(before: dict, after: dict) -> str:
    lines = ["path                      before p50/p95    after p50/p95    budget   verdict"]
    names = list(before)
    for name in names:
        left = before[name]
        right = after.get(name)
        if right is None:
            continue
        verdict = "pass" if right["p95"] <= right["budget"] else "FAIL"
        lines.append(
            "%-24s  %6.2f / %6.2f   %6.2f / %6.2f   %5.0f   %s"
            % (
                name,
                left["p50"],
                left["p95"],
                right["p50"],
                right["p95"],
                right["budget"],
                verdict,
            )
        )
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=7)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--json", help="Write p50/p95 for this run.")
    parser.add_argument("--before", help="JSON from an earlier run. Prints the interleaved table.")
    parser.add_argument("--profile", action="store_true", help="Print cProfile for each path.")
    args = parser.parse_args(list(argv) if argv is not None else None)
    bench = _Bench(args.samples, args.warmup)
    try:
        bench.measure()
        text = format_table(bench.rows)
        print(text)
        payload = _payload(bench.rows)
        if args.json:
            with open(args.json, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
                handle.write("\n")
        if args.before:
            with open(args.before, encoding="utf-8") as handle:
                previous = json.load(handle)
            print()
            print(format_compare(previous, payload))
        if args.profile:
            for name in (
                "open colour",
                "open brush/gradient",
                "open font",
                "open palette",
                "colour drag",
                "gradient stop drag",
            ):
                print("\n# %s" % name)
                print(bench.profile(name))
    finally:
        bench.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
