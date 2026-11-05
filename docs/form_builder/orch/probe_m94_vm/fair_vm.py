"""Back-to-back regression rows. Python 3.9. No QT_QPA_PLATFORM.

Times outline share, the font-size step, the M6 step-commit command, and M7
commit-added on whichever tree is in payload/. Writes results/fair.txt.
"""

from __future__ import annotations

import os
import sys
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAYLOAD = HERE / "payload" if (HERE / "payload" / "app").is_dir() else HERE
SAMPLES = 7
WARMUP = 2
WANTED = {
    "outline rename share",
    "outline move share",
    "outline undo add share",
    "outline reparent share",
    "m4 font size step",
    "m6 step commit command",
}


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


def _load():
    try:
        return tuple(round(float(value), 2) for value in os.getloadavg())
    except OSError as exc:
        return ("OSError", str(exc))


def main() -> int:
    if str(PAYLOAD) not in sys.path:
        sys.path.insert(0, str(PAYLOAD))
    os.chdir(str(PAYLOAD))
    _stub_pytest()
    import qt_alias

    alias = qt_alias.install()
    os.environ["CBCS_DISABLE_BACKGROUND_RUNTIME"] = "1"
    os.environ["CBCS_FB_VALIDATE"] = "0"
    out = HERE / "results"
    out.mkdir(parents=True, exist_ok=True)
    lines = ["alias %s load %s samples %d warmup %d" % (alias, _load(), SAMPLES, WARMUP)]

    from tests.form_builder.perf.harness import (
        _outline_key_rows,
        _outline_structure_rows,
        _read_load,
        _timed,
        reference_form,
        wall_policy,
    )

    wall_on = wall_policy(_read_load(), _read_load())[0]
    lines.append("wall %s" % wall_on)
    form = reference_form(1000, 1505)
    for row in _outline_key_rows(form, SAMPLES, WARMUP, True, wall_on):
        if row.point in WANTED:
            lines.append("ROW\t%s\t%s\t%s\t%s" % (row.point, row.p50, row.p95, row.budget))
    for row in _outline_structure_rows(form, SAMPLES, WARMUP, True, wall_on):
        if row.point in WANTED:
            lines.append("ROW\t%s\t%s\t%s\t%s" % (row.point, row.p50, row.p95, row.budget))

    from tests.form_builder.perf.m4_editors import inspector_group

    specs, teardown = inspector_group()
    try:
        spec = next(item for item in specs if item.point == "m4 font size step")
        row, _dist = _timed(
            spec.point,
            spec.widgets,
            spec.fn,
            spec.budget_ms,
            samples=SAMPLES,
            warmup=WARMUP,
            enforce_absolute=True,
            wall_on=wall_on,
            prepare=spec.prepare,
            cleanup=spec.cleanup,
        )
        lines.append("ROW\t%s\t%s\t%s\t%s" % (row.point, row.p50, row.p95, row.budget))
    finally:
        teardown()

    from tests.form_builder.perf.m6_paths import ui_group

    specs, teardown = ui_group()
    try:
        spec = next(item for item in specs if item.point == "m6 step commit command")
        row, _dist = _timed(
            spec.point,
            spec.widgets,
            spec.fn,
            spec.budget_ms,
            samples=SAMPLES,
            warmup=WARMUP,
            enforce_absolute=True,
            wall_on=wall_on,
            prepare=getattr(spec, "prepare", None),
            cleanup=getattr(spec, "cleanup", None),
        )
        lines.append("ROW\t%s\t%s\t%s\t%s" % (row.point, row.p50, row.p95, row.budget))
    finally:
        teardown()

    import tests.form_builder.perf.m7_paths as m7

    m7.RESULTS = out / "m7"
    print("M7_BEGIN", flush=True)
    code = m7.main([])
    summary = m7.RESULTS / "summary.json"
    if summary.is_file():
        import json

        body = json.loads(summary.read_text(encoding="utf-8"))
        added = (body.get("rows") or {}).get("commit_added") or {}
        lines.append(
            "ROW\tcommit_added\t%s\t%s\t17" % (added.get("p50_ms"), added.get("p95_ms"))
        )
        preview = (body.get("rows") or {}).get("preview_reload") or {}
        lines.append(
            "ROW\tpreview_reload\t%s\t%s\t500" % (preview.get("p50_ms"), preview.get("p95_ms"))
        )
    lines.append("m7_exit %s load %s" % (code, _load()))
    text = "\n".join(lines) + "\n"
    (out / "fair.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        raise
