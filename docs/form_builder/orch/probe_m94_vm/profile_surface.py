"""cProfile one caption edit, one spacing edit and one paste on the VM.

Python 3.9. No pytest. Do not set QT_QPA_PLATFORM. Writes results/profile.txt.
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


def _dump(profile, label, lines):
    stream = io.StringIO()
    stats = pstats.Stats(profile, stream=stream)
    stats.sort_stats("cumulative")
    stats.print_stats(25)
    lines.append("== %s ==" % label)
    lines.append(stream.getvalue())


def main():
    if str(PAYLOAD) not in sys.path:
        sys.path.insert(0, str(PAYLOAD))
    os.chdir(str(PAYLOAD))
    _stub_pytest()
    import qt_alias

    qt_alias.install()
    os.environ["CBCS_DISABLE_BACKGROUND_RUNTIME"] = "1"
    os.environ["CBCS_FB_VALIDATE"] = "0"

    from app.features.form_builder.engine.commands.catalog import SetProperty
    from app.features.form_builder.engine.ui4.values import NumberValue, StringValue
    from app.qt.QtWidgets import QApplication
    from tests.form_builder.perf.reference import reference_form

    form = reference_form(1000, 1505)
    app = QApplication.instance() or QApplication([])
    import importlib
    import tempfile

    main_window = importlib.import_module("app.shell.main_window")
    selection = importlib.import_module("app.features.form_builder.engine.query.selection")
    shutdown_mod = importlib.import_module("testing.main_window_shutdown")
    lines = []
    scratch = tempfile.TemporaryDirectory(prefix="cbcs-m94-profile-")
    root = Path(scratch.name)
    path = root / "speed_form.ui"
    path.write_text(form.xml, encoding="utf-8")
    window = main_window.MainWindow(state_root=str(root / "state"))
    window._editor_tab_factory.open_file_in_editor(str(path))
    window._center_stack.setCurrentIndex(1)
    window.resize(1400, 900)
    window.show()
    app.processEvents()
    surface = window._tab_content_registry.surface_for_path(str(path))
    session = surface._session
    pane = surface._workbench.inspector
    label = session.document.by_name("label0000")
    layout = session.document.by_name("identityForm")
    owner = layout[0] if layout else label[0]
    label_id = label[0]

    step = {"n": 0}

    def edit():
        step["n"] += 1
        outcome = session.log.execute(SetProperty(label_id, "text", StringValue("profile %d" % step["n"])))
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

    def paste():
        session.selection.set((label_id,), source=selection.SelectionSource.CANVAS)
        app.processEvents()
        surface.dispatch("form.action.copy")
        app.processEvents()
        surface.dispatch("form.action.paste")
        app.processEvents()
        pane.flush()

    for fn in (edit, space, paste):
        fn()
        app.processEvents()
    session.log.undo()
    app.processEvents()

    for name, fn in (("edit", edit), ("spacing", space), ("paste", paste)):
        started = time.process_time()
        profile = cProfile.Profile()
        profile.enable()
        fn()
        profile.disable()
        elapsed = (time.process_time() - started) * 1000.0
        lines.append("%s cpu %.2f ms" % (name, elapsed))
        _dump(profile, name, lines)
        if name == "paste":
            session.log.undo()
            app.processEvents()

    out = HERE / "results"
    out.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines)
    (out / "profile.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    shutdown_mod.shutdown_main_window_for_test(window, app)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
