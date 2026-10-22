"""Widget trees from setupUi match ``uic -g python`` on the form corpus."""
from __future__ import annotations

import difflib
import importlib.util
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from types import ModuleType

import pytest

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.ui4.reader import read_ui


def _load_helper(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("%s is missing" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec_module = getattr(spec.loader, "exec_module", None)
    if exec_module is None:
        raise RuntimeError("%s is missing" % path)
    exec_module(module)
    return module


_HERE = Path(__file__).resolve().parent
_locator = _load_helper(
    "cbcs_freecad_locator",
    _HERE.parents[1] / "corpus" / "freecad_locator.py",
)
_uic = _load_helper("cbcs_uic_compare", _HERE / "uic_compare.py")
default_search_roots = _locator.default_search_roots
find_freecad_ui_files = _locator.find_freecad_ui_files
_strip_uic = _uic._strip_uic
compare = _uic.compare

_CORPUS = Path(__file__).resolve().parents[2] / "corpus"
# ``env`` and ``same-error`` pass when both modules fail with the same
# exception type and the same normalised message.
# ``uic-setup`` and ``uic-exec`` are not passes: those files are compared to
# QUiLoader, and a match comes back as ``ok``.
_ACCEPT = frozenset({"ok", "same-error", "env", "reader"})
_ARTIFACTS = Path("/opt/cursor/artifacts")
# Minimum FreeCAD forms that match uic, by the locator root that found them.
# Measured: /opt/freecad-1.1 in the cloud image; FreeCAD 1.1.3 and the
# ~/opt/freecad 3.9 prefix on the Mac. Any other root uses _OTHER_ROOT_RATIO.
_FREECAD_FLOORS = {
    # Measured on the Cursor Cloud image: 62 of 67 forms match (5 are env/same-error).
    Path("/opt/freecad-1.1"): 62,
    Path("/Applications/FreeCAD.app"): 62,
    Path.home() / "opt" / "freecad": 56,
}
_OTHER_ROOT_RATIO = 0.75


def _isolated_status(path: Path):
    """Recompare in a fresh interpreter.

    A long in-process scan can leave a destroyed QObject on Qt's focus chain.
    The next file then reports a property diff that a clean process does not.
    The child process exits with os._exit so Qt teardown cannot hide the status.
    """
    import tempfile

    handle = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
    handle.close()
    script = (
        "import os, sys\n"
        "os.environ['QT_QPA_PLATFORM'] = 'offscreen'\n"
        "from pathlib import Path\n"
        "from PySide6.QtWidgets import QApplication\n"
        "from tests.form_builder.engine.codegen.uic_compare import compare\n"
        "QApplication.instance() or QApplication([])\n"
        "status = compare(Path(sys.argv[1]))[0]\n"
        "Path(sys.argv[2]).write_text(status, encoding='utf-8')\n"
        "os._exit(0)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script, str(path), handle.name],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    try:
        text = Path(handle.name).read_text(encoding="utf-8").strip()
    except OSError:
        text = ""
    try:
        os.unlink(handle.name)
    except OSError:
        pass
    if text:
        return text
    if proc.returncode != 0:
        return None
    return None


def _only_code(detail: object, code: str) -> bool:
    if not isinstance(detail, list) or not detail:
        return False
    return all(isinstance(item, tuple) and item and item[0] == code for item in detail)


def _freecad_roots() -> list:
    roots = list(default_search_roots())
    extra = Path("/opt/freecad-1.1")
    if extra.is_dir():
        roots.append(extra)
    return roots


def _root_of(path: Path, roots: list) -> Path:
    """The first locator root that holds ``path`` (the locator resolves paths)."""
    text = str(path)
    for root in roots:
        try:
            resolved = str(root.resolve())
        except OSError:
            continue
        if text == resolved or text.startswith(resolved.rstrip("/") + "/"):
            return root
    return path.parent


def _rows() -> list:
    rows = []
    for folder in ("qt_examples", "synthetic"):
        root = _CORPUS / folder
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.ui")):
            rows.append((folder, path))
    for raw in find_freecad_ui_files(_freecad_roots()):
        rows.append(("freecad", Path(raw)))
    return rows


def _freecad_floor_failures(by_root: dict) -> list:
    """Roots whose matched count is under their floor, as report lines."""
    failures = []
    for root, counts in sorted(by_root.items(), key=lambda item: str(item[0])):
        total = sum(counts.values())
        matched = counts.get("ok", 0)
        floor = _FREECAD_FLOORS.get(root)
        if floor is None:
            floor = _OTHER_ROOT_RATIO * (total - counts.get("fb507", 0))
        if matched < floor:
            failures.append("%s: %d ok, floor %s of %d" % (root, matched, floor, total))
    return failures


def _text_delta(path: Path, uic: str) -> int:
    data = path.read_bytes()
    try:
        xml = data.decode("utf-8")
    except UnicodeDecodeError:
        xml = data.decode("latin-1")
    read = read_ui(xml, allocator=IdAllocator())
    scope = FormScope(
        kind="project",
        ui_path=str(path),
        project_root=str(path.parent),
        generated_path=str(path.with_name("ui_%s.py" % path.stem)),
        window_path=str(path.with_name("%s_window.py" % path.stem)),
        module_name="ui_" + path.stem,
    )
    generated = generate_form_module(read.document, scope=scope, source_bytes=data)
    proc = subprocess.run([uic, "-g", "python", str(path)], capture_output=True, text=True)
    if generated.text is None or proc.returncode != 0:
        return -1
    ours = generated.text.splitlines()
    theirs = _strip_uic(proc.stdout).splitlines()
    return sum(1 for line in difflib.unified_diff(theirs, ours, n=0) if line[:1] in "+-")


@pytest.mark.oracle
@pytest.mark.timeout(270)
@pytest.mark.parity("R3-322")
@pytest.mark.parity("R3-275")
@pytest.mark.parity("R3-276")
@pytest.mark.parity("R3-277")
@pytest.mark.parity("R3-285")
@pytest.mark.parity("R3-299")
def test_corpus_widget_trees_match_uic(qapp) -> None:
    del qapp
    uic = os.environ.get("CBCS_FB_UIC", "")
    if not uic or not Path(uic).is_file():
        message = "CBCS_FB_UIC is not set"
        if os.environ.get("CBCS_FB_REQUIRE_ORACLE") == "1":
            pytest.fail(message)
        pytest.skip(message)
    rows = _rows()
    assert rows
    roots = _freecad_roots()
    counts = Counter()
    by_folder = {}
    by_root = {}
    problems = []
    text_deltas = []
    for folder, path in rows:
        try:
            result = compare(path)
        except Exception as exc:
            result = ("crash", "%s: %s" % (type(exc).__name__, exc))
        status = result[0]
        if status in ("diff", "crash"):
            fresh = _isolated_status(path)
            if fresh in _ACCEPT or fresh == "fb507":
                result = (fresh, "isolated recheck")
                status = fresh
        counts[status] += 1
        folder_counts = by_folder.setdefault(folder, Counter())
        folder_counts[status] += 1
        detail = result[1] if len(result) > 1 else ""
        if status == "refused" and _only_code(detail, "FB507"):
            status = "fb507"
            counts["fb507"] += 1
            counts["refused"] -= 1
            folder_counts["fb507"] += 1
            folder_counts["refused"] -= 1
        if folder == "freecad":
            by_root.setdefault(_root_of(path, roots), Counter())[status] += 1
        if status not in _ACCEPT and status != "fb507":
            problems.append((folder, str(path), status, detail))
        if folder != "freecad" and status in ("ok", "diff"):
            text_deltas.append((str(path.relative_to(_CORPUS)), _text_delta(path, uic)))
    lines = ["status %s" % dict(counts)]
    for folder in sorted(by_folder):
        total = sum(by_folder[folder].values())
        matched = by_folder[folder].get("ok", 0)
        lines.append(
            "%s %d/%d ok %s" % (folder, matched, total, dict(by_folder[folder]))
        )
    for root in sorted(by_root, key=str):
        root_counts = by_root[root]
        lines.append(
            "freecad root %s %d/%d ok %s"
            % (root, root_counts.get("ok", 0), sum(root_counts.values()), dict(root_counts))
        )
    for item in problems:
        lines.append("MISMATCH %s %s %s %s" % item)
    changed = [item for item in text_deltas if item[1] > 0]
    lines.append("text-diff files %d of %d (informational)" % (len(changed), len(text_deltas)))
    changed.sort(key=lambda item: item[1], reverse=True)
    for path, delta in changed[:20]:
        lines.append("text %s lines %d" % (path, delta))
    report = "\n".join(lines) + "\n"
    print(report)
    try:
        _ARTIFACTS.mkdir(parents=True, exist_ok=True)
        (_ARTIFACTS / "uic-oracle.txt").write_text(report, encoding="utf-8")
    except OSError:
        pass
    assert not problems, report
    if os.environ.get("CBCS_FB_REQUIRE_ORACLE") == "1":
        assert by_root, "no FreeCAD forms found under %s" % [str(root) for root in roots]
    assert by_folder["qt_examples"]["ok"] >= 54
    assert by_folder["synthetic"]["ok"] >= 147
    assert not _freecad_floor_failures(by_root), report
