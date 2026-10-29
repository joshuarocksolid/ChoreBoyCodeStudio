"""The committed Qt class table (CONTRACTS 2.5): reads without Qt, matches the
running Qt, and orders properties the way Qt Designer writes them."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional

import pytest

from app.features.form_builder.engine.ui4 import defaults
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.values import CursorShapeValue

_ROOT = Path(__file__).resolve().parents[3]
_TOOL = _ROOT / "tools" / "form_builder" / "dump_qt_classes.py"
_DATA = Path(defaults.__file__).resolve().parent / defaults.DATA_FILE
_RESAVED = Path(__file__).resolve().parents[1] / "corpus" / "designer_resaved"


def test_the_table_reads_without_importing_qt() -> None:
    program = (
        "import sys\n"
        "from app.features.form_builder.engine.ui4.defaults import QtClassTable\n"
        "table = QtClassTable.shared()\n"
        "assert table.class_info('QPushButton') is not None\n"
        "assert not [name for name in sys.modules if name.startswith(('PySide', 'shiboken'))]\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        cwd=str(_ROOT),
        env=dict(os.environ, PYTHONPATH=str(_ROOT)),
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr[-1500:]


def test_rank_runs_across_the_chain_and_redeclared_properties_sit_where_the_subclass_has_them() -> None:
    table = QtClassTable.shared()
    names = [item.name for item in table.properties("QDialog")]
    assert names.index("objectName") < names.index("geometry") < names.index("sizeGripEnabled")
    # QDialog declares ``modal`` again, after its own sizeGripEnabled (Designer writes it there).
    assert names.index("sizeGripEnabled") < names.index("modal")
    assert names.count("modal") == 1
    grid = [item.name for item in table.properties("QGridLayout")]
    assert grid.index("bottomMargin") < grid.index("spacing")
    box = [item.name for item in table.properties("QVBoxLayout")]
    assert box.index("spacing") < box.index("leftMargin")
    assert table.property_rank("QPushButton", "text", dynamic=False)[0] == 0
    # Designer writes stdset="0" on Qt properties whose setter is not set<Name>
    # (isWrapping), so a name the table knows is a Qt property either way.
    assert table.property_rank("QListView", "isWrapping", dynamic=True)[0] == 0
    assert table.property_rank("QPushButton", "myRole", dynamic=True)[0] == 1


def test_a_subclass_shows_its_own_default() -> None:
    info = QtClassTable.shared().property_info("QLineEdit", "cursor")
    assert info is not None
    assert info.default == CursorShapeValue("IBeamCursor")
    assert QtClassTable.shared().property_info("QPushButton", "cursor").default == CursorShapeValue(  # type: ignore[union-attr]
        "ArrowCursor"
    )


def test_the_resaved_corpus_lists_properties_in_table_order() -> None:
    """Qt Designer's own files are the reference for the table's property order."""
    table = QtClassTable.shared()
    problems: List[str] = []
    for path in sorted(_RESAVED.rglob("*.ui")):
        for element in ET.parse(str(path)).getroot().iter():
            if element.tag not in ("widget", "layout", "action"):
                continue
            class_name = element.get("class") or ""
            if table.class_info(class_name) is None:
                continue
            keys = []
            for prop in element.findall("property"):
                name = prop.get("name") or ""
                if prop.get("stdset") == "0" or name.startswith("cbcs"):
                    continue
                if table.property_info(class_name, name) is None:
                    continue
                keys.append(table.property_rank(class_name, name, dynamic=False))
            if keys != sorted(keys):
                problems.append("%s: %s %s" % (path.name, class_name, element.get("name")))
    assert not problems, "\n".join(problems[:20])


def _live() -> Dict[str, object]:
    if "freecadcmd" in os.path.basename(sys.executable):
        pytest.skip("sys.executable is %s, not a Python that runs scripts" % sys.executable)
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    payload = (
        "import runpy, sys\n"
        "sys.argv = [%r, '--json']\n"
        "runpy.run_path(%r, run_name='__main__')\n" % (str(_TOOL), str(_TOOL))
    )
    proc = subprocess.run(
        [sys.executable, "-c", payload],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    if proc.returncode != 0 and "PySide6" in proc.stderr and "No module named" in proc.stderr:
        pytest.skip("no PySide6 in this interpreter")
    assert proc.returncode == 0, proc.stderr[-2000:]
    return {"text": proc.stdout}


def _comparable(table: Dict[str, object], defaults_too: bool) -> Dict[str, object]:
    """What two dumps of the same Qt must agree on. A volatile default is not
    compared, and default values only when the platform is the same."""
    classes = table["classes"]
    assert isinstance(classes, dict)
    found: Dict[str, object] = {}
    for name, body in classes.items():
        entry = {key: body[key] for key in ("super", "module", "flags", "signals", "slots", "default_signal")}
        props = []
        for item in body["properties"]:
            kept = {key: item[key] for key in ("name", "kind", "designable", "stored", "enum", "notify")}
            kept["volatile"] = item["volatile"]
            if defaults_too and not item["volatile"]:
                kept["default"] = item["default"]
            props.append(kept)
        entry["properties"] = props
        if defaults_too:
            entry["defaults"] = {key: value for key, value in body["defaults"].items() if value is not None}
        found[name] = entry
    found["$enums"] = table["enums"]
    return found


def _first_difference(have: Dict[str, object], want: Dict[str, object]) -> Optional[str]:
    for name in sorted(set(have) | set(want)):
        if name not in have:
            return "%s is missing from the committed table" % name
        if name not in want:
            return "%s is not a class in the running Qt" % name
        left, right = have[name], want[name]
        if left == right:
            continue
        if name == "$enums":
            return "the enum table differs"
        assert isinstance(left, dict) and isinstance(right, dict)
        for key in sorted(set(left) | set(right)):
            if key == "properties":
                mine = {item["name"]: item for item in left[key]}
                theirs = {item["name"]: item for item in right[key]}
                for prop in sorted(set(mine) | set(theirs)):
                    if mine.get(prop) != theirs.get(prop):
                        return "%s.%s differs" % (name, prop)
                if [item["name"] for item in left[key]] != [item["name"] for item in right[key]]:
                    return "%s property order differs" % name
            elif left.get(key) != right.get(key):
                return "%s.%s differs" % (name, key)
    return None


def test_the_committed_table_matches_the_running_qt() -> None:
    """Skips on another Qt. Default values are compared only on the same platform
    (the committed table is the Linux one); everything else is compared always."""
    text = str(_live()["text"])
    live = json.loads(text)
    committed = json.loads(_DATA.read_text(encoding="utf-8"))
    if live["qt_version"] != committed["qt_version"]:
        pytest.skip(
            "running Qt %s; the committed table is Qt %s" % (live["qt_version"], committed["qt_version"])
        )
    if live["missing_modules"] != committed["missing_modules"]:
        pytest.skip("this Qt lacks %s" % (live["missing_modules"],))
    same_platform = live["platform"] == committed["platform"]
    difference = _first_difference(
        _comparable(committed, same_platform), _comparable(live, same_platform)
    )
    assert difference is None, difference
    if same_platform:
        assert text == _DATA.read_text(encoding="utf-8"), "same data, different bytes: rerun the dump"
