#!/usr/bin/env python3
"""Run the form-builder quality gates and print a pass/fail table.

Gates that need app/features/form_builder report "skipped: no package" until
that package exists. A skip does not fail the process. A failed gate does.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
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

UNIT_MARKER = "not oracle and not perf and not performance"
PYTEST_TIMEOUT_SECONDS = 300
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


def _runtime(env_name: str, default: str) -> Path:
    raw = os.environ.get(env_name, "").strip() or default
    return Path(raw).expanduser()


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


def _child_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    env.pop("VIRTUAL_ENV_PROMPT", None)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["CBCS_DISABLE_BACKGROUND_RUNTIME"] = "1"
    env["CBCS_SYNC_PROJECT_OPEN"] = "1"
    env["CBCS_QT_API"] = "pyside6"
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


def _pytest_payload(vendor: Path, marker: str, *, vendor_first: bool) -> str:
    # os._exit skips the Shiboken destructor, which segfaults if Python
    # wrappers outlive Qt. Flush first so a captured pipe keeps the summary.
    args = ["-q", "--tb=line", "tests/form_builder", "-m", marker]
    if vendor_first:
        path_setup = "sys.path.insert(0, {repo!r});sys.path.insert(0, {vendor!r});"
    else:
        # A mismatched vendor tree stays behind the interpreter's site-packages
        # so a py39 extension does not shadow PySide6.
        path_setup = "sys.path.insert(0, {repo!r});sys.path.append({vendor!r});"
    # FreeCAD 1.0's FemMigrateApp implements the old import hook but not
    # find_spec. pytest calls find_spec on every meta_path entry while loading
    # conftest, so the Python 3.9 lane dies before collection. FreeCAD 1.1
    # already provides find_spec, and this shim leaves that class alone.
    shim = (
        "for _finder in sys.meta_path:\n"
        "    if type(_finder).__name__ != 'FemMigrateApp' or hasattr(_finder, 'find_spec'):\n"
        "        continue\n"
        "    def _find_spec(self, fullname, path=None, target=None):\n"
        "        found = self.find_module(fullname, path)\n"
        "        if found is None:\n"
        "            return None\n"
        "        return __import__('importlib.util', fromlist=['spec_from_loader']).spec_from_loader(fullname, found)\n"
        "    type(_finder).find_spec = _find_spec\n"
    )
    payload = (
        "import os, sys\n"
        + shim
        + path_setup
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


def _pytest_in_runtime(runtime: Path, profile: str, marker: str) -> CommandResult:
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
        [str(runtime), "-c", _pytest_payload(vendor, marker, vendor_first=vendor_first)],
        env=env,
        timeout=PYTEST_TIMEOUT_SECONDS,
    )


def _py311_pytest(marker: str) -> CommandResult:
    return _pytest_in_runtime(_runtime("CBCS_FORM_BUILDER_PY311", PY311_DEFAULT), "py311", marker)


def _py39_pytest(marker: str) -> CommandResult:
    return _pytest_in_runtime(_runtime("CBCS_FORM_BUILDER_PY39", PY39_DEFAULT), "py39", marker)


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


def gate_unit_py39() -> GateResult:
    return _judge_pytest("unit-py39-pyside6", _py39_pytest(UNIT_MARKER), require_pass=True)


def gate_syntax_py39() -> GateResult:
    name = "syntax-py39"
    if not _package_ready():
        return _skip(name, "skipped: no package")
    apprun = _runtime("CBCS_FORM_BUILDER_PY39", PY39_DEFAULT)
    files = sorted(path for path in FEATURE_DIR.rglob("*.py") if path.is_file())
    if _is_runtime(apprun):
        program = _syntax_program(FEATURE_DIR)
        result = _run_command([str(apprun), "-c", program], env=_child_env(), timeout=60)
        if result.timed_out:
            return _fail(name, result.seconds, "timed out after %.0fs" % result.seconds, _command_log(result))
        if result.code == 0:
            detail = result.stdout.strip() or "compiled %d files" % len(files)
            return _pass(name, result.seconds, detail.splitlines()[-1])
        return _fail(name, result.seconds, "syntax error", _command_log(result))
    return _syntax_via_ast(name, files)


def _syntax_program(root: Path) -> str:
    # Runs inside the 3.9 AppRun process. Keep the program free of 3.10 syntax.
    lines = [
        "import pathlib, sys",
        "root = pathlib.Path(%s)" % repr(str(root)),
        "files = sorted(path for path in root.rglob('*.py') if path.is_file())",
        "errors = []",
        "for path in files:",
        "    text = path.read_text(encoding='utf-8')",
        "    try:",
        "        compile(text, str(path), 'exec')",
        "    except SyntaxError as exc:",
        "        errors.append('%s:%s: %s' % (path, exc.lineno, exc.msg))",
        "if errors:",
        "    sys.stderr.write('\\n'.join(errors) + '\\n')",
        "    raise SystemExit(1)",
        "sys.stdout.write('compiled %d files\\n' % len(files))",
    ]
    return _apprun_safe("\n".join(lines) + "\n")


def _syntax_via_ast(name: str, files: Sequence[Path]) -> GateResult:
    started = time.monotonic()
    errors: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        try:
            ast.parse(text, filename=str(path), feature_version=(3, 9))
        except SyntaxError as exc:
            errors.append("%s:%s: %s" % (path, exc.lineno, exc.msg))
    seconds = time.monotonic() - started
    if errors:
        return _fail(name, seconds, "syntax error", "\n".join(errors))
    apprun = _runtime("CBCS_FORM_BUILDER_PY39", PY39_DEFAULT)
    return _pass(
        name,
        seconds,
        "compiled %d files with ast.parse feature_version=(3, 9); runtime not found at %s"
        % (len(files), apprun),
    )


def gate_pyright() -> GateResult:
    name = "pyright"
    if not _package_ready():
        return _skip(name, "skipped: no package")
    commands = (
        ["npx", "pyright", "app/features/form_builder"],
        ["npx", "pyright", "-p", "pyrightconfig.tests.json", "tests/form_builder"],
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
    judged = _judge_pytest("oracle", _py311_pytest("oracle"), require_pass=False)
    return judged


def gate_perf() -> GateResult:
    before = _format_load()
    judged = _judge_pytest("perf", _py311_pytest("perf"), require_pass=False)
    after = _format_load()
    detail = "%s; loadavg 1m/5m/15m start %s end %s" % (judged.detail, before, after)
    return GateResult(judged.name, judged.status, judged.seconds, detail, judged.log)


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
}


if __name__ == "__main__":
    raise SystemExit(main())
