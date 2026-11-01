"""M7.R timing probe and Try-mode walk for the ChoreBoy VM.

Python 3.9. No pytest. Times the UX-M7-003 rows on the 300-widget reference
form plus 100 rules and 60 checks, then drives the invoice form in the real
preview child. Writes results/ beside this script.

Do not set QT_QPA_PLATFORM. The preview child is the AppRun process.
"""

from __future__ import annotations

import gc
import json
import os
import shutil
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAYLOAD = HERE / "payload"
RESULTS = HERE / "results"
WORK = HERE / "work"
FIXTURE = HERE / "fixture" / "forms"
RUNS = 20
FORMULA = "1" + (" + 1" * 49) + "   "
BUDGETS = {
    "analyze_compile": 6.0,
    "formula_keystroke": 40.0,
    "behavior_fill": 40.0,
    "commit_rule_added": 50.0,
    "save_generate": 250.0,
    "cbcs_refresh": 16.0,
    "preview_reload": 1500.0,
}
RULE_KEYS = (
    "cbcsEnabledWhen",
    "cbcsVisibleWhen",
    "cbcsReadOnlyWhen",
    "cbcsValue",
    "cbcsDefault",
)


def _load():
    # AppArmor on ChoreBoy blocks /proc/loadavg, so os.getloadavg() raises.
    try:
        return [round(value, 2) for value in os.getloadavg()]
    except OSError:
        return None


def _fail(text):
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "error.txt").write_text(text, encoding="utf-8")
    print(text, file=sys.stderr)
    os._exit(1)


def _capture_log(window):
    """Keep logger lines so a declined form tab can be diagnosed on the guest."""
    import logging

    notes = []

    class _Grab(logging.Handler):
        def emit(self, record):
            notes.append(self.format(record))

    handler = _Grab()
    handler.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
    logging.getLogger().addHandler(handler)
    logger = getattr(window, "_logger", None)
    if logger is not None:
        logger.addHandler(handler)
    return notes


def _bound_surface(window, path):
    """The form tab, whether the editor stored the path or its resolved form."""
    registry = window._tab_content_registry
    asked = str(path)
    surface = registry.surface_for_path(asked)
    if surface is not None:
        return surface
    resolved = str(Path(asked).resolve())
    surface = registry.surface_for_path(resolved)
    if surface is not None:
        return surface
    keys = list(registry._surfaces)
    if len(keys) == 1 and keys[0].endswith(Path(asked).name):
        return registry.surface_for_path(keys[0])
    return None


def _p(samples, fraction):
    ordered = sorted(samples)
    if not ordered:
        return 0.0
    # Hyndman-Fan type 7, the same percentile the M6 probe uses.
    rank = (len(ordered) - 1) * fraction
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def _time(fn, prepare=None):
    samples = []
    for _ in range(RUNS):
        if prepare is not None:
            prepare()
        gc.collect()
        started = time.process_time()
        fn()
        samples.append(time.process_time() - started)
    warm = samples[1:] or samples
    return {
        "n": RUNS,
        "warmup_dropped": 1,
        "clock": "cpu",
        "p50_ms": round(_p(warm, 0.50) * 1000.0, 3),
        "p95_ms": round(_p(warm, 0.95) * 1000.0, 3),
        "load": _load(),
        "samples_ms": [round(value * 1000.0, 3) for value in samples],
    }


def _time_wall(fn):
    samples = []
    cpu = []
    for _ in range(RUNS):
        gc.collect()
        cpu0 = time.process_time()
        wall0 = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - wall0)
        cpu.append(time.process_time() - cpu0)
    warm = samples[1:] or samples
    warm_cpu = cpu[1:] or cpu
    return {
        "n": RUNS,
        "warmup_dropped": 1,
        "clock": "wall",
        "p50_ms": round(_p(warm, 0.50) * 1000.0, 3),
        "p95_ms": round(_p(warm, 0.95) * 1000.0, 3),
        "cpu_p50_ms": round(_p(warm_cpu, 0.50) * 1000.0, 3),
        "cpu_p95_ms": round(_p(warm_cpu, 0.95) * 1000.0, 3),
        "load": _load(),
        "samples_ms": [round(value * 1000.0, 3) for value in samples],
    }


def _idle():
    total = 0
    for index in range(116000):
        total += index
    if total < 0:
        raise RuntimeError("idle")


def _profile(name, fn, prepare=None, runs=8):
    import cProfile
    import io
    import pstats

    profiler = cProfile.Profile()
    for _ in range(runs):
        if prepare is not None:
            prepare()
        gc.collect()
        profiler.enable()
        fn()
        profiler.disable()
    out = io.StringIO()
    stats = pstats.Stats(profiler, stream=out)
    stats.sort_stats("cumulative").print_stats(40)
    text = out.getvalue()
    (RESULTS / ("profile_%s.txt" % name)).write_text(text, encoding="utf-8")
    return _top_frame(text)


def _top_frame(text):
    seen = False
    first = ""
    app_frame = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("ncalls"):
            seen = True
            continue
        if not seen or not stripped:
            continue
        if not first:
            first = stripped
        if "/app/" in stripped or stripped.startswith("app/"):
            app_frame = stripped
            break
    return app_frame or first


def _prop_text(node, key):
    value = node.value(key)
    if value is None:
        return ""
    text = getattr(value, "text", None)
    return text if isinstance(text, str) else ""


def _counts(doc, read_checks):
    rules = 0
    checks = 0
    for node in doc.iter_widgets():
        for key in RULE_KEYS:
            if _prop_text(node, key):
                rules += 1
        raw = _prop_text(node, "cbcsValidate")
        if not raw:
            continue
        checks += len(read_checks(raw).checks)
    return rules, checks


def _id(doc, name):
    found = doc.by_name(name)
    if not found:
        raise RuntimeError("missing %s" % name)
    return found[0]


def _wait_until(predicate, seconds):
    from app.qt.QtCore import QEventLoop, QTimer
    from app.qt.qt_compat import exec_qt

    loop = QEventLoop()
    state = {"done": False}

    def check():
        if predicate():
            state["done"] = True
            loop.quit()
            return
        QTimer.singleShot(20, check)

    QTimer.singleShot(int(seconds * 1000), loop.quit)
    QTimer.singleShot(0, check)
    exec_qt(loop)
    return state["done"]


def _project(root):
    import json as _json

    (root / "forms").mkdir(parents=True)
    (root / "cbcs").mkdir()
    (root / "main.py").write_text("print('shop')\n", encoding="utf-8")
    manifest = root / "cbcs" / "project.json"
    manifest.write_text(
        _json.dumps({"schema_version": 2, "name": "Shop", "default_entry": "main.py"}) + "\n",
        encoding="utf-8",
    )
    return manifest


def _scope_for(path, root):
    from app.features.form_builder.engine.project.forms import FormScope

    stem = path.stem
    return FormScope(
        kind="project",
        ui_path=str(path),
        project_root=str(root),
        generated_path=str(path.parent / ("ui_%s.py" % stem)),
        window_path=str(path.parent / ("%s_window.py" % stem)),
        module_name="forms.ui_%s" % stem,
    )


def _exec(session, command):
    from app.features.form_builder.engine.commands.base import CommandRejected

    try:
        session.log.execute(command)
    except CommandRejected as exc:
        raise RuntimeError("%s: %s" % (type(command).__name__, exc)) from exc


def _write_reference(root):
    from app.features.form_builder.engine.commands.catalog import SetLogic
    from app.features.form_builder.engine.commands.catalog_ext.checks import SetChecks
    from app.features.form_builder.engine.logic.checks import Length, OneOf, Required, read_checks
    from app.features.form_builder.engine.session import FormSession
    from app.features.form_builder.engine.ui4.writer import write_ui

    import reference_form

    built = reference_form.reference_form(300, reference_form.DEFAULT_SEED)
    path = root / "forms" / "order.ui"
    session = FormSession.open(built.xml, path=str(path), scope=_scope_for(path, root))
    try:
        fields = sorted(
            (node for node in session.document.iter_widgets() if (node.object_name or "").startswith("field")),
            key=lambda node: node.object_name or "",
        )
        if len(fields) < 96:
            raise RuntimeError("reference form has %d fields" % len(fields))
        target = fields[0]
        if target.object_name != reference_form.EDIT_NAME:
            raise RuntimeError("edit target is %s" % target.object_name)
        _exec(session, SetLogic(target.id, "cbcsEnabledWhen", "True"))
        _exec(session, SetLogic(target.id, "cbcsVisibleWhen", "True"))
        _exec(session, SetLogic(target.id, "cbcsReadOnlyWhen", "False"))
        _exec(session, SetLogic(target.id, "cbcsValue", '"x"'))
        _exec(session, SetLogic(target.id, "cbcsDefault", '"y"'))
        for node in fields[1:96]:
            _exec(session, SetLogic(node.id, "cbcsEnabledWhen", "True"))
        edits = [node for node in fields if node.class_name == "QLineEdit"]
        if len(edits) < 20:
            raise RuntimeError("reference form has %d line edits" % len(edits))
        bundle = (
            Required("Need a value"),
            Length(1, 32, "Too long"),
            OneOf(("a", "b"), "Pick one"),
        )
        placed = 0
        for node in edits:
            if placed >= 60:
                break
            _exec(session, SetChecks(node.id, bundle))
            placed += 3
        rules, checks = _counts(session.document, read_checks)
        if rules != 100 or checks != 60:
            raise RuntimeError("built %d rules and %d checks" % (rules, checks))
        path.write_text(write_ui(session.document).text, encoding="utf-8")
    finally:
        session.dispose()
    return path


def _write_invoice(root):
    from app.features.form_builder.engine.commands.catalog import SetLogic
    from app.features.form_builder.engine.commands.catalog_ext.checks import AddErrorLabel, SetChecks
    from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
    from app.features.form_builder.engine.logic.checks import Required
    from app.features.form_builder.engine.logic.events_codec import call_step, read_list
    from app.features.form_builder.engine.session import FormSession
    from app.features.form_builder.engine.ui4.writer import write_ui

    source = FIXTURE / "invoice.ui"
    window_src = FIXTURE / "invoice_window.py"
    if not source.is_file() or not window_src.is_file():
        raise RuntimeError("invoice fixture missing at %s" % FIXTURE)
    path = root / "forms" / "invoice.ui"
    text = source.read_text(encoding="utf-8")
    shutil.copyfile(str(window_src), str(root / "forms" / "invoice_window.py"))
    session = FormSession.open(text, path=str(path), scope=_scope_for(path, root))
    try:
        doc = session.document
        _exec(session, SetLogic(_id(doc, "discountEdit"), "cbcsEnabledWhen", "discountCheck"))
        _exec(session, SetLogic(_id(doc, "lineTotalLabel"), "cbcsValue", "qtySpin * priceSpin"))
        _exec(session, SetLogic(_id(doc, "lineTotalLabel"), "cbcsFormat", "money"))
        _exec(session, SetChecks(_id(doc, "emailEdit"), (Required("Email is required"),)))
        _exec(session, AddErrorLabel(_id(doc, "emailEdit")))
        parsed = read_list('[{"do": "validate"}]')
        if parsed.error is not None or not parsed.steps:
            raise RuntimeError("validate step: %s" % (parsed.error,))
        _exec(
            session,
            SetEventSteps(
                "saveButton",
                "clicked",
                (parsed.steps[0], call_step("save_invoice")),
                caption="Save",
            ),
        )
        path.write_text(write_ui(session.document).text, encoding="utf-8")
    finally:
        session.dispose()
    return path


def _row_fail(name, budget, text):
    (RESULTS / ("error_%s.txt" % name)).write_text(text, encoding="utf-8")
    return {
        "pass": False,
        "work_ok": False,
        "error": text,
        "budget_ms": budget,
        "p50_ms": None,
        "p95_ms": None,
        "load": _load(),
        "clock": "cpu",
    }


def _measure(name, fn, budget, clock="cpu", prepare=None):
    print("row %s" % name, flush=True)
    try:
        if clock == "wall":
            row = _time_wall(fn)
        else:
            row = _time(fn, prepare)
    except Exception:
        return _row_fail(name, budget, traceback.format_exc())
    row["budget_ms"] = budget
    row["work_ok"] = True
    row["pass"] = row["p95_ms"] <= budget
    return row


def main():
    if len(FORMULA) != 200:
        _fail("formula length is %d" % len(FORMULA))
    if not PAYLOAD.joinpath("app").is_dir():
        _fail("payload/app is missing. Run build_probe.sh on the build machine first.")
    if not (PAYLOAD / "run_form_preview.py").is_file():
        _fail("payload/run_form_preview.py is missing.")
    sys.path.insert(0, str(HERE))
    sys.path.insert(0, str(PAYLOAD))
    os.environ.setdefault("CBCS_DISABLE_BACKGROUND_RUNTIME", "1")
    os.environ["CBCS_PROBE_RESULTS"] = str(RESULTS)
    RESULTS.mkdir(parents=True, exist_ok=True)
    if WORK.exists():
        shutil.rmtree(WORK)
    try:
        _run()
    except SystemExit:
        raise
    except Exception:
        _fail(traceback.format_exc())


def _run():
    import json as _json

    from app.core.models import LoadedProject, ProjectMetadata
    from app.features.form_builder.engine.commands.catalog import SetLogic
    from app.features.form_builder.engine.logic.formula import SlotKind, analyze, compile_formula
    from app.features.form_builder.engine.logic.formula.types import WHOLE
    from app.features.form_builder.engine.logic.formula_env import env_for
    from app.features.form_builder.engine.logic.rules import rule_graph
    from app.features.form_builder.engine.query.selection import SelectionSource
    from app.features.form_builder.engine.ui4.defaults import QtClassTable
    from app.features.form_builder.qtside.formula.editor import FormulaEditor
    from app.features.form_builder.qtside.inspector.pane import TabId
    from app.qt.QtWidgets import QApplication, QLabel, QMainWindow
    from app.qt.qt_compat import IS_QT6, QT_API
    from app.shell.main_window import MainWindow

    import reference_form

    app = QApplication.instance() or QApplication([])
    root = WORK / "shop"
    manifest = _project(root)
    order_path = _write_reference(root)
    invoice_path = _write_invoice(root)
    window = MainWindow(state_root=str((WORK / "state").resolve()))
    window._loaded_project = LoadedProject(  # type: ignore[attr-defined]
        project_root=str(root.resolve()),
        manifest_path=str(manifest.resolve()),
        metadata=ProjectMetadata(schema_version=2, name="Shop", default_entry="main.py"),
        entries=[],
    )
    notes = _capture_log(window)
    if not window._editor_tab_factory.open_file_in_editor(str(order_path)):  # type: ignore[attr-defined]
        _fail("the reference form did not open\n%s" % "\n".join(notes))
    window._center_stack.setCurrentIndex(1)  # type: ignore[attr-defined]
    window.resize(1400, 900)
    window.show()
    for _ in range(8):
        app.processEvents()
    surface = _bound_surface(window, order_path)
    if surface is None:
        keys = list(window._tab_content_registry._surfaces)  # type: ignore[attr-defined]
        _fail("no form surface for %s\nkeys=%s\n%s" % (order_path, keys, "\n".join(notes)))
    session = surface.session
    doc = session.document
    inspector = surface.workbench.inspector
    canvas = surface.workbench.canvas
    catalog = QtClassTable.shared()
    env = env_for(doc, None, catalog)
    from app.features.form_builder.engine.logic.checks import read_checks

    rules, checks = _counts(doc, read_checks)
    if rules != 100 or checks != 60:
        _fail("open form has %d rules and %d checks" % (rules, checks))
    target = reference_form.EDIT_NAME
    commit_name = "field0001"
    evidence = {
        "rule_count": rules,
        "check_count": checks,
        "python": sys.version.split()[0],
        "qt_api": QT_API,
        "qt6": bool(IS_QT6),
        "platform": os.environ.get("QT_QPA_PLATFORM", ""),
    }
    loadavg_blocked = _load() is None

    def select(name):
        session.selection.set((_id(doc, name),), source=SelectionSource.PROGRAM)
        inspector.flush()

    def paint():
        inspector._pending = True
        visible = inspector.isVisible
        inspector.isVisible = lambda: True
        try:
            inspector.flush()
        finally:
            inspector.isVisible = visible
        canvas.repaint()
        inspector.repaint()
        app.processEvents()

    editor = FormulaEditor()
    label = QLabel()
    editor.set_status_label(label)
    editor.set_context(env, SlotKind.value(WHOLE), type("Reader", (), {})())
    emitted = {"n": 0}

    def analyze_compile():
        found = analyze(FORMULA, env, SlotKind.value(WHOLE))
        made = compile_formula(found, env)
        if not made.source:
            raise RuntimeError("compile returned no source")
        emitted["n"] = len(made.source)

    def prepare_key():
        editor.setPlainText("0")

    def keystroke():
        editor.setPlainText(FORMULA)
        editor.repaint()
        label.repaint()

    def prepare_behavior():
        window._center_stack.setCurrentIndex(1)  # type: ignore[attr-defined]
        inspector.show()
        inspector.focus_tab(TabId.BEHAVIOR)
        select(commit_name)
        app.processEvents()

    def behavior():
        for key in ("events", "state", "checks"):
            section = inspector.behavior.section_widget(key)
            if section is not None and hasattr(section, "_view"):
                section._view = None
        inspector._pending = True
        visible = inspector.isVisible
        inspector.isVisible = lambda: True
        try:
            select(target)
        finally:
            inspector.isVisible = visible

    seq = {"commit": 0, "reload": 0}

    def commit():
        text = "False" if seq["commit"] % 2 == 0 else "True"
        seq["commit"] += 1
        session.log.execute(SetLogic(_id(doc, commit_name), "cbcsEnabledWhen", text))
        rule_graph(doc, env_for(doc, None, catalog))
        paint()

    def save():
        source = surface.content_source()
        if source.prepare_save() is False:
            raise RuntimeError(source.save_notice.text or "save held")
        window._editor_manager.save_tab(str(order_path))  # type: ignore[attr-defined]

    rows = {
        "idle_reference": _time(_idle),
    }
    rows["analyze_compile"] = _measure("analyze_compile", analyze_compile, BUDGETS["analyze_compile"])
    rows["formula_keystroke"] = _measure(
        "formula_keystroke", keystroke, BUDGETS["formula_keystroke"], prepare=prepare_key
    )
    rows["behavior_fill"] = _measure(
        "behavior_fill", behavior, BUDGETS["behavior_fill"], prepare=prepare_behavior
    )
    bare = _measure("bare_repaint", paint, 0.0)
    commit_row = _measure("commit_rule", commit, 0.0)
    rows["bare_repaint"] = bare
    rows["commit_rule"] = commit_row
    if commit_row.get("work_ok") and bare.get("work_ok"):
        added = [
            max(0.0, a - b)
            for a, b in zip(commit_row["samples_ms"][1:], bare["samples_ms"][1:])
        ]
        rows["commit_rule_added"] = {
            "n": len(added),
            "warmup_dropped": 1,
            "clock": "cpu",
            "p50_ms": round(_p(added, 0.50), 3),
            "p95_ms": round(_p(added, 0.95), 3),
            "load": _load(),
            "samples_ms": [round(value, 3) for value in added],
            "budget_ms": BUDGETS["commit_rule_added"],
            "work_ok": True,
            "pass": _p(added, 0.95) <= BUDGETS["commit_rule_added"],
            "derived": "commit_rule minus bare_repaint, paired by run, warm-up dropped",
        }
    else:
        rows["commit_rule_added"] = _row_fail(
            "commit_rule_added",
            BUDGETS["commit_rule_added"],
            commit_row.get("error") or bare.get("error") or "commit pair failed",
        )

    rows["save_generate"] = _measure("save_generate", save, BUDGETS["save_generate"])
    notice = surface.content_source().save_notice
    generated = getattr(session.scope, "generated_path", "") or ""
    generated_bytes = 0
    if generated and os.path.isfile(generated):
        generated_bytes = os.path.getsize(generated)
    evidence["save_notice"] = getattr(notice, "text", "")
    evidence["save_kind"] = getattr(notice, "kind", "")
    evidence["generated_path"] = generated
    evidence["generated_bytes"] = generated_bytes
    evidence["ui_bytes"] = order_path.stat().st_size if order_path.is_file() else 0
    save_row = rows["save_generate"]
    if save_row.get("work_ok") and (evidence["save_kind"] != "generated" or generated_bytes <= 0):
        save_row["work_ok"] = False
        save_row["pass"] = False
        save_row["error"] = "save notice %s bytes %s" % (evidence["save_kind"], generated_bytes)

    refresh_state = {}

    def prepare_refresh():
        if refresh_state.get("ui") is not None:
            return
        if not generated or not os.path.isfile(generated):
            raise RuntimeError("generated module was not written")
        import importlib.util

        spec = importlib.util.spec_from_file_location("ui_order_probe", generated)
        if spec is None or spec.loader is None:
            raise RuntimeError("could not load %s" % generated)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        class_name = ""
        for item in dir(module):
            if item.startswith("Ui_"):
                class_name = item
                break
        if not class_name:
            raise RuntimeError("generated module has no Ui_ class")
        host = QMainWindow()
        ui = getattr(module, class_name)()
        ui.setupUi(host)
        if not hasattr(ui, "cbcs_refresh"):
            raise RuntimeError("%s has no cbcs_refresh" % class_name)
        host.show()
        app.processEvents()
        refresh_state["ui"] = ui
        refresh_state["host"] = host
        refresh_state["class_name"] = class_name
        evidence["refresh_class"] = class_name

    def refresh():
        prepare_refresh()
        refresh_state["ui"].cbcs_refresh()

    try:
        prepare_refresh()
        rows["cbcs_refresh"] = _measure("cbcs_refresh", refresh, BUDGETS["cbcs_refresh"])
    except Exception:
        rows["cbcs_refresh"] = _row_fail("cbcs_refresh", BUDGETS["cbcs_refresh"], traceback.format_exc())

    key_row = rows["formula_keystroke"]
    evidence["formula_status"] = label.text()
    evidence["emitted_chars"] = emitted["n"]
    if key_row.get("work_ok") and "now:" not in label.text():
        key_row["work_ok"] = False
        key_row["pass"] = False
        key_row["error"] = "status %r" % label.text()
    if rows["analyze_compile"].get("work_ok") and emitted["n"] <= 0:
        rows["analyze_compile"]["work_ok"] = False
        rows["analyze_compile"]["pass"] = False
        rows["analyze_compile"]["error"] = "compile returned no source"

    preview = _preview_reload(app, surface, session, doc, commit_name, seq, evidence)
    rows["preview_reload"] = preview
    _profiles(rows, {
        "analyze_compile": (analyze_compile, None),
        "formula_keystroke": (keystroke, prepare_key),
        "behavior_fill": (behavior, prepare_behavior),
        "commit_rule_added": (commit, None),
        "save_generate": (save, None),
        "cbcs_refresh": (refresh, None),
        "preview_reload": (preview.get("rerun"), None),
    })
    try_notes = _try_invoice(app, window, invoice_path, evidence)
    summary = {
        "runs": RUNS,
        "platform": os.environ.get("QT_QPA_PLATFORM", ""),
        "load": _load(),
        "loadavg_blocked": loadavg_blocked,
        "budgets_ms": BUDGETS,
        "evidence": evidence,
        "try": try_notes,
        "rows": {key: value for key, value in rows.items() if key != "preview_reload" or "rerun" not in value},
    }
    if "rerun" in rows["preview_reload"]:
        shown = dict(rows["preview_reload"])
        shown.pop("rerun", None)
        summary["rows"]["preview_reload"] = shown
    (RESULTS / "summary.json").write_text(_json.dumps(_plain(summary), indent=2) + "\n", encoding="utf-8")
    (RESULTS / "summary.txt").write_text(_summary_text(summary), encoding="utf-8")
    (RESULTS / "evidence.txt").write_text(_evidence_text(evidence), encoding="utf-8")
    print(_summary_text(summary), flush=True)
    try:
        from app.features.form_builder.qtside.preview.pool import PreviewPool

        PreviewPool.reset_shared()
    except Exception:
        traceback.print_exc()
    os._exit(0)


def _preview_reload(app, surface, session, doc, commit_name, seq, evidence):
    from app.features.form_builder.engine.commands.catalog import SetLogic
    from app.features.form_builder.qtside.preview.pool import PreviewPool

    print("row preview_reload", flush=True)
    notices = getattr(surface, "own_class_preview", None)
    if notices is None:
        return _row_fail("preview_reload", BUDGETS["preview_reload"], "no preview notices")

    def response_changed(before):
        current = notices.last_response
        return current is not None and current is not before

    before = notices.last_response
    try:
        surface.preview_form()
    except Exception:
        return _row_fail("preview_reload", BUDGETS["preview_reload"], traceback.format_exc())
    if not _wait_until(lambda: response_changed(before), 45):
        pool = PreviewPool.shared()
        evidence["preview_open"] = "timeout"
        evidence["preview_status"] = str(pool.status())
        evidence["preview_stderr"] = "\n".join(pool.stderr_tail())
        return _row_fail("preview_reload", BUDGETS["preview_reload"], "preview did not open\n%s" % evidence["preview_stderr"])
    opened = notices.last_response
    evidence["preview_open"] = "ok" if opened.ok else "fail"
    evidence["preview_open_detail"] = getattr(opened, "detail", "") or ""
    if not opened.ok:
        pool = PreviewPool.shared()
        evidence["preview_stderr"] = "\n".join(pool.stderr_tail())
        return _row_fail(
            "preview_reload",
            BUDGETS["preview_reload"],
            "preview open failed: %s\n%s" % (opened.detail, evidence["preview_stderr"]),
        )

    def reload():
        before_edit = notices.last_response
        text = "False" if seq["reload"] % 2 == 0 else "True"
        seq["reload"] += 1
        session.log.execute(SetLogic(_id(doc, commit_name), "cbcsEnabledWhen", text))
        if not _wait_until(lambda: response_changed(before_edit), 20):
            raise RuntimeError("preview reload timed out")
        current = notices.last_response
        if current is None or not current.ok:
            detail = "" if current is None else (current.detail or current.error)
            raise RuntimeError("preview reload failed: %s" % detail)

    try:
        row = _time_wall(reload)
    except Exception:
        pool = PreviewPool.shared()
        evidence["preview_stderr"] = "\n".join(pool.stderr_tail())
        failed = _row_fail("preview_reload", BUDGETS["preview_reload"], traceback.format_exc())
        failed["rerun"] = reload
        return failed
    row["budget_ms"] = BUDGETS["preview_reload"]
    row["work_ok"] = True
    row["pass"] = row["p95_ms"] <= BUDGETS["preview_reload"]
    row["rerun"] = reload
    pool = PreviewPool.shared()
    evidence["preview_status"] = str(pool.status())
    evidence["preview_stderr"] = "\n".join(pool.stderr_tail())
    last = notices.last_response
    evidence["preview_last_ok"] = bool(last.ok) if last is not None else False
    return row


def _try_invoice(app, window, invoice_path, evidence):
    print("try invoice", flush=True)
    notes = {"path": str(invoice_path)}
    try:
        if not window._editor_tab_factory.open_file_in_editor(str(invoice_path)):  # type: ignore[attr-defined]
            raise RuntimeError("the invoice form did not open")
        for _ in range(8):
            app.processEvents()
        surface = _bound_surface(window, invoice_path)
        if surface is None:
            raise RuntimeError("no invoice surface")
        notices = getattr(surface, "own_class_preview", None)
        before = None if notices is None else notices.last_response
        surface.preview_form()
        if notices is None:
            raise RuntimeError("invoice preview has no notices")

        def opened():
            current = notices.last_response
            return current is not None and current is not before

        if not _wait_until(opened, 45):
            raise RuntimeError("invoice preview did not answer")
        answer = notices.last_response
        notes["preview_ok"] = bool(answer.ok)
        notes["preview_detail"] = getattr(answer, "detail", "") or ""
        if not answer.ok:
            raise RuntimeError("invoice preview failed: %s" % notes["preview_detail"])
        done = RESULTS / "try_walk.done"
        if not _wait_until(lambda: done.is_file(), 30):
            raise RuntimeError("try walk did not finish")
    except Exception:
        text = traceback.format_exc()
        existing = RESULTS / "try_error.txt"
        if not existing.is_file():
            existing.write_text(text, encoding="utf-8")
        notes["error"] = text
        notes["pass"] = False
        _child_log(evidence)
        return notes
    _child_log(evidence)
    ran_path = RESULTS / "what_ran.txt"
    shot = RESULTS / "try_mode.png"
    notes["what_ran_bytes"] = ran_path.stat().st_size if ran_path.is_file() else 0
    notes["screenshot_bytes"] = shot.stat().st_size if shot.is_file() else 0
    notes["pass"] = _try_passed(notes)
    return notes


def _try_passed(notes):
    if (RESULTS / "try_error.txt").is_file():
        return False
    ran = ""
    path = RESULTS / "what_ran.txt"
    if path.is_file():
        ran = path.read_text(encoding="utf-8")
    shot = RESULTS / "try_mode.png"
    if not shot.is_file() or shot.stat().st_size < 32:
        return False
    if "Check all fields" not in ran or "stopped" not in ran:
        return False
    walk = RESULTS / "try_walk.json"
    if not walk.is_file():
        return False
    try:
        data = json.loads(walk.read_text(encoding="utf-8"))
    except ValueError:
        return False
    checks = data.get("checks") or {}
    return all(bool(checks.get(name)) for name in ("discount", "total", "email", "save"))


def _child_log(evidence):
    try:
        from app.features.form_builder.qtside.preview.pool import PreviewPool

        tail = "\n".join(PreviewPool.shared().stderr_tail())
    except Exception:
        tail = traceback.format_exc()
    evidence["child_log"] = tail[-4000:]
    (RESULTS / "child_log.txt").write_text(tail, encoding="utf-8")


def _profiles(rows, fns):
    for name, budget in BUDGETS.items():
        row = rows.get(name) or {}
        if row.get("pass"):
            continue
        pair = fns.get(name)
        if not pair or not callable(pair[0]):
            continue
        fn, prepare = pair
        runs = 1 if name == "preview_reload" else 8
        try:
            frame = _profile(name, fn, prepare, runs=runs)
        except Exception:
            (RESULTS / ("profile_%s.txt" % name)).write_text(traceback.format_exc(), encoding="utf-8")
            frame = ""
        row["top_frame"] = frame


def _plain(value):
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items() if key != "rerun"}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _summary_text(summary):
    lines = [
        "M7.R probe  runs %d  load %s  loadavg_blocked %s"
        % (summary["runs"], summary["load"], summary["loadavg_blocked"]),
        "CPU rows use process_time. preview_reload p50 and p95 are wall clock, because the child is another process.",
        "The first sample of each timed row is warm-up and is left out of p50 and p95.",
    ]
    order = (
        "idle_reference",
        "analyze_compile",
        "formula_keystroke",
        "behavior_fill",
        "commit_rule_added",
        "save_generate",
        "cbcs_refresh",
        "preview_reload",
    )
    rows = summary["rows"]
    for name in order:
        row = rows.get(name) or {}
        budget = BUDGETS.get(name)
        verdict = ""
        if name != "idle_reference":
            verdict = "pass" if row.get("pass") else "fail"
        lines.append(
            "%s  p50 %s ms  p95 %s ms  load %s  budget %s  %s"
            % (
                name,
                row.get("p50_ms"),
                row.get("p95_ms"),
                row.get("load"),
                "" if budget is None else budget,
                verdict,
            )
        )
    try_notes = summary.get("try") or {}
    lines.append("try_pass %s" % try_notes.get("pass"))
    return "\n".join(lines) + "\n"


def _evidence_text(evidence):
    lines = []
    for key in (
        "formula_status",
        "emitted_chars",
        "save_notice",
        "save_kind",
        "generated_bytes",
        "ui_bytes",
        "rule_count",
        "check_count",
        "preview_open",
        "preview_open_detail",
        "preview_status",
        "preview_last_ok",
        "refresh_class",
        "python",
        "qt_api",
        "qt6",
        "platform",
    ):
        lines.append("%s: %s" % (key, evidence.get(key)))
    lines.append("child_log:")
    lines.append(evidence.get("child_log") or "")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
