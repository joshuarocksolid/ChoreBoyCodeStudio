"""Time each Qt event inside one official edit, spacing edit, and paste.

Python 3.9. No pytest. Do not set QT_QPA_PLATFORM. The notify override is
this probe only. Writes results/events.txt.
"""

from __future__ import annotations

import cProfile
import io
import os
import pstats
import sys
import time
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAYLOAD = HERE / "payload" if (HERE / "payload" / "app").is_dir() else HERE


def _stub_pytest():
    if "pytest" in sys.modules:
        return
    module = types.ModuleType("pytest")

    def importorskip(name, exc_type=ImportError):
        __import__(name)
        return sys.modules[name]

    def _marker(*args, **kwargs):
        if len(args) == 1 and callable(args[0]) and not kwargs:
            return args[0]

        def decorator(fn):
            return fn

        return decorator

    class _Marks(object):
        def __getattr__(self, _name):
            return _marker

    module.importorskip = importorskip
    module.mark = _Marks()
    module.fixture = _marker
    sys.modules["pytest"] = module


def _event_name(event):
    kind = event.type()
    name = getattr(kind, "name", None)
    if name:
        return str(name)
    try:
        return str(int(kind))
    except (TypeError, ValueError):
        return str(kind)


def _receiver(receiver):
    cls = type(receiver).__name__
    getter = getattr(receiver, "objectName", None)
    oname = ""
    if callable(getter):
        try:
            oname = getter() or ""
        except RuntimeError:
            oname = ""
    return cls, oname or "-"


class _Gap(object):
    """Times the gap from one delivered event to the next. That gap is the handler."""

    def __init__(self):
        from app.qt.QtCore import QObject

        probe = self

        class Filter(QObject):
            def eventFilter(self, watched, event):  # noqa: N802
                if not probe.recording:
                    return False
                now = time.perf_counter()
                if probe.pending is not None:
                    key, started = probe.pending
                    probe._add(key, now - started)
                probe.pending = ((_event_name(event),) + _receiver(watched), now)
                return False

        self.filter = Filter()
        self.recording = False
        self.pending = None
        self.buckets = {}
        self.how = ""

    def _add(self, key, spent):
        slot = self.buckets.get(key)
        if slot is None:
            self.buckets[key] = [1, spent]
        else:
            slot[0] += 1
            slot[1] += spent

    def flush(self):
        if self.pending is None:
            return
        key, started = self.pending
        self._add(key, time.perf_counter() - started)
        self.pending = None


_WATCH = None


def _install_watch():
    global _WATCH
    from app.qt.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    _WATCH = _Gap()
    _WATCH.app = app
    _WATCH.how = "filter on %s" % type(app).__name__
    return app


def _begin():
    from app.qt.QtWidgets import QApplication

    QApplication.instance().installEventFilter(_WATCH.filter)
    _WATCH.buckets = {}
    _WATCH.pending = None
    _WATCH.recording = True


def _end():
    _WATCH.recording = False
    _WATCH.flush()
    from app.qt.QtWidgets import QApplication

    QApplication.instance().removeEventFilter(_WATCH.filter)


def _report(lines, label):
    rows = sorted(_WATCH.buckets.items(), key=lambda item: item[1][1], reverse=True)
    total_n = sum(slot[0] for _key, slot in rows)
    total_ms = sum(slot[1] for _key, slot in rows) * 1000.0
    lines.append("%s events %d handler-gap %.1f ms" % (label, total_n, total_ms))
    lines.append("type\tclass\tobject\tcount\tms")
    for key, slot in rows[:15]:
        lines.append("%s\t%s\t%s\t%d\t%.2f" % (key[0], key[1], key[2], slot[0], slot[1] * 1000.0))
    lines.append("named %s" % label)
    for key, slot in rows:
        kind = str(key[0])
        if "LayoutRequest" in kind or "ActionChanged" in kind or "ToolTipChange" in kind:
            lines.append(
                "named\t%s\t%s\t%s\t%d\t%.2f" % (key[0], key[1], key[2], slot[0], slot[1] * 1000.0)
            )
    _WATCH.buckets = {}


def _profile(fn, label, lines):
    profile = cProfile.Profile()
    profile.enable()
    fn()
    profile.disable()
    stream = io.StringIO()
    stats = pstats.Stats(profile, stream=stream)
    stats.sort_stats("cumulative")
    stats.print_stats(20)
    lines.append("== cProfile %s ==" % label)
    lines.append(stream.getvalue())


def _drain(app, lines, label):
    """Finish deletes and timers from the window that just closed.

    A later, smaller form was slower when this drain was missing. Its samples
    included the big window coming down.
    """
    import gc

    from app.qt.QtWidgets import QApplication

    for _turn in range(40):
        app.processEvents()
    gc.collect()
    app.processEvents()
    alive = [
        widget
        for widget in QApplication.topLevelWidgets()
        if type(widget).__name__ == "MainWindow"
    ]
    lines.append("%s mains_alive %d" % (label, len(alive)))
    return len(alive)


def _open(main_window, count, lines):
    import tempfile

    from tests.form_builder.perf.reference import reference_form

    form = reference_form(count, 1505)
    scratch = tempfile.TemporaryDirectory(prefix="cbcs-m94-events-")
    root = Path(scratch.name)
    path = root / "speed_form.ui"
    path.write_text(form.xml, encoding="utf-8")
    window = main_window.MainWindow(state_root=str(root / "state"))
    opened_ok = window._editor_tab_factory.open_file_in_editor(str(path))
    window._center_stack.setCurrentIndex(1)
    window.resize(1400, 900)
    window.show()
    app = _WATCH.app
    surface = None
    for _turn in range(40):
        app.processEvents()
        for candidate in (str(path), str(path.resolve())):
            found = window._tab_content_registry.surface_for_path(candidate)
            if found is not None and getattr(found, "_session", None) is not None:
                surface = found
                break
        if surface is not None:
            break
    if surface is None:
        keys = tuple(getattr(window._tab_content_registry, "_surfaces", ()))
        raise RuntimeError(
            "no form surface opened=%s path=%s keys=%s" % (opened_ok, path, keys)
        )
    session = surface._session
    pane = surface._workbench.inspector
    label = session.document.by_name("label0000")[0]
    layout = session.document.by_name("identityForm")
    owner = layout[0] if layout else label
    from app.qt.QtWidgets import QApplication

    mains = sum(1 for widget in QApplication.topLevelWidgets() if type(widget).__name__ == "MainWindow")
    lines.append("opened %d widgets label %s layout %s mains %d" % (count, label, owner, mains))
    return scratch, window, surface, session, pane, label, owner


def _time_rows(surface, session, pane, label, owner, lines, tag):
    from app.features.form_builder.engine.commands.catalog import SetProperty
    from app.features.form_builder.engine.ui4.values import NumberValue, StringValue
    from tests.form_builder.perf.stats import measure

    app = _WATCH.app
    step = {"n": 0}

    def edit():
        step["n"] += 1
        outcome = session.log.execute(SetProperty(label, "text", StringValue("probe %d" % (step["n"] + 1000))))
        if outcome.noop:
            raise RuntimeError("text edit was a no-op")
        app.processEvents()
        pane.flush()

    def space():
        step["n"] += 1
        outcome = session.log.execute(SetProperty(owner, "spacing", NumberValue(20 + (step["n"] % 5))))
        if outcome.noop:
            raise RuntimeError("spacing edit was a no-op")
        app.processEvents()
        pane.flush()

    from app.features.form_builder.engine.query import selection as selection_mod

    session.selection.set((label,), source=selection_mod.SelectionSource.CANVAS)
    app.processEvents()
    surface.dispatch("form.action.copy")
    app.processEvents()

    def paste():
        surface.dispatch("form.action.paste")
        app.processEvents()
        pane.flush()

    def undo():
        session.log.undo()
        app.processEvents()

    for name, fn, cleanup in (("edit", edit, None), ("spacing", space, None), ("paste", paste, undo)):
        dist = measure(fn, warmup=2, samples=7, cleanup=cleanup)
        lines.append(
            "%s %s cpu p50 %.3f p95 %.3f n %d"
            % (tag, name, dist.cpu_p50 * 1000.0, dist.cpu_p95 * 1000.0, dist.n)
        )


def main():
    if str(PAYLOAD) not in sys.path:
        sys.path.insert(0, str(PAYLOAD))
    os.chdir(str(PAYLOAD))
    _stub_pytest()
    import qt_alias

    alias = qt_alias.install()
    os.environ["CBCS_DISABLE_BACKGROUND_RUNTIME"] = "1"
    os.environ["CBCS_FB_VALIDATE"] = "0"
    # FreeCAD 1.0 keeps the builder off. The probe still builds the form on
    # the binding this process already chose. Forcing PySide6 here imports
    # shiboken6, which that image does not ship.
    import app.features.form_builder.install as fb_install

    forced = False
    if not fb_install.form_builder_enabled():
        fb_install.form_builder_enabled = lambda: True
        forced = True
    _install_watch()
    lines = ["alias %s watch %s builder_forced %s" % (alias, _WATCH.how, forced)]

    from app.features.form_builder.engine.commands.catalog import SetProperty
    from app.features.form_builder.engine.query import selection as selection_mod
    from app.features.form_builder.engine.ui4.values import NumberValue, StringValue
    import importlib

    main_window = importlib.import_module("app.shell.main_window")
    shutdown_mod = importlib.import_module("testing.main_window_shutdown")
    # The small form goes first, then a drain, so its clock is not the big
    # window being destroyed. The event trace stays on the 1000-widget form.
    scratch60, window60, surface60, session60, pane60, label60, owner60 = _open(main_window, 60, lines)
    app = _WATCH.app
    _time_rows(surface60, session60, pane60, label60, owner60, lines, "widgets60")
    shutdown_mod.shutdown_main_window_for_test(window60, app)
    scratch60.cleanup()
    _drain(app, lines, "after60")

    scratch, window, surface, session, pane, label, owner = _open(main_window, 1000, lines)
    app = _WATCH.app
    step = {"n": 0}

    def edit():
        step["n"] += 1
        outcome = session.log.execute(SetProperty(label, "text", StringValue("surface %d" % step["n"])))
        if outcome.noop:
            raise RuntimeError("text edit was a no-op")
        app.processEvents()
        pane.flush()

    def space():
        step["n"] += 1
        outcome = session.log.execute(SetProperty(owner, "spacing", NumberValue(6 + (step["n"] % 5))))
        if outcome.noop:
            raise RuntimeError("spacing edit was a no-op")
        app.processEvents()
        pane.flush()

    session.selection.set((label,), source=selection_mod.SelectionSource.CANVAS)
    app.processEvents()
    surface.dispatch("form.action.copy")
    app.processEvents()

    def paste():
        surface.dispatch("form.action.paste")
        app.processEvents()
        pane.flush()

    edit()
    space()
    paste()
    session.log.undo()
    app.processEvents()

    _time_rows(surface, session, pane, label, owner, lines, "widgets1000")

    def record(fn, label):
        _begin()
        fn()
        _end()
        _report(lines, label)

    record(edit, "edit-sample")
    record(space, "spacing-sample")
    record(paste, "paste-sample")
    session.log.undo()
    app.processEvents()

    def paste_only():
        surface.dispatch("form.action.paste")

    _profile(paste_only, "paste-dispatch", lines)
    session.log.undo()
    app.processEvents()

    shutdown_mod.shutdown_main_window_for_test(window, app)
    scratch.cleanup()
    _drain(app, lines, "after1000")

    out = HERE / "results"
    out.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines) + "\n"
    (out / "events.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
