# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false, reportOptionalCall=false, reportIndexIssue=false
"""Your own classes, engine side: the ``ast`` resolver, the registry, the commands and the header (M5.4).

R3 123 and 194-195 live here; the editor never imports a project module (CONTRACTS 10.4).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import List

import pytest

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.codegen.names import header_module
from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog_ext.promote import UseBaseClass, UseOwnClass
from app.features.form_builder.engine.diagnostics import CODES
from app.features.form_builder.engine.project import custom_widgets as cw
from app.features.form_builder.engine.project.adoption import FormScope
from app.features.form_builder.engine.ui4.writer import write_ui
from tests.form_builder.engine.commands._support import BOX, nid, open_log

pytestmark = pytest.mark.unit

TILL = '''"""Mentions TillDisplay and QLabel only in text."""
import os
from PySide6.QtWidgets import QLabel, QWidget

os.environ["CBCS_TEST_IMPORTED_TILL"] = "yes"


class Helper:
    pass


class TillDisplay(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)


class FrameBased(QtWidgets.QFrame):
    pass


class Derived(Helper):
    pass
'''


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "shop"
    (root / "widgets").mkdir(parents=True)
    (root / "widgets" / "till_display.py").write_text(TILL, encoding="utf-8")
    (root / "widgets" / "broken.py").write_text(
        "import sys\nclass Broken(QWidget):\n    def __init__(self, parent=None):\n        raise RuntimeError('boom')\n",
        encoding="utf-8",
    )
    pkg = root / "widgets" / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("class FromInit(QPushButton):\n    pass\n", encoding="utf-8")
    return root


def test_the_seven_check_lines(tmp_path: Path) -> None:
    root = str(_project(tmp_path))

    def line(module: str, name: str, expected: str, project: object = root) -> str:
        check = cw.check_module(project, module, name, expected)  # type: ignore[arg-type]
        return cw.check_sentence(check, name, module, "Label", lambda q: {"QFrame": "Frame"}.get(q, q))

    assert line("widgets.till_display", "TillDisplay", "QLabel") == "Found TillDisplay in widgets/till_display.py."
    assert line("widgets.till_display", "FrameBased", "QLabel") == (
        "FrameBased in widgets/till_display.py is based on Frame, not Label. The form may look different when it runs."
    )
    assert line("widgets.till_display", "Nope", "QLabel") == "widgets/till_display.py has no class called Nope."
    assert line("widgets.missing", "Thing", "QLabel") == (
        "There's no widgets/missing.py in this project yet. You can still use the name."
    )
    assert line("widgets..x", "Thing", "QLabel") == "Use a module path like widgets.till_display."
    assert line("widgets.till_display", "2Bad", "QLabel") == (
        "Use a class name like TillDisplay: letters, digits and _, starting with a letter."
    )
    assert line("widgets.till_display", "TillDisplay", "QLabel", project=None) == (
        "This form isn't in a project, so Preview shows a stand-in."
    )
    assert cw.check_module(root, "widgets.pkg", "FromInit", "QPushButton").path == "widgets/pkg/__init__.py"
    # A base taken from another module can't be judged: the class counts as found.
    assert cw.check_module(root, "widgets.till_display", "Derived", "QLabel").state == cw.FOUND
    assert cw.check_module(root, "widgets.till_display", "TillDisplay", "QLabel").state == cw.FOUND
    assert cw.BAD_CLASS in cw.BLOCKING and cw.BAD_MODULE in cw.BLOCKING


@pytest.mark.parity("R3-198")
def test_the_resolver_never_imports_or_runs_project_code(tmp_path: Path) -> None:
    root = str(_project(tmp_path))
    before = set(sys.modules)
    os.environ.pop("CBCS_TEST_IMPORTED_TILL", None)
    cw.check_module(root, "widgets.till_display", "TillDisplay", "QLabel")
    cw.check_module(root, "widgets.broken", "Broken", "QWidget")
    cw.classes_in(root, "widgets/till_display.py")
    gained = {name for name in set(sys.modules) - before if name.split(".")[0] in ("widgets", "till_display", "broken")}
    assert gained == set()
    assert "CBCS_TEST_IMPORTED_TILL" not in os.environ


def test_the_resolver_stays_inside_the_project_and_survives_hostile_files(tmp_path: Path) -> None:
    root = _project(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_text("class Out(QWidget):\n    pass\n", encoding="utf-8")
    try:
        os.symlink(outside, root / "widgets" / "linked.py")
    except OSError:
        pytest.skip("no symlinks")
    assert cw.module_file(str(root), "widgets.linked") == ""
    assert cw.module_file(str(root), "..outside") == ""
    assert cw.module_parts("os.system('x')") is None
    (root / "widgets" / "deep.py").write_text("x = " + "(" * 5000 + ")" * 5000 + "\n", encoding="utf-8")
    (root / "widgets" / "bad.py").write_text("class (:\n", encoding="utf-8")
    (root / "widgets" / "huge.py").write_text("#" * (cw.MAX_BYTES + 10), encoding="utf-8")
    for module in ("widgets.deep", "widgets.bad", "widgets.huge"):
        assert cw.check_module(str(root), module, "Anything", "QWidget").state == cw.NO_CLASS


@pytest.mark.parametrize("line", ["x = " + "1+" * 300000 + "1", "x = a" + ".b" * 300000, "x = f" + "()" * 300000])
def test_one_very_long_expression_does_not_kill_the_editor(tmp_path: Path, line: str) -> None:
    """On Python 3.9 (ChoreBoy) ``ast.parse`` of such a file (600 KB, under ``MAX_BYTES``) overflows the C
    stack and takes the editor down with it. Only class headers are parsed, so the class after it is found."""
    root = _project(tmp_path)
    (root / "widgets" / "long.py").write_text(
        '"""class Fake(QWidget): pass\n"""\n' + line + "\nclass Wanted(\n    QLabel,  # the base\n):\n    pass\n",
        encoding="utf-8",
    )
    check = cw.check_module(str(root), "widgets.long", "Wanted", "QLabel")
    assert (check.state, check.bases, check.line) == (cw.FOUND, ("QLabel",), 4)
    assert cw.check_module(str(root), "widgets.long", "Fake", "QWidget").state == cw.NO_CLASS


def test_a_fifo_named_like_a_module_does_not_block_the_check(tmp_path: Path) -> None:
    root = _project(tmp_path)
    if not hasattr(os, "mkfifo"):
        pytest.skip("no FIFOs")
    os.mkfifo(str(root / "widgets" / "pipe.py"))
    assert cw.classes_in(str(root), "widgets/pipe.py") == ()


def test_the_check_is_cached_by_mtime(tmp_path: Path) -> None:
    root = _project(tmp_path)
    assert cw.check_module(str(root), "widgets.till_display", "TillDisplay", "QLabel").state == cw.FOUND
    path = root / "widgets" / "till_display.py"
    path.write_text("class TillDisplay(QFrame):\n    pass\n", encoding="utf-8")
    os.utime(path, ns=(1_000_000_000, 2_000_000_000))
    assert cw.check_module(str(root), "widgets.till_display", "TillDisplay", "QLabel").state == cw.OTHER_BASE


@pytest.mark.parity("R3-196", "R3-197")
def test_declaration_fields_stand_in_for_the_plugin_interface_and_round_trip() -> None:
    """Name, group, tooltip, include file, container, size hint, add-page method, signals and slots are
    declarations the editor reads (never plugin code): they round-trip through the registry, the form's
    declaration and the Insert entry (UX-CUST-011)."""
    from app.features.form_builder.qtside.insert.catalog._custom import custom_entries

    entry = cw.RegistryEntry(
        "Wizardish", "widgets.wizardish", "QWidget", container=True, description="Pages of steps",
        size=(300, 120), add_page_method="addStep", signals=("stepChanged(int)",), slots=("next()", "back()"),
    )
    assert cw.entry_from_json(entry.to_json()) == entry
    spec = cw.declaration_spec(entry)
    assert spec.field("container") == 1 and spec.field("addpagemethod") == "addStep"
    assert (spec.field("sizehint").width, spec.field("sizehint").height) == (300, 120)
    [tile] = custom_entries((), (entry,))
    assert (tile.category, tile.description, tile.header, tile.base_class) == ("Your widgets", "Pages of steps", "widgets/wizardish.h", "QWidget")
    log = open_log(BOX)
    doc = log.document
    log.execute(UseOwnClass((nid(doc, "label"),), "Wizardish", "widgets.wizardish", "QWidget", container=True, size=(300, 120)))
    declared = doc.custom_widget("Wizardish")
    back = cw.entry_from_declaration(declared)
    assert back is not None and back.container and back.size == (300, 120) and back.module == "widgets.wizardish"
    # The editor reads declarations, not code: no Designer plugin path is touched and nothing is imported.
    assert "widgets.wizardish" not in sys.modules


def test_the_registry_round_trips_and_ignores_bad_entries() -> None:
    store = cw.MemoryStore()
    registry = cw.CustomWidgetRegistry(store)
    entry = cw.RegistryEntry(
        "TillDisplay", "widgets.till_display", "QLabel", description="Running total", size=(200, 48),
        add_page_method="addTill", signals=("totalChanged(int)",), slots=("reset()",),
    )
    assert registry.upsert(entry) is True
    assert registry.upsert(entry) is False
    assert registry.entries() == (entry,)
    store.value = store.value + [{"class": "Bad Name", "module": "x", "base": "QLabel"}, "junk", {"class": "TillDisplay", "module": "again", "base": "QLabel"}]
    assert registry.entries() == (entry,)
    assert [item.class_name for item in registry.compatible("QLabel")] == ["TillDisplay"]
    assert registry.compatible("QPushButton") == ()
    assert [item.class_name for item in registry.compatible("QWidget")] == ["TillDisplay"]
    assert registry.remove("TillDisplay") is True and registry.entries() == ()
    assert store.value is None
    assert entry.label == "TillDisplay · widgets.till_display"


def test_the_header_is_the_module_as_designer_and_uic_read_it() -> None:
    assert cw.header_for_module("widgets.till_display") == "widgets/till_display.h"
    assert header_module("widgets/till_display.h") == "widgets.till_display"
    assert cw.module_for_header("widgets/till_display.h") == "widgets.till_display"
    with pytest.raises(ValueError):
        cw.header_for_module("widgets..bad")
    from app.features.form_builder.engine import diagnostic_codes

    diagnostic_codes.discover()
    assert "FB035" in CODES


@pytest.mark.parity("R3-123", "R3-194")
def test_use_own_class_declares_once_writes_the_header_and_demotes_to_the_original_bytes() -> None:
    log = open_log(BOX)
    doc = log.document
    before = write_ui(doc).text
    label = nid(doc, "label")
    log.execute(UseOwnClass((label,), "TillDisplay", "widgets.till_display", "QLabel", names=("label",)))
    text = write_ui(doc).text
    assert '<widget class="TillDisplay" name="label">' in text
    assert (
        "<customwidget>\n   <class>TillDisplay</class>\n   <extends>QLabel</extends>\n"
        '   <header location="local">widgets/till_display.h</header>\n  </customwidget>'
    ) in text
    assert text.count("<customwidget>") == 1
    assert log.undo_label() == "Use class TillDisplay for label"
    # A second widget of the same class shares the declaration.
    log.execute(UseOwnClass((nid(doc, "okButton"),), "TillDisplay", "widgets.till_display", "QLabel", names=("okButton",)))
    assert write_ui(doc).text.count("<customwidget>") == 1
    log.undo()
    log.execute(UseBaseClass((label,), "label", names=("label",)))
    assert log.undo_label() == "Use label for label"
    assert "<customwidget>" not in write_ui(doc).text
    assert write_ui(doc).text == before
    while log.can_undo():
        log.undo()
    assert write_ui(doc).text == before


@pytest.mark.parity("R3-195")
def test_container_size_and_other_declaration_children_are_kept() -> None:
    log = open_log(BOX)
    doc = log.document
    log.execute(
        UseOwnClass((nid(doc, "label"),), "Card", "widgets.card", "QWidget", container=True, size=(200, 80), names=("label",))
    )
    text = write_ui(doc).text
    assert "<sizehint>" in text and "<width>200</width>" in text and "<container>1</container>" in text
    # A hand-written declaration keeps its other children when another widget joins the class.
    kept = text.replace("<container>1</container>", "<container>1</container>\n   <addpagemethod>addCard</addpagemethod>")
    log2 = open_log(kept)
    log2.execute(UseOwnClass((nid(log2.document, "okButton"),), "Card", "widgets.card", "QWidget", names=("okButton",)))
    again = write_ui(log2.document).text
    assert "<addpagemethod>addCard</addpagemethod>" in again and again.count("<customwidget>") == 1


def test_use_own_class_refuses_the_form_itself_and_a_class_declared_on_another_base() -> None:
    log = open_log(BOX)
    doc = log.document
    with pytest.raises(CommandRejected):
        log.execute(UseOwnClass((doc.root.id,), "TillDisplay", "widgets.till_display", "QWidget"))
    log.execute(UseOwnClass((nid(doc, "label"),), "TillDisplay", "widgets.till_display", "QLabel", names=("label",)))
    with pytest.raises(CommandRejected):
        log.execute(UseOwnClass((nid(doc, "okButton"),), "TillDisplay", "widgets.till_display", "QPushButton"))
    with pytest.raises(CommandRejected):
        log.execute(UseOwnClass((nid(doc, "okButton"),), "Till Display", "widgets.till_display", "QPushButton"))


def test_switching_to_another_own_class_drops_the_old_declaration_when_nothing_uses_it() -> None:
    log = open_log(BOX)
    doc = log.document
    label = nid(doc, "label")
    log.execute(UseOwnClass((label,), "TillDisplay", "widgets.till_display", "QLabel", names=("label",)))
    log.execute(UseOwnClass((label,), "Broken", "widgets.broken", "QLabel", names=("label",)))
    text = write_ui(doc).text
    assert "<class>Broken</class>" in text and "<class>TillDisplay</class>" not in text


def _uic() -> str:
    uic = os.environ.get("CBCS_FB_UIC", "") or "/Applications/FreeCAD.app/Contents/Resources/lib/qt6/uic"
    if not Path(uic).is_file():
        pytest.skip("no uic")
    return uic


def _imports(source: str) -> List[str]:
    return sorted(
        line.strip()
        for line in source.splitlines()
        if line.startswith(("from ", "import ")) and "PySide" not in line and "__future__" not in line
    )


@pytest.mark.pain("P-7")
@pytest.mark.parity("R3-123", "R3-194")
def test_generated_code_imports_the_real_module_like_uic(tmp_path: Path) -> None:
    log = open_log(BOX)
    doc = log.document
    log.execute(UseOwnClass((nid(doc, "label"),), "TillDisplay", "widgets.till_display", "QLabel", names=("label",)))
    log.execute(UseOwnClass((nid(doc, "okButton"),), "Pay", "widgets.pay", "QPushButton", names=("okButton",)))
    text = write_ui(doc).text
    ui = tmp_path / "shop.ui"
    ui.write_text(text, encoding="utf-8")
    ours = generate_form_module(
        doc,
        scope=FormScope(
            kind="project", ui_path=str(ui), project_root=str(tmp_path), generated_path=str(tmp_path / "ui_shop.py"),
            window_path=str(tmp_path / "shop_window.py"), module_name="ui_shop",
        ),
        source_bytes=text.encode("utf-8"),
    )
    assert ours.text is not None
    done = subprocess.run([_uic(), "-g", "python", str(ui)], capture_output=True, text=True, check=True)
    assert _imports(ours.text) == _imports(done.stdout)
    assert "from widgets.till_display import TillDisplay" in ours.text
    assert "self.label = TillDisplay(" in ours.text.replace("self.Form", "Form") or "TillDisplay(" in ours.text
    assert not [d for d in ours.diagnostics if d.code in ("FB504", "FB502")]
