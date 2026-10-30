# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false
"""UX-M6-003 rows for the speed harness.

One session holds the 300-widget reference form, 120 events and a 2,000-line
window file. Engine-only rows (the codec, rename, and window-file reads) do
not open that window. Run just these rows with
``python -m tests.form_builder.perf.m6_paths``.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

KEY_BUDGET_MS = 16.0
Name = Tuple[str, Optional[int], float]


@dataclass(frozen=True)
class Spec:
    point: str
    widgets: Optional[int]
    budget_ms: float
    fn: Callable[[], None]
    prepare: Optional[Callable[[], None]] = None
    cleanup: Optional[Callable[[], None]] = None
    baseline: Optional[Callable[[], None]] = None
    note: str = ""


@dataclass(frozen=True)
class Group:
    key: str
    names: Tuple[Name, ...]
    build: Callable[[], Tuple[List[Spec], Callable[[], None]]]


def _app():  # type: ignore[no-untyped-def]
    from app.qt.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _window_text(methods: int, pad_to: int) -> str:
    lines = [
        "from PySide6.QtWidgets import QDialog",
        "",
        "class RefWindow(QDialog):",
        "    def __init__(self, parent=None):",
        "        super().__init__(parent)",
        "        self.ui = Ui_Ref()",
        "        self.ui.setupUi(self)",
        "",
    ]
    for index in range(methods):
        lines.append("    def method_%d(self):" % index)
        lines.append("        return %d" % index)
        lines.append("")
    while len(lines) < pad_to:
        lines.append("    # pad")
    return "\n".join(lines[:pad_to]) + "\n"


def _bulk(chars: int) -> str:
    body = _window_text(40, 80)
    pad = "    # %s\n" % ("x" * 40)
    while len(body) < chars:
        body += pad
    return body[:chars]


def _engine_group() -> Tuple[List[Spec], Callable[[], None]]:
    from app.features.form_builder.engine.commands.catalog import Rename
    import json

    from app.features.form_builder.engine.logic.codec import parse_steps
    from app.features.form_builder.engine.project.handler_checks import check_handlers
    from app.features.form_builder.engine.project.window_file import read_window
    from app.features.form_builder.engine.ui4.defaults import QtClassTable
    from tests.form_builder.engine.commands._support import open_log

    text = json.dumps(
        [{"do": "slot", "target": "edit%d" % (index % 20), "slot": "clear()"} for index in range(50)]
    )
    root = tempfile.mkdtemp(prefix="m6r-engine-")
    small = _bulk(100 * 1024)
    large = _bulk(1_000_000)
    read_window(root, "small.py", text=small, token="warm-small")
    read_window(root, "large.py", text=large, token="warm-large")
    seq = {"read": 0}

    props = []
    conns = []
    for index in range(40):
        conns.append(
            "<connection><sender>button0</sender><signal>clicked()</signal>"
            "<receiver>edit%d</receiver><slot>clear()</slot></connection>" % (index % 20)
        )
    for index in range(60):
        props.append(
            '<property name="cbcsHint%d" stdset="0"><string>v%d</string></property>' % (index, index)
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0"><class>Ref</class>'
        '<widget class="QDialog" name="Ref"><property name="geometry">'
        '<rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>'
        "%s" % "".join(props)
        + '<layout class="QVBoxLayout" name="verticalLayout">'
        '<item><widget class="QPushButton" name="button0"/></item>'
        + "".join('<item><widget class="QLineEdit" name="edit%d"/></item>' % i for i in range(20))
        + "</layout></widget><resources/><connections>%s</connections></ui>" % "".join(conns)
    )
    log = open_log(xml)
    button = log.document.by_name("button0")[0]
    flip = {"name": "buttonOne"}

    def codec() -> None:
        parsed = parse_steps(text)
        if parsed.error is not None or len(parsed.steps) != 50:
            raise RuntimeError(parsed.error)

    def rename() -> None:
        nxt = "buttonTwo" if flip["name"] == "buttonOne" else "buttonOne"
        log.execute(Rename(button, nxt))
        flip["name"] = nxt

    def read_small() -> None:
        # A new tail misses the text cache, so the sample includes the parse.
        read_window(root, "small.py", text=small[:-12] + "# %08d\n" % seq["read"])
        seq["read"] += 1

    def read_large() -> None:
        read_window(root, "large.py", text=large[:-12] + "# %08d\n" % seq["read"])
        seq["read"] += 1

    def read_cached() -> None:
        read_window(root, "small.py", text=small, token="warm-small")

    checked = {"read": read_window(root, "small.py", text=small, token="checks")}

    def checks() -> None:
        check_handlers(log.document, checked["read"], classes=QtClassTable.shared())

    specs = [
        Spec("m6 codec 50 steps", None, 1.0, codec, note="parse and write a 50-step list"),
        Spec("m6 rename 40 events", None, 3.0, rename, note="40 connections and 60 logic properties"),
        Spec("m6 read window 100 KB", None, 30.0, read_small, note="pre-scan plus ast"),
        Spec("m6 read window 1 MB", None, 250.0, read_large, note="pre-scan plus ast, idle"),
        Spec("m6 read window cached", None, 1.0, read_cached, note="same editor token"),
        Spec("m6 code checks cached", None, 5.0, checks, note="against a cached reading"),
    ]
    names = tuple((spec.point, spec.widgets, spec.budget_ms) for spec in specs)

    def teardown() -> None:
        import shutil

        shutil.rmtree(root, ignore_errors=True)

    engine_group.names = names  # type: ignore[attr-defined]
    return specs, teardown


def engine_group() -> Tuple[List[Spec], Callable[[], None]]:
    return _engine_group()


def _ui_group() -> Tuple[List[Spec], Callable[[], None]]:
    import gc

    from app.features.form_builder.engine.codegen.api import generate_form_module
    from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
    from app.features.form_builder.engine.logic.events_codec import call_step, slot_step
    from app.features.form_builder.engine.query.selection import SelectionSource
    from app.features.form_builder.engine.project.forms import FormScope
    from app.features.form_builder.engine.ui4.writer import write_ui
    from app.features.form_builder.integration.handlers import MethodRequest
    from app.features.form_builder.integration.handlers_code import SERVICE
    from app.features.form_builder.qtside.inspector.pane import TabId
    from app.features.form_builder.qtside.pickers import open_event_picker
    from app.features.form_builder.qtside.pickers.flow import PickerSource
    from tests.form_builder.qtside.test_m3_keyboard_scripts import _close, _session
    from tests.form_builder.qtside.test_m6_2b_perf import _window_source
    from tests.form_builder.qtside.test_m6_m6_1b_perf import _form

    app = _app()
    folder = Path(tempfile.mkdtemp(prefix="m6r-ui-")).resolve()
    window, kb, guard = _session(folder, app, _form())
    surface = kb.surface
    session = kb.session
    doc = session.document
    inspector = surface.workbench.inspector
    canvas = surface.workbench.canvas
    path = folder / "shop" / "forms" / "customer_window.py"
    path.write_text(_window_source(), encoding="utf-8")
    qapp = app
    seq = {"n": 0, "commit": 0, "key": 0}
    keys = ("e", "ed", "edi", "edit", "edit1", "")
    picker = open_event_picker(inspector, PickerSource("button0", "clicked"), "")
    qapp.processEvents()
    one = (slot_step("edit0", "clear()"),)
    ten = tuple(slot_step("edit%d" % index, "clear()") for index in range(10))
    session.log.execute(SetEventSteps("button10", "clicked", ten, caption="Ten"))
    qapp.processEvents()

    def _select(name: str) -> None:
        session.selection.set((doc.by_name(name)[0],), source=SelectionSource.PROGRAM)
        inspector.flush()

    def behavior() -> None:
        _select("bigList")

    def prepare_behavior() -> None:
        inspector.focus_tab(TabId.BEHAVIOR)
        _select("edit3")
        qapp.processEvents()

    def keystroke() -> None:
        picker.search.setText(keys[seq["key"] % len(keys)])
        seq["key"] += 1
        picker.repaint()

    def command_only() -> None:
        steps = one if seq["commit"] % 2 == 0 else ()
        seq["commit"] += 1
        session.log.execute(SetEventSteps("button0", "clicked", steps, caption="Connect"))

    def repaint() -> None:
        canvas.repaint()
        inspector.repaint()
        qapp.processEvents()

    def commit_paint() -> None:
        command_only()
        repaint()

    def arrows() -> None:
        canvas.repaint()

    def show_all() -> None:
        from app.features.form_builder.integration.workbench_ext.connections import links_for

        host = links_for(surface)
        if host is not None:
            host.toggle_show_all()
        canvas.repaint()

    def open_overlay() -> None:
        surface.modes.open("connections")
        qapp.processEvents()

    def close_overlay() -> None:
        surface.modes.close()
        qapp.processEvents()

    def drag_frame() -> None:
        canvas.repaint()
        qapp.processEvents()

    def _gesture(prefix: str) -> None:
        seq["n"] += 1
        name = "%s_%d" % (prefix, seq["n"])
        out = SERVICE.make_method(
            surface,
            MethodRequest(
                "Write code",
                (SetEventSteps("button1", "clicked", (call_step(name),), caption="Call %s" % name),),
                name,
                "",
                "button1",
                "clicked",
            ),
        )
        if not out.ok:
            raise RuntimeError(out.reason)
        # Paint the caret. Do not pump the event loop: the save's history
        # checkpoint and lint are posted for the next turn, and pumping would
        # put them back on this gesture's clock.
        canvas.repaint()
        inspector.repaint()

    def clean_gesture() -> None:
        _gesture("clean")

    def dirty_gesture() -> None:
        _gesture("dirty")

    def file_closed() -> None:
        _gesture("closed")

    def close_tab() -> None:
        manager = getattr(window, "_editor_manager", None)
        close = getattr(manager, "close_file", None)
        if callable(close) and path.is_file():
            close(str(path))
            qapp.processEvents()

    def open_tab() -> None:
        window._editor_tab_workflow.open_file_at_line(str(path), 1)
        qapp.processEvents()

    def dirty_tab() -> None:
        open_tab()
        editor = window._workspace_controller.widget_for_path(str(path))
        if editor is not None:
            editor.insertPlainText("\n# scratch\n")
        qapp.processEvents()

    def f12_open() -> None:
        SERVICE.go_to(surface, "method_0")
        qapp.processEvents()

    def f12_closed() -> None:
        SERVICE.go_to(surface, "method_1")
        qapp.processEvents()

    scope = FormScope(
        kind="project",
        ui_path=str(folder / "shop" / "forms" / "customer.ui"),
        project_root=str(folder / "shop"),
        generated_path=str(folder / "shop" / "forms" / "ui_customer.py"),
        window_path=str(path),
        module_name="ui_customer",
    )

    def save_form() -> None:
        written = write_ui(doc)
        generate_form_module(doc, scope=scope, source_bytes=written.text.encode("utf-8"))

    specs = [
        Spec("m6 behavior fill", 300, KEY_BUDGET_MS, behavior, prepare=prepare_behavior, note="widget with 20 events"),
        Spec("m6 picker keystroke", 300, KEY_BUDGET_MS, keystroke, note="event picker"),
        Spec("m6 step commit command", 300, 2.0, command_only, note="SetEventSteps alone"),
        Spec(
            "m6 step commit added",
            300,
            50.0,
            commit_paint,
            baseline=repaint,
            note="command through repaint, minus the repaint",
        ),
        Spec(
            "m6 arrows",
            300,
            4.0,
            arrows,
            prepare=lambda: _select("button10"),
            note="selection with 10 connections",
        ),
        Spec("m6 show all", 300, KEY_BUDGET_MS, show_all, note="120 events on the reference form"),
        Spec("m6 open connections", 300, 50.0, open_overlay, cleanup=close_overlay),
        Spec("m6 link drag frame", 300, KEY_BUDGET_MS, drag_frame, prepare=open_overlay, cleanup=close_overlay),
        Spec("m6 double-click tab open", 300, 80.0, clean_gesture, prepare=open_tab, note="clean tab, history deferred"),
        Spec("m6 double-click dirty tab", 300, 80.0, dirty_gesture, prepare=dirty_tab),
        Spec("m6 double-click file not open", 300, 200.0, file_closed, prepare=close_tab),
        Spec("m6 F12 tab open", 300, 30.0, f12_open, prepare=open_tab),
        Spec("m6 F12 not open", 300, 150.0, f12_closed, prepare=close_tab),
        Spec("m6 save 40 step lists", 300, 60.0, save_form, note="write plus generate"),
    ]
    ui_group.names = tuple((spec.point, spec.widgets, spec.budget_ms) for spec in specs)  # type: ignore[attr-defined]

    def teardown() -> None:
        gc.collect()
        try:
            picker.release()
        except Exception:
            pass
        _close(window, qapp, guard)
        import shutil

        shutil.rmtree(folder, ignore_errors=True)

    return specs, teardown


def ui_group() -> Tuple[List[Spec], Callable[[], None]]:
    return _ui_group()


ENGINE_NAMES: Tuple[Name, ...] = (
    ("m6 codec 50 steps", None, 1.0),
    ("m6 rename 40 events", None, 3.0),
    ("m6 read window 100 KB", None, 30.0),
    ("m6 read window 1 MB", None, 250.0),
    ("m6 read window cached", None, 1.0),
    ("m6 code checks cached", None, 5.0),
)
UI_NAMES: Tuple[Name, ...] = (
    ("m6 behavior fill", 300, KEY_BUDGET_MS),
    ("m6 picker keystroke", 300, KEY_BUDGET_MS),
    ("m6 step commit command", 300, 2.0),
    ("m6 step commit added", 300, 50.0),
    ("m6 arrows", 300, 4.0),
    ("m6 show all", 300, KEY_BUDGET_MS),
    ("m6 open connections", 300, 50.0),
    ("m6 link drag frame", 300, KEY_BUDGET_MS),
    ("m6 double-click tab open", 300, 80.0),
    ("m6 double-click dirty tab", 300, 80.0),
    ("m6 double-click file not open", 300, 200.0),
    ("m6 F12 tab open", 300, 30.0),
    ("m6 F12 not open", 300, 150.0),
    ("m6 save 40 step lists", 300, 60.0),
)

GROUPS: Tuple[Group, ...] = (
    Group("engine", ENGINE_NAMES, engine_group),
    Group("ui", UI_NAMES, ui_group),
)


def main(argv: Optional[object] = None) -> int:
    import argparse
    import sys

    from tests.form_builder.perf import harness

    parser = argparse.ArgumentParser(description="UX-M6-003 speed rows")
    parser.add_argument("--samples", type=int, default=40)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--only", default="")
    args = parser.parse_args(list(argv) if argv is not None else sys.argv[1:])  # type: ignore[arg-type]
    only = tuple(item for item in args.only.split(",") if item)
    report = harness.run_m6_speed(samples=args.samples, warmup=args.warmup, only=only)
    sys.stdout.write(harness.format_table(report))
    sys.stdout.write("load start %s end %s\n" % (report.load_start, report.load_end))
    return 0 if report.ok else 1


if __name__ == "__main__":
    import sys

    raise SystemExit(main())
