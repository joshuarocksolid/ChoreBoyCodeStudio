#!/usr/bin/env python3
"""Run the form-builder quality gates and print a pass/fail table.

Gates that need app/features/form_builder report "skipped: no package" until
that package exists. A skip does not fail the process. A failed gate does.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
FEATURE_DIR = REPO_ROOT / "app" / "features" / "form_builder"
TESTS_DIR = REPO_ROOT / "tests" / "form_builder"
PY311_DEFAULT = "/Applications/FreeCAD.app/Contents/Resources/bin/python"
PY39_DEFAULT = "~/opt/freecad/AppRun"

# ``--quick`` drops the two gates whose startup dominates a local edit loop.
QUICK_SKIP = frozenset({"unit-py39-pyside6", "pyright"})
# The repo fast shard is minutes, so the default table lists it and does not run it.
FULL_ONLY = frozenset({"fast-shard-regression"})
# n=15 across 300, 600 and 1000 widgets. The default table lists it and does not run it.
OPT_IN = frozenset({"speed"})
PERF_GATE_TIMEOUT_SECONDS = 30

UNIT_MARKER = "not oracle and not perf and not performance and not soak"
# Form-builder tests that live with the shell and feature unit suites. The
# fast shard needs /opt/freecad/AppRun, so these would otherwise never run here.
TEST_PATHS = (
    "tests/form_builder",
    "tests/unit/features/form_builder",
    "tests/unit/shell/test_form_package_dialog.py",
    "tests/unit/shell/test_form_run_routing.py",
    "tests/unit/shell/test_form_status_sentence.py",
    "tests/unit/shell/test_form_tab_shell_keys.py",
    "tests/unit/tools/test_form_builder_parity.py",
)
# The unit lane takes about 940 s when the machine load is near 40.
PYTEST_TIMEOUT_SECONDS = 1500
FAST_SHARD_TIMEOUT_SECONDS = 400
COMMAND_TIMEOUT_SECONDS = 180

_COUNT_RE = re.compile(
    r"(\d+)\s+(passed|failed|skipped|errors|error|deselected|xfailed|xpassed)"
)


@dataclass(frozen=True)
class GateResult:
    name: str
    status: str
    seconds: float
    detail: str
    log: str = ""


@dataclass(frozen=True)
class CommandResult:
    code: int
    seconds: float
    stdout: str
    stderr: str
    timed_out: bool = False


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    unknown = [name for name in (args.only or []) if name not in _GATE_RUNNERS]
    if unknown:
        known = ", ".join(_GATE_RUNNERS)
        print(
            "unknown gate %s; known gates: %s" % (", ".join(unknown), known),
            file=sys.stderr,
        )
        return 2

    plan = _plan(run_quick=args.quick, run_full=args.full, only=args.only)
    results: list[GateResult] = []
    for name, skip_reason in plan:
        if skip_reason is not None:
            results.append(GateResult(name, "skip", 0.0, skip_reason))
            continue
        print("running %s" % name, file=sys.stderr, flush=True)
        started = time.monotonic()
        try:
            result = _GATE_RUNNERS[name]()
        except Exception as exc:  # noqa: BLE001 — one gate must not hide the rest of the table
            result = GateResult(name, "fail", time.monotonic() - started, "runner error: %s" % exc)
        results.append(result)

    print(_format_table(results))
    _print_failure_logs(results)
    if args.json:
        _write_json(Path(args.json), results)
    failed = [item.name for item in results if item.status == "fail"]
    if failed:
        print("form-builder checks: FAIL (%s)" % ", ".join(failed))
        return 1
    print("form-builder checks: PASS")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Skip unit-py39-pyside6 and pyright. Does nothing when --only is set.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Also run fast-shard-regression. Does nothing when --only is set.",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        metavar="GATE",
        help="Run these gates only. Names: %s." % ", ".join(_gate_names()),
    )
    parser.add_argument(
        "--json",
        metavar="PATH",
        help="Write the same rows as JSON for another program.",
    )
    return parser


def _gate_names() -> tuple[str, ...]:
    return tuple(_GATE_RUNNERS)


def _plan(
    *,
    run_quick: bool,
    run_full: bool,
    only: list[str] | None,
) -> list[tuple[str, str | None]]:
    if only:
        return [(name, None) for name in only]
    rows: list[tuple[str, str | None]] = []
    for name in _GATE_RUNNERS:
        if name in OPT_IN:
            rows.append((name, "skipped: opt-in --only speed"))
            continue
        if name in FULL_ONLY and not run_full:
            rows.append((name, "skipped: opt-in --full"))
            continue
        if run_quick and name in QUICK_SKIP:
            rows.append((name, "skipped: --quick"))
            continue
        rows.append((name, None))
    return rows


def _format_table(results: Sequence[GateResult]) -> str:
    rows = [
        (item.name, item.status, "%.2f" % item.seconds, " ".join(item.detail.split()))
        for item in results
    ]
    header = ("gate", "status", "seconds", "detail")
    widths = [
        max([len(header[index])] + [len(row[index]) for row in rows])
        for index in range(3)
    ]

    def line(cols: tuple[str, str, str, str]) -> str:
        padded = [cols[index].ljust(widths[index]) for index in range(3)]
        return "  ".join(padded + [cols[3]])

    rule = "  ".join("-" * width for width in widths)
    body = [line(header), rule, *(line(row) for row in rows)]
    return "\n".join(body)


def _print_failure_logs(results: Sequence[GateResult]) -> None:
    for item in results:
        if item.status != "fail" or not item.log.strip():
            continue
        print()
        print("--- %s ---" % item.name)
        print(item.log.rstrip())


def _write_json(path: Path, results: Sequence[GateResult]) -> None:
    payload = {
        "ok": not any(item.status == "fail" for item in results),
        "gates": [
            {
                "gate": item.name,
                "status": item.status,
                "seconds": round(item.seconds, 2),
                "detail": " ".join(item.detail.split()),
                **(
                    {"log_tail": _tail(item.log, limit=80)}
                    if item.status == "fail" and item.log.strip()
                    else {}
                ),
            }
            for item in results
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


# Cloud images export the short names. Local runs use the longer ones.
_RUNTIME_ALIASES = {
    "CBCS_FORM_BUILDER_PY311": ("CBCS_FB_PY311",),
    "CBCS_FORM_BUILDER_PY39": ("CBCS_FB_PY39",),
}


def _runtime(env_name: str, default: str) -> Path:
    names = (env_name,) + _RUNTIME_ALIASES.get(env_name, ())
    for name in names:
        raw = os.environ.get(name, "").strip()
        if raw:
            return Path(raw).expanduser()
    return Path(default).expanduser()


def _is_runtime(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def _package_ready() -> bool:
    return FEATURE_DIR.is_dir() and any(FEATURE_DIR.rglob("*.py"))


def _skip(name: str, detail: str, seconds: float = 0.0) -> GateResult:
    return GateResult(name, "skip", seconds, detail)


def _fail(name: str, seconds: float, detail: str, log: str = "") -> GateResult:
    return GateResult(name, "fail", seconds, detail, log)


def _pass(name: str, seconds: float, detail: str) -> GateResult:
    return GateResult(name, "pass", seconds, detail)


def _vendor_candidates(dirname: str) -> list[Path]:
    candidates: list[Path] = []
    configured = os.environ.get("CBCS_ARTIFACTS_DIR", "").strip()
    if configured:
        candidates.append(Path(configured).expanduser() / dirname)
    link = REPO_ROOT / "vendor"
    if link.is_symlink():
        target = Path(os.readlink(link))
        if not target.is_absolute():
            target = link.parent / target
        candidates.append(target.parent / dirname)
    elif link.is_dir() and dirname == "vendor":
        candidates.append(link)
    artifacts_name = "ChoreBoyCodeStudio_artifacts"
    candidates.append(REPO_ROOT.parent / artifacts_name / dirname)
    candidates.append(REPO_ROOT.parent.parent / artifacts_name / dirname)
    return candidates


def _has_pytest(path: Path) -> bool:
    return (path / "pytest" / "__init__.py").is_file()


def _pytest_vendor(profile: str) -> Path | None:
    # pytest is pure Python, so a py39 tree can serve the py311 interpreter
    # when the matching native tree is not on this machine.
    order = ["vendor_" + profile]
    for fallback in ("vendor_py311", "vendor_py39", "vendor"):
        if fallback not in order:
            order.append(fallback)
    seen: set[Path] = set()
    for dirname in order:
        for candidate in _vendor_candidates(dirname):
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            if _has_pytest(candidate):
                return candidate
    return None


def _qt_tool(name: str) -> Path | None:
    """uic or rcc next to the FreeCAD Qt install.

    Darwin keeps the tools under the app bundle. Linux FreeCAD 1.1 keeps them
    under qt6, sometimes in bin or libexec.
    """
    candidates = [
        Path("/Applications/FreeCAD.app/Contents/Resources/lib/qt6") / name,
    ]
    root = Path("/opt/freecad-1.1/usr/lib/qt6")
    for relative in (name, os.path.join("bin", name), os.path.join("libexec", name)):
        candidates.append(root / relative)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _resolved_qt_tool(name: str) -> Path | None:
    raw = os.environ.get("CBCS_FB_" + name.upper(), "").strip()
    if raw:
        path = Path(raw).expanduser()
        return path if path.is_file() else None
    return _qt_tool(name)


def _child_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    env.pop("VIRTUAL_ENV_PROMPT", None)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["CBCS_DISABLE_BACKGROUND_RUNTIME"] = "1"
    env["CBCS_SYNC_PROJECT_OPEN"] = "1"
    env["CBCS_QT_API"] = "pyside6"
    for tool in ("uic", "rcc"):
        found = _qt_tool(tool)
        if found is not None:
            env.setdefault("CBCS_FB_" + tool.upper(), str(found))
    env["CBCS_FB_REQUIRE_ORACLE"] = "1"
    if not env.get("CBCS_UIC") and env.get("CBCS_FB_UIC"):
        env["CBCS_UIC"] = env["CBCS_FB_UIC"]
    # Captured children block-buffer stdout. os._exit would drop pytest's summary.
    env["PYTHONUNBUFFERED"] = "1"
    if extra:
        env.update(extra)
    return env


def _run_command(
    command: Sequence[str],
    *,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
) -> CommandResult:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            list(command),
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", "replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
        return CommandResult(
            code=124,
            seconds=time.monotonic() - started,
            stdout=stdout,
            stderr=stderr,
            timed_out=True,
        )
    return CommandResult(
        code=completed.returncode,
        seconds=time.monotonic() - started,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _tail(text: str, limit: int = 40) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) <= limit:
        return "\n".join(lines)
    return "\n".join(lines[-limit:])


def _command_log(result: CommandResult) -> str:
    parts: list[str] = []
    if result.stdout.strip():
        parts.append(_tail(result.stdout))
    if result.stderr.strip():
        parts.append(_tail(result.stderr))
    return "\n".join(parts)


def _pytest_counts(text: str) -> tuple[str, dict[str, int]]:
    last = ""
    counts: dict[str, int] = {}
    for line in text.splitlines():
        found = _COUNT_RE.findall(line)
        if not found:
            continue
        if " in " not in line and "no tests ran" not in line:
            continue
        last = " ".join(line.split())
        counts = {}
        for raw_count, raw_name in found:
            name = "error" if raw_name in {"error", "errors"} else raw_name
            counts[name] = counts.get(name, 0) + int(raw_count)
    return last, counts


def _pytest_payload(vendor: Path, marker: str, *, vendor_first: bool, pin_vendor: bool = False) -> str:
    # os._exit skips the Shiboken destructor, which segfaults if Python
    # wrappers outlive Qt. Flush first so a captured pipe keeps the summary.
    args = ["-q", "--tb=line", *TEST_PATHS, "-m", marker]
    if vendor_first:
        path_setup = "sys.path.insert(0, {repo!r});sys.path.insert(0, {vendor!r});"
    else:
        # A mismatched vendor tree stays behind the interpreter's site-packages
        # so a py39 extension does not shadow PySide6.
        path_setup = "sys.path.insert(0, {repo!r});sys.path.append({vendor!r});"
    # The repo vendor symlink follows the last AppRun. A PySide6 run points it
    # at vendor_py311, whose jedi uses ``str | None`` and cannot import on 3.9.
    # Pin the selected tree before pytest imports the intelligence stack.
    pin = ""
    if pin_vendor:
        pin = (
            "from pathlib import Path as _PinPath\n"
            "import app.bootstrap.vendor_paths as _vp\n"
            "def _pin_vendor(app_root=None):\n"
            " t={vendor!r}\n"
            " if t not in sys.path:\n"
            "  sys.path.insert(0, t)\n"
            " return _PinPath(t)\n"
            "_vp.ensure_vendor_path_on_sys_path=_pin_vendor\n"
        )
    # FreeCAD 1.0 installs a meta-path finder without find_spec. Pytest's
    # importlib mode calls find_spec directly, so give those finders the
    # legacy find_module wrapper before collection starts.
    payload = (
        "import importlib.util as _iu, os, sys\n"
        "def _legacy_find_spec(finder, name, path=None, target=None):\n"
        " loader=finder.find_module(name, path)\n"
        " return None if loader is None else _iu.spec_from_loader(name, loader)\n"
        "for _finder in list(sys.meta_path):\n"
        " if not hasattr(_finder, 'find_spec'):\n"
        "  _finder.find_spec=_legacy_find_spec.__get__(_finder)\n"
        + path_setup
        + pin
        + "os.chdir({repo!r})\n"
        "code=int(__import__('pytest').main({args!r}))\n"
        "sys.stdout.flush();sys.stderr.flush()\n"
        "os._exit(code)\n"
    ).format(repo=str(REPO_ROOT), vendor=str(vendor), args=args)
    return _apprun_safe(payload)


def _longest_slash_free(code: str) -> int:
    return max(len(part.encode("utf-8")) for part in code.split("/"))


def _apprun_safe(code: str) -> str:
    """Keep each slash-free run in an AppRun ``-c`` payload under 200 bytes.

    FreeCAD 1.1 calls ``filesystem::status`` on the argument. A run longer
    than NAME_MAX aborts with "File name too long". A quoted slash is a
    no-op statement, inserted at the indent of the next line.
    """
    if _longest_slash_free(code) <= 200:
        return code
    output: list[str] = []
    pending = 0
    for line in code.splitlines(keepends=True):
        leading = len(line.split("/", 1)[0].encode("utf-8"))
        if output and line.strip() and pending + leading > 180:
            indent = line[: len(line) - len(line.lstrip(" "))]
            output.append(indent + "'/'\n")
            pending = len("'\n".encode("utf-8"))
        output.append(line)
        if "/" in line:
            pending = len(line.rsplit("/", 1)[1].encode("utf-8"))
        else:
            pending += len(line.encode("utf-8"))
    text = "".join(output)
    longest = _longest_slash_free(text)
    if longest > 200:
        raise ValueError("AppRun -c payload has a slash-free run of %s bytes" % longest)
    return text


def _pytest_in_runtime(
    runtime: Path,
    profile: str,
    marker: str,
    timeout: float = PYTEST_TIMEOUT_SECONDS,
    pin_vendor: bool = False,
) -> CommandResult:
    if not _is_runtime(runtime):
        return CommandResult(code=127, seconds=0.0, stdout="", stderr="runtime missing: %s" % runtime)
    vendor = _pytest_vendor(profile)
    if vendor is None:
        return CommandResult(
            code=127,
            seconds=0.0,
            stdout="",
            stderr="pytest not found for vendor_%s or vendor/" % profile,
        )
    vendor_first = vendor.name == "vendor_" + profile
    pythonpath = (
        os.pathsep.join([str(vendor), str(REPO_ROOT)])
        if vendor_first
        else str(REPO_ROOT)
    )
    env = _child_env({"PYTHONPATH": pythonpath})
    return _run_command(
        [
            str(runtime),
            "-c",
            _pytest_payload(
                vendor,
                marker,
                vendor_first=vendor_first,
                pin_vendor=pin_vendor and vendor_first,
            ),
        ],
        env=env,
        timeout=timeout,
    )


def _py311_pytest(marker: str, timeout: float | None = None) -> CommandResult:
    return _pytest_in_runtime(
        _runtime("CBCS_FORM_BUILDER_PY311", PY311_DEFAULT),
        "py311",
        marker,
        timeout=PYTEST_TIMEOUT_SECONDS if timeout is None else timeout,
    )


def _py39_pytest(marker: str) -> CommandResult:
    return _pytest_in_runtime(
        _runtime("CBCS_FORM_BUILDER_PY39", PY39_DEFAULT),
        "py39",
        marker,
        pin_vendor=True,
    )


def _judge_pytest(name: str, result: CommandResult, *, require_pass: bool) -> GateResult:
    if result.code == 127:
        detail = result.stderr.strip() or "runtime not found"
        if detail.startswith("runtime missing:"):
            path = detail.split(":", 1)[1].strip()
            return _skip(name, "skipped: runtime not found at %s" % path, result.seconds)
        return _fail(name, result.seconds, detail, _command_log(result))
    if result.timed_out:
        return _fail(
            name,
            result.seconds,
            "timed out after %.0fs" % result.seconds,
            _command_log(result),
        )
    summary, counts = _pytest_counts(result.stdout + "\n" + result.stderr)
    passed = counts.get("passed", 0)
    failed = counts.get("failed", 0) + counts.get("error", 0)
    if result.code == 5 or (result.code == 0 and passed == 0 and failed == 0):
        if require_pass:
            return _fail(
                name,
                result.seconds,
                summary or "no tests passed",
                _command_log(result),
            )
        return _skip(name, "skipped: no tests", result.seconds)
    if result.code == 0 and passed > 0 and failed == 0:
        return _pass(name, result.seconds, summary or "%d passed" % passed)
    return _fail(name, result.seconds, summary or "pytest exit %s" % result.code, _command_log(result))


def gate_unit_py311() -> GateResult:
    return _note_vendor_fallback(
        _judge_pytest("unit-py311", _py311_pytest(UNIT_MARKER), require_pass=True),
        "py311",
    )


def _note_vendor_fallback(result: GateResult, profile: str) -> GateResult:
    if result.status != "pass":
        return result
    vendor = _pytest_vendor(profile)
    if vendor is None or vendor.name == "vendor_" + profile:
        return result
    return GateResult(
        result.name,
        result.status,
        result.seconds,
        "%s; pytest from %s" % (result.detail, vendor.name),
        result.log,
    )


def _py39_skip_reason(runtime: Path) -> str | None:
    """Why the 3.9 lane cannot run, or None when the interpreter can import PySide6.

    The interpreter is probed, not its launcher text: a hybrid AppRun script may
    mention ``freecadcmd`` and still run ``-c`` fine. Tests that need a real
    ``python`` executable (for ``--json`` tools) skip themselves.
    """
    if not _is_runtime(runtime):
        return "skipped: no Python 3.9 runtime at %s" % runtime
    probe = _run_command([str(runtime), "-c", "import PySide6"], timeout=60)
    if probe.code != 0:
        tail = (probe.stderr or probe.stdout or "import failed").strip().splitlines()
        detail = tail[-1] if tail else "import failed"
        return "skipped: %s has no PySide6 (%s)" % (runtime, detail[:200])
    return None


def gate_unit_py39() -> GateResult:
    runtime = _runtime("CBCS_FORM_BUILDER_PY39", PY39_DEFAULT)
    reason = _py39_skip_reason(runtime)
    if reason is not None:
        return _skip("unit-py39-pyside6", reason)
    return _judge_pytest("unit-py39-pyside6", _py39_pytest(UNIT_MARKER), require_pass=True)


def gate_syntax_py39() -> GateResult:
    name = "syntax-py39"
    if not _package_ready():
        return _skip(name, "skipped: no package")
    apprun = _runtime("CBCS_FORM_BUILDER_PY39", PY39_DEFAULT)
    reason = _py39_skip_reason(apprun)
    if reason is not None:
        return _skip(name, reason)
    program = _syntax_program(FEATURE_DIR, TESTS_DIR / "corpus")
    script = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False)
    script.write(program)
    script.close()
    try:
        result = _run_command(
            [str(apprun), script.name],
            env=_child_env(),
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    finally:
        os.unlink(script.name)
    if result.timed_out:
        return _fail(name, result.seconds, "timed out after %.0fs" % result.seconds, _command_log(result))
    if result.code == 0:
        detail = "compiled feature sources and generated corpus output"
        for line in result.stdout.splitlines():
            if line.startswith("cbcs-syntax-py39:"):
                detail = line.split(":", 1)[1].strip()
        return _pass(name, result.seconds, detail)
    return _fail(name, result.seconds, "syntax error", _command_log(result))


def _syntax_program(root: Path, corpus: Path) -> str:
    # Runs inside the 3.9 AppRun process. Keep the program free of 3.10 syntax.
    lines = [
        "import pathlib, sys, tempfile",
        "sys.path.insert(0, %s)" % repr(str(REPO_ROOT)),
        "root = pathlib.Path(%s)" % repr(str(root)),
        "corpus = pathlib.Path(%s)" % repr(str(corpus)),
        "errors = []",
        "files = sorted(path for path in root.rglob('*.py') if path.is_file())",
        "for path in files:",
        "    text = path.read_text(encoding='utf-8')",
        "    try:",
        "        compile(text, str(path), 'exec')",
        "    except SyntaxError as exc:",
        "        errors.append('%s:%s: %s' % (path, exc.lineno, exc.msg))",
        "from app.features.form_builder.engine.codegen.api import generate_form_module",
        "from app.features.form_builder.engine.codegen.resources import (",
        "    compile_resource_tree, read_qrc, render_rc_module,",
        ")",
        "from app.features.form_builder.engine.ids import IdAllocator",
        "from app.features.form_builder.engine.project.forms import FormScope",
        "from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui",
        "outputs = []",
        "for path in sorted(corpus.rglob('*.ui')):",
        "    data = path.read_bytes()",
        "    try:",
        "        xml = data.decode('utf-8')",
        "    except UnicodeDecodeError:",
        "        xml = data.decode('latin-1')",
        "    try:",
        "        read = read_ui(xml, allocator=IdAllocator())",
        "        scope = FormScope(",
        "            kind='project',",
        "            ui_path=str(path),",
        "            project_root=str(path.parent),",
        "            generated_path=str(path.with_name('ui_%s.py' % path.stem)),",
        "            window_path=str(path.with_name('%s_window.py' % path.stem)),",
        "            module_name='ui_' + path.stem,",
        "        )",
        "        generated = generate_form_module(",
        "            read.document, scope=scope, source_bytes=data,",
        "        )",
        "    except UiReadError:",
        "        continue",
        "    except Exception as exc:",
        "        errors.append('%s: %s: %s' % (path, type(exc).__name__, exc))",
        "        continue",
        "    if generated.text:",
        "        outputs.append((str(path), generated.text))",
        "def _read_beside(base, rel):",
        "    target = base / rel",
        "    if not target.is_file():",
        "        raise FileNotFoundError(rel)",
        "    return target.read_bytes()",
        "for path in sorted(corpus.rglob('*.qrc')):",
        "    try:",
        "        document = read_qrc(path.read_text(encoding='utf-8'))",
        "        tree, _diags = compile_resource_tree(",
        "            document,",
        "            read_file=lambda rel, base=path.parent: _read_beside(base, rel),",
        "        )",
        "        rendered = render_rc_module(tree, qrc_file_name=path.name)",
        "    except Exception as exc:",
        "        errors.append('%s: %s: %s' % (path, type(exc).__name__, exc))",
        "        continue",
        "    outputs.append((str(path), rendered))",
        "folder = pathlib.Path(tempfile.mkdtemp(prefix='fb-syntax-'))",
        "for index, pair in enumerate(outputs):",
        "    source, text = pair",
        "    out = folder / ('gen_%04d.py' % index)",
        "    out.write_text(text, encoding='utf-8')",
        "    try:",
        "        compile(text, str(out), 'exec')",
        "    except SyntaxError as exc:",
        "        errors.append('%s -> %s:%s: %s' % (source, out.name, exc.lineno, exc.msg))",
        "if errors:",
        "    sys.stderr.write('\\n'.join(errors) + '\\n')",
        "    raise SystemExit(1)",
        "sys.stdout.write(",
        "    'cbcs-syntax-py39: compiled %d files and %d generated outputs\\n'",
        "    % (len(files), len(outputs))",
        ")",
    ]
    return "\n".join(lines) + "\n"


def gate_pyright() -> GateResult:
    name = "pyright"
    if not _package_ready():
        return _skip(name, "skipped: no package")
    python = str(_runtime("CBCS_FORM_BUILDER_PY311", PY311_DEFAULT))
    commands = (
        ["npx", "pyright", "--pythonpath", python, "app/features/form_builder"],
        [
            "npx",
            "pyright@1.1.410",
            "--pythonpath",
            python,
            "-p",
            "pyrightconfig.tests.json",
            "tests/form_builder",
        ],
    )
    started = time.monotonic()
    details: list[str] = []
    logs: list[str] = []
    for command in commands:
        result = _run_command(command, timeout=COMMAND_TIMEOUT_SECONDS)
        label = " ".join(command)
        if result.timed_out:
            return _fail(name, time.monotonic() - started, "timed out: %s" % label, _command_log(result))
        if result.code != 0:
            logs.append("$ " + label)
            logs.append(_command_log(result))
            return _fail(
                name,
                time.monotonic() - started,
                "pyright exit %s: %s" % (result.code, label),
                "\n".join(logs),
            )
        line = _pyright_summary(result.stdout + "\n" + result.stderr)
        details.append(line or label)
    return _pass(name, time.monotonic() - started, "; ".join(details))


def _pyright_summary(text: str) -> str:
    for line in reversed(text.splitlines()):
        stripped = " ".join(line.split())
        if "error" in stripped and "warning" in stripped:
            return stripped
    return ""


def gate_dune() -> GateResult:
    name = "dune"
    result = _run_command(
        [sys.executable, "-m", "tools.dune.check"],
        timeout=COMMAND_TIMEOUT_SECONDS,
    )
    if result.timed_out:
        return _fail(name, result.seconds, "timed out after %.0fs" % result.seconds, _command_log(result))
    if result.code == 0:
        detail = result.stdout.strip().splitlines()
        return _pass(name, result.seconds, detail[-1] if detail else "dune check ok")
    return _fail(name, result.seconds, "dune check failed", _command_log(result))


def gate_fast_shard() -> GateResult:
    name = "fast-shard-regression"
    result = _run_command(
        [sys.executable, str(REPO_ROOT / "testing" / "run_test_shard.py"), "fast"],
        timeout=FAST_SHARD_TIMEOUT_SECONDS,
    )
    if result.timed_out:
        return _fail(name, result.seconds, "timed out after %.0fs" % result.seconds, _command_log(result))
    summary, counts = _pytest_counts(result.stdout + "\n" + result.stderr)
    if result.code == 0:
        return _pass(name, result.seconds, summary or "fast shard exit 0")
    failed = counts.get("failed", 0) + counts.get("error", 0)
    detail = summary or "fast shard exit %s" % result.code
    if failed:
        detail = summary or "%d failed" % failed
    return _fail(name, result.seconds, detail, _command_log(result))


def gate_oracle() -> GateResult:
    missing = [name for name in ("uic", "rcc") if _resolved_qt_tool(name) is None]
    if missing:
        return _fail("oracle", 0.0, "missing Qt tool: %s" % ", ".join(missing))
    return _judge_pytest("oracle", _py311_pytest("oracle"), require_pass=True)


def gate_perf() -> GateResult:
    # Mac profile, 5 samples. The n=15 harness is the opt-in speed gate.
    before = _format_load()
    judged = _judge_pytest(
        "perf",
        _py311_pytest("perf", timeout=PERF_GATE_TIMEOUT_SECONDS),
        require_pass=True,
    )
    after = _format_load()
    detail = "%s; loadavg 1m/5m/15m start %s end %s" % (judged.detail, before, after)
    return GateResult(judged.name, judged.status, judged.seconds, detail, judged.log)


def gate_speed() -> GateResult:
    name = "speed"
    runtime = _runtime("CBCS_FORM_BUILDER_PY311", PY311_DEFAULT)
    if not _is_runtime(runtime):
        return _skip(name, "skipped: runtime not found at %s" % runtime)
    script = REPO_ROOT / "tools" / "form_builder_speed.py"
    result = _run_command(
        [str(runtime), str(script), "--profile", "mac"],
        env=_child_env({"PYTHONPATH": str(REPO_ROOT)}),
        timeout=180,
    )
    if result.timed_out:
        return _fail(name, result.seconds, "timed out after %.0fs" % result.seconds, _command_log(result))
    text = result.stdout + "\n" + result.stderr
    if result.code == 0 and "speed: PASS" in text:
        return _pass(name, result.seconds, "full mac harness, 15 samples, forms 300/600/1000")
    return _fail(
        name,
        result.seconds,
        "speed harness exit %s" % result.code,
        _command_log(result),
    )


def _format_load() -> str:
    try:
        one, five, fifteen = os.getloadavg()
    except OSError:
        return "unavailable"
    return "%.2f/%.2f/%.2f" % (one, five, fifteen)


_GATE_RUNNERS: dict[str, Callable[[], GateResult]] = {
    "unit-py311": gate_unit_py311,
    "unit-py39-pyside6": gate_unit_py39,
    "syntax-py39": gate_syntax_py39,
    "pyright": gate_pyright,
    "dune": gate_dune,
    "fast-shard-regression": gate_fast_shard,
    "oracle": gate_oracle,
    "perf": gate_perf,
    "speed": gate_speed,
}


if __name__ == "__main__":
    raise SystemExit(main())
