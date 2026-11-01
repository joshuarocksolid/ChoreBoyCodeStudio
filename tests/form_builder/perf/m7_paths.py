# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false
"""UX-M7-003 Mac rows.

The form is the M6 reference form plus 100 rules and 60 checks. Run it with
the FreeCAD python.

``python -m tests.form_builder.perf.m7_paths``

20 samples, the first dropped, Hyndman-Fan p50 and p95, process CPU, load on
every row, and the M6.R idle loop. A miss is profiled into
``docs/form_builder/orch/m7r_mac/results/``.
"""

from __future__ import annotations

import gc
import json
import os
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from tests.form_builder.perf.stats import percentile

RUNS = 20
IDLE_LOOPS = 116000
LOAD_LIMIT = 4.0
LOAD_WAIT_S = 15 * 60
ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / "docs" / "form_builder" / "orch" / "m7r_mac" / "results"
TARGET = "field0000"
PREVIEW_EDIT = "field0096"
FORMULA = "1" + (" + 1" * 49) + "   "
_FORMULA_KEYS = (
    "cbcsEnabledWhen",
    "cbcsVisibleWhen",
    "cbcsReadOnlyWhen",
    "cbcsValue",
    "cbcsDefault",
)


@dataclass(frozen=True)
class BudgetRow:
    key: str
    title: str
    budget_ms: float


MAC_ROWS: Tuple[BudgetRow, ...] = (
    BudgetRow("analyze_compile", "Analyze plus compile a 200-character formula", 2.0),
    BudgetRow("formula_keystroke", "Formula-editor keystroke", 16.0),
    BudgetRow("behavior_fill", "Behavior tab fill", 16.0),
    BudgetRow("commit_added", "Commit a rule, added", 17.0),
    BudgetRow("save", "Save with generate", 80.0),
    BudgetRow("cbcs_refresh", "Generated cbcs_refresh", 5.0),
    BudgetRow("preview_reload", "Preview reload after a rule edit", 500.0),
)
_BUDGETS = {item.key: item.budget_ms for item in MAC_ROWS}


def paired_added(commit_ms: Sequence[float], bare_ms: Sequence[float]) -> List[float]:
    """Commit minus the paired bare sample. The first sample of each series is warmup."""
    commit = list(commit_ms)[1:]
    bare = list(bare_ms)[1:]
    return [max(0.0, left - right) for left, right in zip(commit, bare)]


def _load() -> List[float]:
    try:
        return [round(float(value), 2) for value in os.getloadavg()]
    except OSError:
        return []


def _p(samples: Sequence[float], fraction: float) -> float:
    return percentile(list(samples), fraction)


def _idle() -> str:
    # Fixed work, about 5 ms of CPU on an idle Mac. A loaded host takes longer.
    total = 0
    for index in range(IDLE_LOOPS):
        total += index
    if total < 0:
        raise RuntimeError("idle")
    return "The loop added the integers from 0 through 115999."


def reference_xml() -> str:
    """M6 reference form with the rules and checks stored as cbcs properties."""
    from app.features.form_builder.engine.commands.base import CommandRejected
    from app.features.form_builder.engine.commands.catalog import SetLogic
    from app.features.form_builder.engine.logic.checks import Length, Preset, Required, write_checks
    from app.features.form_builder.engine.ui4.writer import write_ui
    from tests.form_builder.perf.reference import DEFAULT_SEED, reference_form
    from tests.support.form_builder.command_fixtures import open_log

    if len(FORMULA) != 200:
        raise RuntimeError("the formula is %d characters" % len(FORMULA))
    built = reference_form(300, DEFAULT_SEED)
    log = open_log(built.xml)
    document = log.document
    three = write_checks(
        (
            Required("Name is required"),
            Length(1, 12, "Keep it short"),
            Preset("email", "Enter an email address"),
        )
    )
    one = write_checks((Required("Name is required"),))
    if not three or not one:
        raise RuntimeError("checks did not serialize")

    def put(name: str, key: str, text: str) -> None:
        found = document.by_name(name)
        if not found:
            raise RuntimeError("the reference form has no %s" % name)
        try:
            outcome = log.execute(SetLogic(found[0], key, text))
        except CommandRejected as exc:
            raise RuntimeError("%s %s rejected. %s" % (name, key, exc)) from exc
        if outcome.noop:
            raise RuntimeError("%s %s was a no-op" % (name, key))

    put(TARGET, "cbcsEnabledWhen", "True")
    put(TARGET, "cbcsVisibleWhen", "True")
    put(TARGET, "cbcsReadOnlyWhen", "False")
    put(TARGET, "cbcsValue", '"ready"')
    put(TARGET, "cbcsDefault", '"0"')
    for index in range(1, 96):
        put("field%04d" % index, "cbcsEnabledWhen", "True")
    put(TARGET, "cbcsValidate", three)
    for index in range(1, 58):
        put("field%04d" % index, "cbcsValidate", one)
    if not document.by_name(PREVIEW_EDIT):
        raise RuntimeError("the reference form has no %s" % PREVIEW_EDIT)
    xml = write_ui(document).text
    rules, checks = count_logic(xml)
    if rules != 100 or checks != 60:
        raise RuntimeError("stored %d rules and %d checks" % (rules, checks))
    return xml


def count_logic(xml: str) -> Tuple[int, int]:
    """Rule properties and check objects the product would read back."""
    from app.features.form_builder.engine.ids import IdAllocator
    from app.features.form_builder.engine.logic.checks import read_checks
    from app.features.form_builder.engine.ui4.reader import read_ui
    from app.features.form_builder.engine.ui4.values import CStringValue, StringValue

    document = read_ui(xml, allocator=IdAllocator()).document
    rules = 0
    checks = 0
    for node in document.iter_widgets():
        for key in _FORMULA_KEYS:
            value = node.value(key)
            text = getattr(value, "text", "")
            if isinstance(text, str) and text.strip():
                rules += 1
        raw = node.value("cbcsValidate")
        blob = getattr(raw, "text", "")
        if not isinstance(blob, str) or not blob.strip():
            continue
        found = read_checks(blob)
        if found.error is not None:
            raise RuntimeError("cbcsValidate on %s failed. %s" % (node.object_name, found.error))
        checks += len(found.checks)
    return rules, checks


def _wait_for_load() -> Dict[str, Any]:
    started = time.monotonic()
    waits = 0
    while True:
        load = _load()
        elapsed = time.monotonic() - started
        if not load or load[0] <= LOAD_LIMIT or elapsed >= LOAD_WAIT_S:
            return {
                "waited_s": round(elapsed, 1),
                "waits": waits,
                "load": load,
                "gave_up": bool(load) and load[0] > LOAD_LIMIT,
            }
        time.sleep(30)
        waits += 1


def _row_from_samples(samples_s: Sequence[float], *, evidence: str, error: str = "") -> Dict[str, Any]:
    judged = list(samples_s)[1:] if len(samples_s) > 1 else list(samples_s)
    return {
        "n": len(samples_s),
        "judged": len(judged),
        "warmup_dropped": 1 if len(samples_s) > 1 else 0,
        "p50_ms": round(_p(judged, 0.50) * 1000.0, 3) if judged else None,
        "p95_ms": round(_p(judged, 0.95) * 1000.0, 3) if judged else None,
        "load": _load(),
        "samples_ms": [round(value * 1000.0, 3) for value in samples_s],
        "evidence": evidence,
        "error": error,
    }


def _time(fn: Callable[[], str], prepare: Optional[Callable[[], None]] = None) -> Dict[str, Any]:
    samples: List[float] = []
    evidence = ""
    error = ""
    for _index in range(RUNS):
        started = time.process_time()
        try:
            if prepare is not None:
                prepare()
            gc.collect()
            started = time.process_time()
            evidence = fn() or evidence
        except Exception:
            samples.append(max(0.0, time.process_time() - started))
            error = traceback.format_exc()
            break
        samples.append(max(0.0, time.process_time() - started))
    return _row_from_samples(samples, evidence=evidence, error=error)


def _judge(row: Dict[str, Any], budget_ms: Optional[float]) -> None:
    row["budget_ms"] = budget_ms
    if budget_ms is None:
        row["pass"] = None
        return
    if row.get("error") or row.get("p95_ms") is None:
        row["pass"] = False
        return
    row["pass"] = bool(float(row["p95_ms"]) <= budget_ms)


def _maybe_profile(
    key: str,
    row: Dict[str, Any],
    fn: Callable[[], str],
    prepare: Optional[Callable[[], None]] = None,
) -> None:
    budget = _BUDGETS.get(key)
    p95 = row.get("p95_ms")
    if budget is None or row.get("pass") or p95 is None or float(p95) <= budget:
        return
    try:
        row["hottest"] = _profile(key, fn, prepare)
    except Exception:
        row["profile_error"] = traceback.format_exc()


def _profile(name: str, fn: Callable[[], str], prepare: Optional[Callable[[], None]] = None) -> str:
    import cProfile
    import io
    import pstats

    profiler = cProfile.Profile()
    for _index in range(8):
        if prepare is not None:
            prepare()
        gc.collect()
        profiler.enable()
        try:
            fn()
        finally:
            profiler.disable()
    buffer = io.StringIO()
    stats = pstats.Stats(profiler, stream=buffer)
    stats.sort_stats("cumulative").print_stats(45)
    stats.sort_stats("tottime").print_stats(30)
    text = buffer.getvalue()
    hot = _hot_words(_hottest_token(text))
    path = RESULTS / ("profile_%s.txt" % name)
    path.write_text("hottest %s\n%s" % (hot, text), encoding="utf-8")
    return hot


def _hottest_token(text: str) -> str:
    armed = False
    for line in text.splitlines():
        if "Ordered by: internal time" in line or "Ordered by: tottime" in line:
            armed = True
            continue
        if not armed or not line.strip() or line.strip().startswith("ncalls"):
            continue
        if "restriction <" in line:
            continue
        parts = line.split()
        if len(parts) >= 6 and "(" in parts[-1]:
            return parts[-1]
    return "unknown"


def _hot_words(token: str) -> str:
    if token.startswith("{") and token.endswith("}"):
        return token[1:-1]
    if token.endswith(")") and "(" in token:
        place, _, name = token.rpartition("(")
        file_part = place.rsplit(":", 1)[0]
        return "%s in %s" % (name[:-1], file_part)
    return token


def _preview_command() -> Tuple[List[str], str]:
    """Launch the real preview script.

    An already-set AppRun is used as AppRun. Otherwise the measurement python
    starts ``run_form_preview.py``. ``CBCS_FB_APPRUN`` is not pointed at the
    conda PySide2 launcher.
    """
    from app.features.form_builder.qtside.preview.launch import (
        apprun_preview_command,
        current_runtime_python,
        python_preview_command,
        repo_root,
    )

    root = repo_root()
    script = os.path.join(root, "run_form_preview.py")
    if not os.path.isfile(script):
        raise RuntimeError("run_form_preview.py is missing")
    configured = os.environ.get("CBCS_FB_APPRUN", "").strip() or os.environ.get("CBCS_FB_APPRUN_11", "").strip()
    if configured:
        if not os.path.isfile(configured):
            raise RuntimeError("CBCS_FB_APPRUN is not a file. %s" % configured)
        return apprun_preview_command(configured, root), configured
    python = current_runtime_python()
    if not os.path.isfile(python):
        raise RuntimeError("preview python is missing. %s" % python)
    return python_preview_command(python, root), python


def _clear_old_profiles() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    for old in RESULTS.glob("profile_*.txt"):
        old.unlink()


def _measure() -> Dict[str, Any]:
    import sys

    print("waiting for load", flush=True)
    waited = _wait_for_load()
    print("load %s" % waited["load"], flush=True)
    rows: Dict[str, Any] = {"idle_reference": _time(_idle)}
    _judge(rows["idle_reference"], None)
    print("idle_reference p95 %s" % rows["idle_reference"]["p95_ms"], flush=True)
    xml = reference_xml()
    print("form stored 100 rules and 60 checks", flush=True)
    _engine_rows(rows, xml)
    try:
        _shell_rows(rows, xml)
    except Exception:
        err = traceback.format_exc()
        print(err, flush=True)
        for spec in MAC_ROWS:
            if spec.key not in rows:
                rows[spec.key] = _row_from_samples([], evidence="", error=err)
                _judge(rows[spec.key], spec.budget_ms)
    return {
        "runs": RUNS,
        "warmup_dropped": 1,
        "platform": os.environ.get("QT_QPA_PLATFORM", ""),
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "load_wait": waited,
        "load": _load(),
        "rows": rows,
    }


def _engine_rows(rows: Dict[str, Any], xml: str) -> None:
    from types import SimpleNamespace

    from app.features.form_builder.engine.logic.formula import SlotKind, analyze, compile_formula
    from app.features.form_builder.engine.logic.formula.types import WHOLE
    from app.features.form_builder.engine.logic.formula_env import env_for
    from app.features.form_builder.engine.ui4.defaults import QtClassTable
    from app.features.form_builder.qtside.formula.editor import FormulaEditor
    from app.qt.QtWidgets import QApplication, QLabel
    from tests.form_builder.qtside.support import open_session

    app = QApplication.instance() or QApplication([])
    session = open_session(xml, "/tmp/cbcs-m7-reference.ui")
    editor = FormulaEditor()
    label = QLabel()
    try:
        env = env_for(session.document, None, QtClassTable.shared())
        slot = SlotKind.value(WHOLE)

        def analyze_compile() -> str:
            analysis = analyze(FORMULA, env, slot)
            emitted = compile_formula(analysis, env)
            if analysis.tree is None or not emitted.source:
                raise RuntimeError("analyze or compile returned nothing")
            return "Compiled source is %d characters." % len(emitted.source)

        editor.set_status_label(label)
        editor.resize(420, 72)
        editor.show()
        label.show()
        editor.set_context(env, slot, SimpleNamespace())
        app.processEvents()

        def prepare_key() -> None:
            editor.setPlainText("0")

        def keystroke() -> str:
            editor.setPlainText(FORMULA)
            editor.repaint()
            label.repaint()
            text = label.text().replace("\n", " ")
            if "now:" not in text:
                raise RuntimeError("status label has no now line. %s" % text)
            return "The status label contained the now mark."

        print("analyze", flush=True)
        rows["analyze_compile"] = _time(analyze_compile)
        _judge(rows["analyze_compile"], 2.0)
        _maybe_profile("analyze_compile", rows["analyze_compile"], analyze_compile)
        print("keystroke", flush=True)
        rows["formula_keystroke"] = _time(keystroke, prepare_key)
        _judge(rows["formula_keystroke"], 16.0)
        _maybe_profile("formula_keystroke", rows["formula_keystroke"], keystroke, prepare_key)
        print(
            "analyze p95 %s keystroke p95 %s"
            % (rows["analyze_compile"]["p95_ms"], rows["formula_keystroke"]["p95_ms"]),
            flush=True,
        )
        _time_refresh(rows, session.document)
    finally:
        editor.deleteLater()
        label.deleteLater()
        app.processEvents()
        session.dispose()


def _time_refresh(rows: Dict[str, Any], document: object) -> None:
    import re
    import shutil
    import tempfile

    from app.features.form_builder.engine.codegen.api import generate_form_module
    from app.features.form_builder.engine.project.forms import FormScope
    from app.qt.QtWidgets import QApplication, QMainWindow

    folder = Path(tempfile.mkdtemp(prefix="m7r-refresh-"))
    host = None
    app = QApplication.instance()
    try:
        scope = FormScope(
            kind="project",
            ui_path=str(folder / "forms" / "order.ui"),
            project_root=str(folder),
            generated_path=str(folder / "forms" / "ui_order.py"),
            window_path=str(folder / "forms" / "order_window.py"),
            module_name="ui_order",
        )
        (folder / "forms").mkdir(parents=True)
        made = generate_form_module(document, scope=scope, source_bytes=None)  # type: ignore[arg-type]
        text = made.text or ""
        if "def cbcs_refresh" not in text:
            rows["cbcs_refresh"] = _row_from_samples(
                [],
                evidence="",
                error="generate did not emit cbcs_refresh. %s"
                % " ".join("%s %s" % (item.code, item.message) for item in made.diagnostics),
            )
            _judge(rows["cbcs_refresh"], 5.0)
            return
        match = re.search(r"^class (Ui_\w+)\b", text, re.MULTILINE)
        if match is None:
            rows["cbcs_refresh"] = _row_from_samples([], evidence="", error="generated module has no Ui class")
            _judge(rows["cbcs_refresh"], 5.0)
            return
        namespace: Dict[str, Any] = {"__name__": "ui_order_m7"}
        exec(compile(text, str(scope.generated_path), "exec"), namespace)
        ui = namespace[match.group(1)]()
        host = QMainWindow()
        ui.setupUi(host)
        field = getattr(ui, TARGET, None)
        if field is None or not hasattr(field, "setText"):
            rows["cbcs_refresh"] = _row_from_samples([], evidence="", error="generated ui has no %s" % TARGET)
            _judge(rows["cbcs_refresh"], 5.0)
            return

        def prepare() -> None:
            field.setText("")

        def refresh() -> str:
            ui.cbcs_refresh()
            shown = field.text()
            if shown != "ready":
                raise RuntimeError("cbcs_refresh left the text %r" % shown)
            return "cbcs_refresh set the target field to ready."

        print("refresh", flush=True)
        rows["cbcs_refresh"] = _time(refresh, prepare)
        _judge(rows["cbcs_refresh"], 5.0)
        _maybe_profile("cbcs_refresh", rows["cbcs_refresh"], refresh, prepare)
        print("refresh p95 %s" % rows["cbcs_refresh"]["p95_ms"], flush=True)
    finally:
        if host is not None:
            host.deleteLater()
        if app is not None:
            app.processEvents()
        shutil.rmtree(folder, ignore_errors=True)


def _shell_rows(rows: Dict[str, Any], xml: str) -> None:
    import shutil
    import tempfile

    from app.qt.QtWidgets import QApplication
    from tests.form_builder.qtside.test_m3_keyboard_scripts import _close, _session

    app = QApplication.instance() or QApplication([])
    # macOS mkdtemp returns /var, and the editor binds the /private/var real path.
    folder = Path(tempfile.mkdtemp(prefix="m7r-shell-")).resolve()
    window = None
    guard = None
    pool = None
    try:
        print("opening the reference form", flush=True)
        window, kb, guard = _session(folder, app, xml)
        _behavior_save_commit(rows, app, kb)
        pool = _time_preview(rows, kb)
    finally:
        if pool is not None:
            try:
                pool.shutdown()
            except Exception:
                traceback.print_exc()
        if window is not None and guard is not None:
            try:
                _close(window, app, guard)
            except Exception:
                traceback.print_exc()
        shutil.rmtree(folder, ignore_errors=True)


def _behavior_save_commit(rows: Dict[str, Any], app: Any, kb: Any) -> None:
    from app.features.form_builder.engine.commands.catalog import SetLogic
    from app.features.form_builder.engine.query.selection import SelectionSource
    from app.features.form_builder.integration.save_pipeline import finish_save, pipeline_bytes
    from app.features.form_builder.qtside.inspector.pane import TabId
    from app.qt.QtWidgets import QLabel, QWidget

    surface = kb.surface
    session = kb.session
    document = session.document
    inspector = surface.workbench.inspector
    canvas = surface.workbench.canvas
    scope = session.scope
    ui_path = Path(kb.path)

    def select(name: str) -> None:
        session.selection.set((document.by_name(name)[0],), source=SelectionSource.PROGRAM)
        inspector.flush()

    def paint() -> None:
        canvas.repaint()
        inspector.repaint()
        app.processEvents()

    inspector.isVisible = lambda: True
    inspector.focus_tab(TabId.BEHAVIOR)
    select("field0001")
    for _turn in range(4):
        app.processEvents()

    def prepare_behavior() -> None:
        select("field0001")
        app.processEvents()

    def behavior() -> str:
        select(TARGET)
        state = inspector.findChild(QLabel, "formBuilder.state.title")
        checks = inspector.findChild(QLabel, "formBuilder.checks.title")
        events = inspector.findChild(QWidget, "formBuilder.events")
        if state is None or state.text() != "STATE":
            raise RuntimeError("STATE did not fill")
        if checks is None or checks.text() != "CHECKS":
            raise RuntimeError("CHECKS did not fill")
        if events is None:
            raise RuntimeError("Events did not fill")
        nows = []
        for key in _FORMULA_KEYS:
            label = inspector.findChild(QLabel, "formBuilder.state.now.%s" % key)
            nows.append("" if label is None else label.text())
        if any("now:" not in text for text in nows):
            raise RuntimeError("now lines were %s" % (nows,))
        missing = [
            index
            for index in range(3)
            if inspector.findChild(QWidget, "formBuilder.checks.row.%d" % index) is None
        ]
        if missing:
            raise RuntimeError("missing check rows %s" % (missing,))
        return "STATE showed five now lines and CHECKS showed three rows."

    print("behavior", flush=True)
    rows["behavior_fill"] = _time(behavior, prepare_behavior)
    _judge(rows["behavior_fill"], 16.0)
    _maybe_profile("behavior_fill", rows["behavior_fill"], behavior, prepare_behavior)
    print("behavior p95 %s" % rows["behavior_fill"]["p95_ms"], flush=True)

    def save() -> str:
        text = pipeline_bytes(document)
        ui_path.write_text(text, encoding="utf-8")
        notice = finish_save(scope, document, text)
        generated = str(getattr(scope, "generated_path", "") or "")
        if notice.kind != "generated":
            raise RuntimeError(notice.text)
        if not generated or not os.path.isfile(generated) or os.path.getsize(generated) < 1:
            raise RuntimeError("generate did not write a file")
        return "Saved %s and wrote %s." % (ui_path.name, os.path.basename(generated))

    print("save", flush=True)
    rows["save"] = _time(save)
    _judge(rows["save"], 80.0)
    generated = str(getattr(scope, "generated_path", "") or "")
    if not rows["save"].get("error") and generated and os.path.isfile(generated):
        body = Path(generated).read_text(encoding="utf-8")
        if "def cbcs_refresh" not in body:
            rows["save"]["error"] = "the generated file has no cbcs_refresh"
            rows["save"]["pass"] = False
        else:
            rows["save"]["evidence"] += " The file defines cbcs_refresh."
    _maybe_profile("save", rows["save"], save)
    print("save p95 %s" % rows["save"]["p95_ms"], flush=True)

    owner = document.by_name(TARGET)[0]
    flip = {"text": "False"}

    def bare() -> str:
        paint()
        return "bare repaint"

    def commit() -> str:
        text = flip["text"]
        flip["text"] = "True" if text == "False" else "False"
        session.log.execute(SetLogic(owner, "cbcsVisibleWhen", text))
        paint()
        stored = document.node(owner).value("cbcsVisibleWhen")
        if getattr(stored, "text", "") != text:
            raise RuntimeError("stored text was %r" % getattr(stored, "text", None))
        label = inspector.findChild(QLabel, "formBuilder.state.value.cbcsVisibleWhen")
        shown = "" if label is None else label.text()
        if text not in shown:
            raise RuntimeError("inspector showed %r" % shown)
        return "Visible when is stored as %s and the inspector shows it." % text

    print("commit", flush=True)
    for _turn in range(4):
        app.processEvents()
    bare_row = _time(bare)
    commit_row = _time(commit)
    rows["bare_repaint"] = bare_row
    rows["commit"] = commit_row
    added = paired_added(commit_row.get("samples_ms") or [], bare_row.get("samples_ms") or [])
    added_row: Dict[str, Any] = {
        "n": len(added),
        "judged": len(added),
        "warmup_dropped": 1,
        "p50_ms": round(_p(added, 0.50), 3) if added else None,
        "p95_ms": round(_p(added, 0.95), 3) if added else None,
        "load": _load(),
        "samples_ms": [round(value, 3) for value in added],
        "evidence": commit_row.get("evidence") or "",
        "error": commit_row.get("error") or bare_row.get("error") or "",
        "derived": "commit minus bare_repaint, paired by run, warmup dropped",
        "bare_p95_ms": bare_row.get("p95_ms"),
        "commit_p95_ms": commit_row.get("p95_ms"),
    }
    _judge(added_row, 17.0)
    rows["commit_added"] = added_row
    _maybe_profile("commit_added", added_row, commit)
    print("commit_added p95 %s" % added_row["p95_ms"], flush=True)


def _time_preview(rows: Dict[str, Any], kb: Any) -> object:
    from app.features.form_builder.engine.commands.catalog import SetLogic
    from app.features.form_builder.engine.ipc.timing import DirectorConfig
    from app.features.form_builder.qtside.preview.launch import repo_root
    from app.features.form_builder.qtside.preview.pool import PreviewPool
    from app.qt.QtCore import QEventLoop, QTimer
    from app.qt.qt_compat import exec_qt

    surface = kb.surface
    session = kb.session
    document = session.document
    command, launcher = _preview_command()
    PreviewPool.reset_shared()
    pool = PreviewPool(
        command=command,
        config=DirectorConfig(
            handshake_timeout=90.0,
            request_timeout=45.0,
            shutdown_grace=2.0,
            ping_interval=30.0,
            prewarm=False,
        ),
        root=repo_root(),
    )
    PreviewPool._shared = pool
    control = getattr(surface, "preview_control", None)
    notices = getattr(surface, "own_class_preview", None)
    if control is None or notices is None:
        rows["preview_reload"] = _row_from_samples([], evidence="", error="the form tab has no preview control")
        rows["preview_reload"]["launcher"] = launcher
        _judge(rows["preview_reload"], 500.0)
        return pool

    def wait_response(timeout_s: float) -> object:
        loop = QEventLoop()
        timer = QTimer()
        timer.setInterval(15)

        def poke() -> None:
            if notices.last_response is not None:
                timer.stop()
                loop.quit()

        timer.timeout.connect(poke)
        timer.start()
        QTimer.singleShot(int(timeout_s * 1000), loop.quit)
        exec_qt(loop)
        timer.stop()
        return notices.last_response

    def one_reload() -> str:
        notices.last_response = None
        control.preview()
        response = wait_response(45.0)
        if response is None:
            tail = " | ".join(pool.stderr_tail()[-5:])
            raise RuntimeError("the child did not answer. %s" % tail)
        if not getattr(response, "ok", False):
            raise RuntimeError(
                "child refused %s %s" % (getattr(response, "error", ""), getattr(response, "detail", ""))
            )
        result = getattr(response, "result", None) or {}
        names = result.get("object_names") or []
        if TARGET not in names:
            raise RuntimeError("child object names omit the target field")
        pid = pool.status().child_pid
        if not pid:
            raise RuntimeError("preview response had no child pid")
        return "Child pid %s wrote a response frame listing the target field." % pid

    owner = document.by_name(PREVIEW_EDIT)[0]
    flip = {"text": "True"}

    def prepare() -> None:
        text = flip["text"]
        flip["text"] = "False" if text == "True" else "True"
        session.log.execute(SetLogic(owner, "cbcsEnabledWhen", text))

    print("preview via %s" % launcher, flush=True)
    try:
        prepare()
        prime = one_reload()
        print("preview prime %s" % prime, flush=True)
        spawned = len(pool.spawn_monotonic)
        rows["preview_reload"] = _time(one_reload, prepare)
        rows["preview_reload"]["spawns"] = len(pool.spawn_monotonic)
        rows["preview_reload"]["launcher"] = launcher
        if rows["preview_reload"].get("error"):
            tail = " | ".join(pool.stderr_tail()[-8:])
            if tail:
                rows["preview_reload"]["error"] += "\n" + tail
        elif rows["preview_reload"]["spawns"] != spawned:
            rows["preview_reload"]["evidence"] += " The child was started again during the samples."
        _judge(rows["preview_reload"], 500.0)
        _maybe_profile("preview_reload", rows["preview_reload"], one_reload, prepare)
    except Exception:
        rows["preview_reload"] = _row_from_samples([], evidence="", error=traceback.format_exc())
        tail = " | ".join(pool.stderr_tail()[-8:])
        if tail:
            rows["preview_reload"]["error"] += "\n" + tail
        rows["preview_reload"]["launcher"] = launcher
        _judge(rows["preview_reload"], 500.0)
    print("preview p95 %s" % rows["preview_reload"].get("p95_ms"), flush=True)
    return pool


def _plain_error(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    last = lines[-1]
    if ": " in last:
        kind, _, message = last.partition(": ")
        return "%s. %s" % (kind, message)
    return last


def _load_words(load: object) -> str:
    if isinstance(load, list) and load:
        return " ".join(str(item) for item in load)
    return "unavailable"


def _sentence(title: str, row: Dict[str, Any], idle_p95: object, budget: Optional[float]) -> str:
    if row.get("derived"):
        count = "20 commit samples and 20 bare repaint samples. The first of each was dropped, and %s paired differences were judged." % (
            row.get("judged") or 0
        )
    else:
        count = "%s samples, %s judged after dropping the first." % (row.get("n") or 0, row.get("judged") or 0)
    bits = [
        title + ".",
        count,
        "p50 %s ms." % row.get("p50_ms"),
        "p95 %s ms." % row.get("p95_ms"),
        "Load %s." % _load_words(row.get("load")),
        "Idle reference p95 %s ms." % idle_p95,
    ]
    if budget is not None:
        bits.append("Mac budget %s ms." % budget)
    if row.get("derived"):
        bits.append(
            "Paired commit p95 %s ms against bare repaint p95 %s ms, sample by sample, warmup dropped."
            % (row.get("commit_p95_ms"), row.get("bare_p95_ms"))
        )
    evidence = str(row.get("evidence") or "").strip()
    if evidence:
        bits.append(evidence if evidence.endswith(".") else evidence + ".")
    error = _plain_error(str(row.get("error") or ""))
    if error:
        bits.append("The run stopped. %s" % error)
    if row.get("hottest"):
        bits.append("Profile hot spot is %s." % row["hottest"])
    if budget is None:
        bits.append("No budget. This is the noise floor.")
    elif row.get("pass"):
        bits.append("Pass.")
    else:
        bits.append("Fail.")
    return " ".join(bits)


def _wait_words(waited: Dict[str, Any]) -> str:
    load = _load_words(waited.get("load"))
    if waited.get("gave_up"):
        return (
            "One minute load stayed above 4 for %s seconds, %s rechecks, and the run measured anyway at %s."
            % (waited.get("waited_s"), waited.get("waits"), load)
        )
    if waited.get("waits"):
        return (
            "The run slept until the one minute load was at or under 4. Waited %s seconds. Load then was %s."
            % (waited.get("waited_s"), load)
        )
    return "One minute load at the start was %s, so the run did not sleep." % load


def _write(summary: Dict[str, Any]) -> int:
    rows = summary["rows"]
    idle = rows.get("idle_reference") or {}
    idle_p95 = idle.get("p95_ms")
    failures = []
    for spec in MAC_ROWS:
        row = rows.get(spec.key)
        if row is None or not row.get("pass"):
            failures.append(spec.key)
    summary["failures"] = failures
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    lines = [
        "UX-M7-003 Mac measurement.",
        "%d samples per row. The first sample is warmup and is left out of p50 and p95." % RUNS,
        _wait_words(summary.get("load_wait") or {}),
        "Python %s." % summary.get("executable"),
        "",
        _sentence("Idle reference", idle, idle_p95, None),
        (
            "The idle reference is a fixed loop of %d additions and nothing else. "
            "Its p95 is the noise floor on this machine at this load. "
            "A row whose p95 sits near that number is not a stable reading of the feature."
        )
        % IDLE_LOOPS,
        "",
    ]
    for spec in MAC_ROWS:
        row = rows.get(spec.key) or {
            "n": 0,
            "judged": 0,
            "p50_ms": None,
            "p95_ms": None,
            "load": [],
            "pass": False,
            "error": "missing",
        }
        lines.append(_sentence(spec.title, row, idle_p95, spec.budget_ms))
        lines.append("")
    text = "\n".join(lines).rstrip() + "\n"
    (RESULTS / "summary.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    return 0 if not failures else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    del argv
    _clear_old_profiles()
    summary = _measure()
    return _write(summary)


if __name__ == "__main__":
    import sys

    raise SystemExit(main())
