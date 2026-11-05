"""M9.4 speed rows on the ChoreBoy VM.

Python 3.9. No pytest. Do not set QT_QPA_PLATFORM. The guest has a display.
AppArmor makes os.getloadavg() raise; the harness and this file both catch that.

Pass a scratch directory as the first argument. This probe deletes that
directory before writing. With no argument, results land in ./results.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAYLOAD = HERE / "payload" if (HERE / "payload" / "app").is_dir() else HERE


def _loadavg():
    try:
        return [round(value, 2) for value in os.getloadavg()], ""
    except OSError as exc:
        return None, "%s: %s" % (type(exc).__name__, exc)


def _output_dir():
    if len(sys.argv) > 1:
        path = Path(sys.argv[1]).resolve()
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)
        return path
    path = HERE / "results"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write(directory, name, payload):
    directory.mkdir(parents=True, exist_ok=True)
    text = payload if isinstance(payload, str) else json.dumps(payload, indent=2, default=str)
    path = directory / name
    tmp = path.with_suffix(path.suffix + ".partial")
    tmp.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    os.replace(str(tmp), str(path))


def _stub_pytest():
    if "pytest" in sys.modules:
        return
    module = types.ModuleType("pytest")

    def importorskip(name, exc_type=ImportError):
        __import__(name)
        return sys.modules[name]

    def _marker(*args, **_kwargs):
        if len(args) == 1 and callable(args[0]) and not _kwargs:
            return args[0]

        def decorator(fn):
            return fn

        return decorator

    module.importorskip = importorskip

    class _Marks(object):
        def __getattr__(self, _name):
            return _marker

    module.mark = _Marks()
    module.fixture = _marker
    sys.modules["pytest"] = module


def _runtime():
    facts = {"executable": sys.executable, "python": sys.version.split()[0]}
    try:
        import FreeCAD

        facts["freecad"] = getattr(FreeCAD, "Version", lambda: ())()
    except ImportError as exc:
        facts["freecad_error"] = str(exc)
    return facts


def main():
    if str(PAYLOAD) not in sys.path:
        sys.path.insert(0, str(PAYLOAD))
    os.chdir(str(PAYLOAD))
    out = _output_dir()
    _stub_pytest()
    import qt_alias

    alias = qt_alias.install()
    # FreeCAD 1.0 leaves the builder off. The speed rows open a real form
    # tab, so the probe turns the feature on for whichever binding loaded.
    import app.features.form_builder.install as fb_install

    if not fb_install.form_builder_enabled():
        fb_install.form_builder_enabled = lambda: True
    load, load_error = _loadavg()
    facts = {
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "loadavg": load,
        "loadavg_error": load_error,
        "alias": alias,
        "runtime": _runtime(),
        "output": str(out),
    }
    try:
        from tests.form_builder.perf.harness import format_table, report_json, run_speed

        # profile "mac" turns on the millisecond budgets. This process is the VM.
        report = run_speed(profile="mac", samples=7, warmup=2, sizes=(300, 1000))
        body = report_json(report)
        body["machine"] = "ChoreBoyExp"
        body["budget_profile"] = "mac means the millisecond budgets are enforced"
        _write(out, "summary.json", body)
        text = format_table(report)
        _write(out, "summary.txt", text)
        print(text, flush=True)
        facts["speed_ok"] = bool(report.ok)
        facts["rows"] = len(report.rows)
    except Exception:
        facts["speed_error"] = traceback.format_exc()
        _write(out, "facts.json", facts)
        print(facts["speed_error"], file=sys.stderr)
        return 1
    try:
        from tests.form_builder.perf import m7_paths

        m7_paths.RESULTS = out / "m7"
        facts["m7_exit"] = m7_paths.main([])
    except Exception:
        facts["m7_error"] = traceback.format_exc()
        print(facts["m7_error"], file=sys.stderr)
    _write(out, "facts.json", facts)
    return 0 if facts.get("speed_ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
