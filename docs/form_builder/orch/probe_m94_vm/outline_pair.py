"""One outline rename, move, and reparent. CPU of note_edited, plus call counts.

Python 3.9. The app package is whatever sys.path finds first. This file stays
outside that package so both trees run the same script.
"""

from __future__ import annotations

import cProfile
import gc
import io
import os
import pstats
import sys
import time
import types
from pathlib import Path


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


def main() -> int:
    label = sys.argv[1] if len(sys.argv) > 1 else "tree"
    root = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else Path(__file__).resolve().parent
    tests = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else root
    sys.path.insert(0, str(root))
    if str(tests) not in sys.path:
        sys.path.insert(1, str(tests))
    os.chdir(str(tests))
    _stub_pytest()
    import qt_alias

    alias = qt_alias.install()
    os.environ["CBCS_DISABLE_BACKGROUND_RUNTIME"] = "1"
    os.environ["CBCS_FB_VALIDATE"] = "0"

    from app.features.form_builder.engine.commands.catalog import MoveNodes, MovePage, Rename
    from app.features.form_builder.engine.commands.placement import InBoxLayout
    from tests.form_builder.perf.harness import _close_outline, _outline_widgets
    from tests.form_builder.perf.reference import reference_form

    form = reference_form(1000, 1505)
    session, parent, outline, app = _outline_widgets(form.xml)
    lines = ["label %s alias %s" % (label, alias)]
    try:
        outline.attach(session, lambda _key: None)
        owner = session.document.by_name(form.edit_name)[0]
        counter = {"n": 0}

        def rename():
            counter["n"] += 1
            session.log.execute(Rename(owner, "pair%04d" % counter["n"]))
            outline.note_edited()

        def rename_patch():
            counter["n"] += 1
            session.log.execute(Rename(owner, "only%04d" % counter["n"]))
            started = time.process_time()
            outline.note_edited()
            return (time.process_time() - started) * 1000.0

        samples = []
        gc.collect()
        gc.disable()
        try:
            for index in range(9):
                spent = rename_patch()
                if index >= 2:
                    samples.append(spent)
        finally:
            gc.enable()
        samples.sort()
        lines.append(
            "rename_note_edited_cpu_ms %s p50 %.3f"
            % (" ".join("%.2f" % item for item in samples), samples[len(samples) // 2])
        )

        profile = cProfile.Profile()
        counter["n"] += 1
        session.log.execute(Rename(owner, "prof%04d" % counter["n"]))
        profile.enable()
        outline.note_edited()
        profile.disable()
        stream = io.StringIO()
        stats = pstats.Stats(profile, stream=stream)
        stats.sort_stats("cumulative")
        stats.print_stats(20)
        lines.append(stream.getvalue().rstrip())

        tabs = session.document.by_name("tabs")[0]

        def move_patch():
            host = session.document.node(tabs)
            names = [child.object_name for child in host.child_widgets]
            origin = names.index("tabDetails")
            dest = origin + 1 if origin + 1 < len(names) else origin - 1
            session.log.execute(MovePage(tabs, origin, dest))
            started = time.process_time()
            outline.note_edited()
            return (time.process_time() - started) * 1000.0

        moved = []
        gc.collect()
        gc.disable()
        try:
            for index in range(9):
                spent = move_patch()
                if index >= 2:
                    moved.append(spent)
        finally:
            gc.enable()
        moved.sort()
        move_p50 = moved[len(moved) // 2]
        lines.append(
            "move_note_edited_cpu_ms %s p50 %.3f"
            % (" ".join("%.2f" % item for item in moved), move_p50)
        )

        target = session.document.by_name("label0010")[0]
        outer = session.document.by_name("outer")[0]
        turn = {"n": 0}

        def reparent_patch():
            turn["n"] += 1
            if turn["n"] % 2:
                session.log.execute(MoveNodes((target,), InBoxLayout(outer, 0)))
            else:
                session.log.undo()
            started = time.process_time()
            outline.note_edited()
            return (time.process_time() - started) * 1000.0

        reparented = []
        gc.collect()
        gc.disable()
        try:
            for index in range(9):
                spent = reparent_patch()
                if index >= 2:
                    reparented.append(spent)
        finally:
            gc.enable()
        reparented.sort()
        reparent_p50 = reparented[len(reparented) // 2]
        lines.append(
            "reparent_note_edited_cpu_ms %s p50 %.3f"
            % (" ".join("%.2f" % item for item in reparented), reparent_p50)
        )
    finally:
        _close_outline(session, parent, app)
    text = "\n".join(lines) + "\n"
    print(text, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
