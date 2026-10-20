"""QUiLoader and uic oracles."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from spikes.form_builder.generate import generate_ui
from spikes.form_builder.model import iter_widgets
from spikes.form_builder.tests.treeutil import signature
from spikes.form_builder.xmlio import dump_ui, load_ui

APP = QApplication.instance() or QApplication([])
UIC = "/Applications/FreeCAD.app/Contents/Resources/lib/qt6/uic"
FREECAD = Path("/Applications/FreeCAD.app")

FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry">
   <rect><x>0</x><y>0</y><width>400</width><height>300</height></rect>
  </property>
  <property name="windowTitle"><string>Form</string></property>
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0">
    <widget class="QLabel" name="nameLabel">
     <property name="text"><string>&amp;Name</string></property>
     <property name="buddy"><cstring>nameEdit</cstring></property>
    </widget>
   </item>
   <item row="0" column="1">
    <widget class="QLineEdit" name="nameEdit">
     <property name="placeholderText"><string>Name</string></property>
    </widget>
   </item>
   <item row="1" column="0">
    <widget class="QLabel" name="notesLabel">
     <property name="text"><string>Notes</string></property>
    </widget>
   </item>
   <item row="1" column="1">
    <widget class="QPlainTextEdit" name="notesEdit"/>
   </item>
   <item row="2" column="0" colspan="2">
    <widget class="QDialogButtonBox" name="buttonBox">
     <property name="standardButtons">
      <set>QDialogButtonBox::Cancel|QDialogButtonBox::Ok</set>
     </property>
    </widget>
   </item>
  </layout>
 </widget>
 <tabstops>
  <tabstop>nameEdit</tabstop>
  <tabstop>notesEdit</tabstop>
 </tabstops>
 <resources/>
 <connections/>
</ui>
"""


def _load(path: str):
    from PySide6.QtUiTools import QUiLoader

    loader = QUiLoader()
    loader.clearPluginPaths()
    widget = loader.load(path)
    if widget is None:
        raise RuntimeError(loader.errorString() or f"failed to load {path}")
    return widget


class LoaderOracleTest(unittest.TestCase):
    def test_saved_form_matches_model_and_reloads(self):
        doc = load_ui(FORM)
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "form.ui")
            Path(path).write_text(dump_ui(doc), encoding="utf-8")
            again = dump_ui(load_ui(Path(path).read_text(encoding="utf-8")))
            self.assertEqual(Path(path).read_text(encoding="utf-8"), again)
            loaded = _load(path)
        names = {widget.object_name for widget in iter_widgets(doc)}
        found = {loaded.objectName()}
        for child in loaded.findChildren(QWidget):
            if child.objectName():
                found.add(child.objectName())
        self.assertTrue(names <= found)
        self.assertEqual(loaded.layout().metaObject().className(), "QFormLayout")
        label = loaded.findChild(QWidget, "nameLabel")
        edit = loaded.findChild(QWidget, "nameEdit")
        self.assertIs(label.buddy(), edit)
        self.assertEqual(loaded.windowTitle(), "Form")


class GeneratorOracleTest(unittest.TestCase):
    def test_sample_matches_uic_tree(self):
        doc = load_ui(FORM)
        ours = generate_ui(doc, "form.ui")
        with tempfile.TemporaryDirectory() as folder:
            ui_path = Path(folder) / "form.ui"
            ui_path.write_text(dump_ui(doc), encoding="utf-8")
            uic_py = Path(folder) / "ui_form_uic.py"
            subprocess.check_call([UIC, "-g", "python", "-o", str(uic_py), str(ui_path)])
            our_py = Path(folder) / "ui_form_ours.py"
            our_py.write_text(ours, encoding="utf-8")
            diff = _diff(uic_py.read_text(encoding="utf-8"), ours)
            report = Path(__file__).resolve().parents[1] / "generator_diff.txt"
            report.write_text(diff or "(no textual diff)\n", encoding="utf-8")
            uic_widget = _setup(uic_py, "Ui_Form", QWidget)
            our_widget = _setup(our_py, "Ui_Form", QWidget)
            self.assertEqual(signature(uic_widget), signature(our_widget), diff[:1500])


class CorpusOracleTest(unittest.TestCase):
    def test_designer_corpus_round_trip(self):
        paths = sorted(FREECAD.rglob("*.ui"))
        failures = []
        for path in paths:
            try:
                original = path.read_text(encoding="utf-8")
                doc = load_ui(original)
                saved = dump_ui(doc)
                saved_again = dump_ui(load_ui(saved))
                if saved != saved_again:
                    failures.append(f"{path.name}: save is not deterministic")
                    continue
                with tempfile.TemporaryDirectory() as folder:
                    copy_path = Path(folder) / "form.ui"
                    copy_path.write_text(saved, encoding="utf-8")
                    before = _load(str(path))
                    after = _load(str(copy_path))
                    if signature(before) != signature(after):
                        failures.append(f"{path.name}: QUiLoader tree changed")
            except Exception as exc:
                failures.append(f"{path.name}: {type(exc).__name__}: {exc}")
        rate = 100.0 * (len(paths) - len(failures)) / max(len(paths), 1)
        report = Path(__file__).resolve().parents[1] / "corpus_report.txt"
        lines = [f"passed {len(paths) - len(failures)} / {len(paths)} ({rate:.1f}%)", *failures]
        report.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.assertEqual(failures, [], "\n".join(lines[:40]))


def _setup(path: Path, class_name: str, host_cls):
    import importlib.util

    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    host = host_cls()
    ui = getattr(module, class_name)()
    ui.setupUi(host)
    return host


def _diff(left: str, right: str) -> str:
    import difflib

    return "".join(
        difflib.unified_diff(
            left.splitlines(True),
            right.splitlines(True),
            fromfile="uic",
            tofile="ours",
        )
    )


if __name__ == "__main__":
    unittest.main()
