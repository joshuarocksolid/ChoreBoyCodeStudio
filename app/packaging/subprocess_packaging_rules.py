"""Subprocess checks against measured ChoreBoy AppArmor results."""

from __future__ import annotations

import ast
import shlex
from dataclasses import dataclass
from pathlib import Path

from app.core.models import RuntimeIssue
from app.support.runtime_explainer import HELP_TOPIC_PACKAGING

_SUBPROCESS_CALL_NAMES = {"Popen", "call", "check_call", "check_output", "run"}
_OS_EXEC_NAMES = {
    "execl",
    "execle",
    "execlp",
    "execlpe",
    "execv",
    "execve",
    "execvp",
    "execvpe",
    "popen",
}
_SHELL_BUILTINS = {
    ":",
    ".",
    "[",
    "alias",
    "break",
    "cd",
    "continue",
    "echo",
    "eval",
    "exec",
    "exit",
    "export",
    "false",
    "getopts",
    "hash",
    "local",
    "printf",
    "pwd",
    "read",
    "return",
    "set",
    "shift",
    "source",
    "test",
    "times",
    "trap",
    "true",
    "type",
    "ulimit",
    "umask",
    "unalias",
    "unset",
    "wait",
}

TARGET_FREECAD_VERSION = "1.0.0"
TARGET_TESTED_ON = "2026-10-20"
TARGET_TESTED_ON_DISPLAY = "20 Oct 2026"
# Images shops are moving to. A program they deny gets a warning, not a block.
UPCOMING_FREECAD_VERSIONS = ("1.1.1",)


@dataclass(frozen=True)
class MeasuredExec:
    """One measured program result for a FreeCAD version and test date."""

    freecad_version: str
    tested_on: str
    tested_on_display: str
    program: str
    verdict: str
    detail: str


def _row(
    version: str,
    tested_on: str,
    display: str,
    program: str,
    verdict: str,
    detail: str,
) -> MeasuredExec:
    return MeasuredExec(
        freecad_version=version,
        tested_on=tested_on,
        tested_on_display=display,
        program=program,
        verdict=verdict,
        detail=detail,
    )


# Keyed by FreeCAD version, then by the argv0 string the probe ran or its bare name.
MEASURED_EXEC: dict[str, dict[str, MeasuredExec]] = {
    "1.0.0": {
        program: _row("1.0.0", "2026-10-20", "20 Oct 2026", program, verdict, detail)
        for program, verdict, detail in (
            ("/opt/freecad/AppRun", "allowed", "return code 0"),
            ("/bin/sh", "allowed", "return code 0"),
            ("sh", "allowed", "return code 0"),
            ("/bin/ls", "allowed", "return code 0"),
            ("/usr/bin/pdftoppm", "denied", "PermissionError errno 13"),
            ("pdftoppm", "denied", "PermissionError errno 13"),
            ("/usr/bin/python3", "denied", "PermissionError errno 13"),
            ("python3", "denied", "PermissionError errno 13"),
            ("/bin/bash", "denied", "PermissionError errno 13"),
            ("bash", "denied", "PermissionError errno 13"),
            ("pcmanfm", "denied", "PermissionError errno 13"),
            ("/usr/local/bin/pcmanfm", "denied", "PermissionError errno 13"),
            ("xdg-open", "denied", "PermissionError errno 13"),
            ("/usr/bin/xdg-open", "denied", "PermissionError errno 13"),
            ("okular", "denied", "PermissionError errno 13"),
            ("/usr/bin/okular", "denied", "PermissionError errno 13"),
            ("/usr/bin/env", "denied", "PermissionError errno 13"),
            ("env", "denied", "PermissionError errno 13"),
        )
    },
    "0.21": {
        "/bin/sh": _row(
            "0.21",
            "2026-03-06",
            "6 Mar 2026",
            "/bin/sh",
            "allowed",
            "the only binary that returned success",
        ),
        "/bin/bash": _row("0.21", "2026-03-06", "6 Mar 2026", "/bin/bash", "denied", "PermissionError errno 13"),
        "/usr/bin/env": _row("0.21", "2026-03-06", "6 Mar 2026", "/usr/bin/env", "denied", "PermissionError errno 13"),
        "/usr/bin/python3": _row(
            "0.21",
            "2026-03-06",
            "6 Mar 2026",
            "/usr/bin/python3",
            "denied",
            "PermissionError errno 13",
        ),
    },
    # FreeCAD 1.1.1, ChoreBoyExp, measured 2026-10-20. See docs/DISCOVERY.md section 1B.
    "1.1.1": {
        program: _row("1.1.1", "2026-10-20", "20 Oct 2026", program, verdict, detail)
        for program, verdict, detail in (
            ("/opt/freecad/AppRun", "allowed", "return code 0"),
            ("/bin/sh", "denied", "PermissionError"),
            ("sh", "denied", "PermissionError"),
            ("/bin/bash", "denied", "PermissionError"),
            ("bash", "denied", "PermissionError"),
            ("/usr/bin/git", "denied", "PermissionError"),
            ("git", "denied", "PermissionError"),
        )
    },
}


_SYSTEM_BIN_FOLDERS = frozenset({"/bin", "/usr/bin", "/usr/local/bin", "/sbin", "/usr/sbin"})


def lookup_measured_exec(program: str, *, freecad_version: str = TARGET_FREECAD_VERSION) -> MeasuredExec | None:
    """Return the measured row for *program* on *freecad_version*, if one exists."""
    table = MEASURED_EXEC.get(freecad_version, {})
    name = program.strip()
    row = table.get(name)
    if row is not None:
        return row
    # A system program is the same binary whichever system bin folder names it.
    folder, _, bare = name.rpartition("/")
    if folder in _SYSTEM_BIN_FOLDERS and bare:
        return table.get(bare)
    return None


def running_freecad_table_key() -> str:
    """Return the MEASURED_EXEC key for the FreeCAD this process runs in.

    Packaging runs on the machine the app is usually installed on, so a FreeCAD
    1.1 machine is checked against the 1.1 measurements. Anything else, including
    no importable FreeCAD module, uses the target version.
    """
    import importlib

    try:
        version = importlib.import_module("FreeCAD").Version()
    except Exception:
        return TARGET_FREECAD_VERSION
    major_minor = ".".join(str(part) for part in list(version)[:2])
    for key in MEASURED_EXEC:
        if key.startswith(major_minor + "."):
            return key
    return TARGET_FREECAD_VERSION


def tested_on_phrase(measurement: MeasuredExec | None = None) -> str:
    row = measurement or lookup_measured_exec("/bin/sh")
    if row is None:
        return f"FreeCAD {TARGET_FREECAD_VERSION} (ChoreBoy lab test, {TARGET_TESTED_ON_DISPLAY})"
    return f"FreeCAD {row.freecad_version} (ChoreBoy lab test, {row.tested_on_display})"


def subprocess_issues(
    *,
    tree: ast.AST,
    file_path: Path,
    project_root: Path,
    import_path: str = "",
    freecad_version: str = TARGET_FREECAD_VERSION,
) -> list[RuntimeIssue]:
    """Return packaging issues for subprocess and os exec usage in one module."""
    rel_file = file_path.relative_to(project_root).as_posix()
    bindings = _call_bindings(tree)
    issues: list[RuntimeIssue] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        kind = _call_kind(node, bindings)
        if kind is None:
            continue
        lineno = int(getattr(node, "lineno", 1) or 1)
        shell_call = kind == "os.system" or (kind == "subprocess" and _shell_keyword_is_true(node))
        if shell_call:
            issues.append(_shell_true_issue(rel_file, lineno, import_path))
        raw_shell = _raw_command_text(node) if shell_call else None
        if raw_shell is not None:
            programs = _programs_in_shell_command(raw_shell)
        else:
            argv = _literal_argv(node)
            programs = _programs_from_argv(argv) if argv is not None else []
        for program in programs:
            measurement = lookup_measured_exec(program, freecad_version=freecad_version)
            if measurement is not None and measurement.verdict == "allowed":
                upcoming = _denied_on_upcoming_version(program, freecad_version)
                if upcoming is not None:
                    issues.append(
                        _upcoming_denied_issue(
                            rel_file=rel_file,
                            lineno=lineno,
                            program=program,
                            call_name=_call_display(node),
                            measurement=upcoming,
                            import_path=import_path,
                        )
                    )
                continue
            if measurement is not None and measurement.verdict == "denied":
                issues.append(
                    _denied_issue(
                        rel_file=rel_file,
                        lineno=lineno,
                        program=program,
                        call_name=_call_display(node),
                        measurement=measurement,
                        import_path=import_path,
                    )
                )
                continue
            issues.append(
                _untested_issue(
                    rel_file=rel_file,
                    lineno=lineno,
                    program=program,
                    call_name=_call_display(node),
                    import_path=import_path,
                    freecad_version=freecad_version,
                )
            )
    return issues


def _call_bindings(tree: ast.AST) -> tuple[set[str], dict[str, str], set[str], dict[str, str]]:
    subprocess_modules: set[str] = set()
    subprocess_functions: dict[str, str] = {}
    os_modules: set[str] = set()
    os_functions: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_name = alias.name.split(".")[0]
                bound = alias.asname or alias.name.split(".")[0]
                if root_name == "subprocess":
                    subprocess_modules.add(bound)
                elif root_name == "os":
                    os_modules.add(bound)
        elif isinstance(node, ast.ImportFrom) and node.module:
            root_name = node.module.split(".")[0]
            for alias in node.names:
                bound = alias.asname or alias.name
                if root_name == "subprocess" and alias.name in _SUBPROCESS_CALL_NAMES:
                    subprocess_functions[bound] = alias.name
                elif root_name == "os" and alias.name == "system":
                    os_functions[bound] = "system"
                elif root_name == "os" and alias.name in _OS_EXEC_NAMES:
                    os_functions[bound] = alias.name
    return subprocess_modules, subprocess_functions, os_modules, os_functions


def _call_kind(
    node: ast.Call,
    bindings: tuple[set[str], dict[str, str], set[str], dict[str, str]],
) -> str | None:
    subprocess_modules, subprocess_functions, os_modules, os_functions = bindings
    func = node.func
    if isinstance(func, ast.Name):
        if func.id in subprocess_functions:
            return "subprocess"
        if os_functions.get(func.id) == "system":
            return "os.system"
        if func.id in os_functions:
            return "os.exec"
        return None
    if not isinstance(func, ast.Attribute) or not isinstance(func.value, ast.Name):
        return None
    if func.value.id in subprocess_modules and func.attr in _SUBPROCESS_CALL_NAMES:
        return "subprocess"
    if func.value.id in os_modules and func.attr == "system":
        return "os.system"
    if func.value.id in os_modules and func.attr in _OS_EXEC_NAMES:
        return "os.exec"
    return None


def _call_display(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        owner = func.value.id if isinstance(func.value, ast.Name) else "os"
        return f"{owner}.{func.attr}"
    if isinstance(func, ast.Name):
        return func.id
    return "subprocess"


def _shell_keyword_is_true(node: ast.Call) -> bool:
    for keyword in node.keywords:
        if (
            keyword.arg == "shell"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is True
        ):
            return True
    return False


def _literal_argv(node: ast.Call) -> list[str] | None:
    if not node.args:
        return None
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        text = first.value.strip()
        if not text:
            return None
        try:
            return shlex.split(text)
        except ValueError:
            return text.split()
    if isinstance(first, (ast.List, ast.Tuple)):
        values: list[str] = []
        for elt in first.elts:
            if not isinstance(elt, ast.Constant) or not isinstance(elt.value, str):
                return None
            values.append(elt.value)
        return values
    return None


def _raw_command_text(node: ast.Call) -> str | None:
    if not node.args:
        return None
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        text = first.value.strip()
        return text or None
    return None


def _programs_from_argv(argv: list[str]) -> list[str]:
    if not argv:
        return []
    # The shell itself is checked too: FreeCAD 1.1 denies /bin/sh.
    if argv[0] in {"/bin/sh", "sh"} and "-c" in argv:
        index = argv.index("-c")
        if index + 1 >= len(argv):
            return [argv[0]]
        return [argv[0], *_programs_in_shell_command(argv[index + 1])]
    return [argv[0]]


def _programs_in_shell_command(command: str) -> list[str]:
    programs: list[str] = []
    for segment in _split_shell_segments(command):
        try:
            tokens = shlex.split(segment, posix=True)
        except ValueError:
            tokens = segment.split()
        while tokens and _is_assignment(tokens[0]):
            tokens = tokens[1:]
        if not tokens:
            continue
        program = tokens[0]
        if program == "exec" and len(tokens) > 1:
            program = tokens[1]
        elif program in _SHELL_BUILTINS:
            continue
        programs.append(program)
    return programs


def _split_shell_segments(command: str) -> list[str]:
    segments: list[str] = []
    current: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(command):
        char = command[index]
        if quote is not None:
            current.append(char)
            if char == quote:
                quote = None
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            current.append(char)
            index += 1
            continue
        if command.startswith("&&", index) or command.startswith("||", index):
            segments.append("".join(current))
            current = []
            index += 2
            continue
        if char in {";", "|"}:
            segments.append("".join(current))
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    segments.append("".join(current))
    return [segment.strip() for segment in segments if segment.strip()]


def _is_assignment(token: str) -> bool:
    return "=" in token and not token.startswith("=")


def _program_token(program: str) -> str:
    return program.replace("/", "_").replace(" ", "_")


def _denied_issue(
    *,
    rel_file: str,
    lineno: int,
    program: str,
    call_name: str,
    measurement: MeasuredExec,
    import_path: str,
) -> RuntimeIssue:
    phrase = tested_on_phrase(measurement)
    return RuntimeIssue(
        issue_id=f"package.subprocess.denied.{rel_file}.{lineno}.{_program_token(program)}",
        workflow="package",
        severity="blocking",
        title=f"ChoreBoy blocks the program {Path(program).name}",
        summary=(
            f"{rel_file} starts `{program}` with `{call_name}`. "
            "ChoreBoy does not let apps started from FreeCAD run this program, "
            "so the call would fail with Permission denied (errno 13)."
        ),
        why_it_happened=(
            f"Tested on {phrase}: starting {Path(program).name} from an app was denied. "
            f"The measured result was {measurement.detail}."
        ),
        next_steps=[
            "Remove this call, or do the same work in Python inside your app.",
            "Exec `/opt/freecad/AppRun` with an argv list. Do not call `/bin/sh`.",
        ],
        help_topic=HELP_TOPIC_PACKAGING,
        evidence={
            "source_file": rel_file,
            "line_number": lineno,
            "command_name": program,
            "freecad_version": measurement.freecad_version,
            "tested_on": measurement.tested_on,
            "import_path": import_path,
            "report_row": f"Blocked program: {Path(program).name}",
        },
    )


def _denied_on_upcoming_version(program: str, freecad_version: str) -> MeasuredExec | None:
    """Return the row of a newer FreeCAD image that denies *program*, if any."""
    for version in UPCOMING_FREECAD_VERSIONS:
        if version == freecad_version:
            continue
        row = lookup_measured_exec(program, freecad_version=version)
        if row is not None and row.verdict == "denied":
            return row
    return None


def _upcoming_denied_issue(
    *,
    rel_file: str,
    lineno: int,
    program: str,
    call_name: str,
    measurement: MeasuredExec,
    import_path: str,
) -> RuntimeIssue:
    name = Path(program).name or program
    return RuntimeIssue(
        issue_id=f"package.subprocess.upcoming_denied.{rel_file}.{lineno}.{_program_token(program)}",
        workflow="package",
        severity="degraded",
        title=f"{name} works on FreeCAD {TARGET_FREECAD_VERSION} but not on FreeCAD {measurement.freecad_version}",
        summary=(
            f"{rel_file} starts `{program}` with `{call_name}`. "
            f"That works on today's ChoreBoy, but FreeCAD {measurement.freecad_version} denies it. "
            "The export continues."
        ),
        why_it_happened=(
            f"Tested on {tested_on_phrase(measurement)}: starting {name} from an app was denied. "
            f"The measured result was {measurement.detail}."
        ),
        next_steps=[
            "Exec `/opt/freecad/AppRun` with an argv list. That works on both FreeCAD versions.",
        ],
        help_topic=HELP_TOPIC_PACKAGING,
        evidence={
            "source_file": rel_file,
            "line_number": lineno,
            "command_name": program,
            "freecad_version": measurement.freecad_version,
            "tested_on": measurement.tested_on,
            "import_path": import_path,
            "report_row": f"Denied on FreeCAD {measurement.freecad_version}: {name}",
        },
    )


def _untested_issue(
    *,
    rel_file: str,
    lineno: int,
    program: str,
    call_name: str,
    import_path: str,
    freecad_version: str,
) -> RuntimeIssue:
    sample = lookup_measured_exec("/bin/sh", freecad_version=freecad_version)
    phrase = tested_on_phrase(sample)
    name = Path(program).name or program
    return RuntimeIssue(
        issue_id=f"package.subprocess.untested.{rel_file}.{lineno}.{_program_token(program)}",
        workflow="package",
        severity="degraded",
        title=f"{name} has not been tested on ChoreBoy",
        summary=(
            f"{rel_file} starts `{program}` with `{call_name}`. "
            "CBCS has no test result for this program, so it may work or it may fail "
            "with Permission denied."
        ),
        why_it_happened=(
            f"CBCS checks programs against a list tested on {phrase}. "
            f"{name} is not on that list. The export continues."
        ),
        next_steps=[
            f"Install the packaged app on a ChoreBoy and try the part that uses {name} before you share it.",
        ],
        help_topic=HELP_TOPIC_PACKAGING,
        evidence={
            "source_file": rel_file,
            "line_number": lineno,
            "command_name": program,
            "freecad_version": sample.freecad_version if sample is not None else freecad_version,
            "tested_on": sample.tested_on if sample is not None else "",
            "import_path": import_path,
            "report_row": f"Untested program: {name}",
        },
    )


def _shell_true_issue(rel_file: str, lineno: int, import_path: str) -> RuntimeIssue:
    return RuntimeIssue(
        issue_id=f"package.subprocess.shell_true.{rel_file}.{lineno}",
        workflow="package",
        severity="blocking",
        title="Package uses shell=True subprocess execution",
        summary="A subprocess call opts into shell parsing, which is not part of the supported ChoreBoy packaging contract.",
        why_it_happened=(
            "A shell string hides the program name. FreeCAD 1.1 denies `/bin/sh`. "
            "On FreeCAD 1.0 a denied program still fails when the shell starts it."
        ),
        next_steps=[
            "Replace shell=True with an explicit argv list.",
            "Exec that argv through `/opt/freecad/AppRun`. Do not call `/bin/sh`.",
        ],
        help_topic=HELP_TOPIC_PACKAGING,
        evidence={
            "source_file": rel_file,
            "line_number": lineno,
            "import_path": import_path,
            "report_row": "Blocked program: shell=True",
        },
    )
