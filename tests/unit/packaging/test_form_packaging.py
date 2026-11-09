"""Packaging a project that has a form."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.adoption import scope_for
from app.features.form_builder.engine.project.create import create_form
from app.features.form_builder.engine.project.fs import OsFileSystem
from app.features.form_builder.engine.project.save import write_generated
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.project.packaging import inspect_forms
from app.features.form_builder.install import form_builder_enabled
from app.packaging.form_files import form_packaging_issues, save_packaged_form
from app.packaging.packager import package_project

pytestmark = pytest.mark.unit

_QRC = (
    '<!DOCTYPE RCC><RCC version="1.0">'
    '<qresource prefix="/cbcs"><file>dot.bin</file></qresource></RCC>\n'
)
_RUNTIME = frozenset({"PySide6"})


def _form_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (root / "cbcs").mkdir()
    (root / "cbcs" / "project.json").write_text('{"name":"Demo"}\n', encoding="utf-8")
    created = create_form(str(root), "invoice", OsFileSystem(), template="widget")
    assert created.refused is None
    forms = root / "forms"
    (forms / "dot.bin").write_bytes(b"one")
    (forms / "icons.qrc").write_text(_QRC, encoding="utf-8")
    ui_path = forms / "invoice.ui"
    text = ui_path.read_text(encoding="utf-8").replace(
        "</ui>\n",
        ' <resources><include location="icons.qrc"/></resources>\n</ui>\n',
    )
    ui_path.write_text(text, encoding="utf-8")
    files = OsFileSystem()
    scope = scope_for(str(ui_path), str(root), files)
    document = read_ui(text, allocator=IdAllocator()).document
    written = write_generated(scope, document, text.encode("utf-8"), files)
    assert written.text_written
    (root / "cbcs_connections.py").write_text(
        "def open_connection(name):\n    return None\n",
        encoding="utf-8",
    )
    hand = root / "cbcs" / "form_builder" / "hand_edits"
    hand.mkdir(parents=True)
    (hand / "ui_invoice.abcd1234.py.txt").write_text("edited\n", encoding="utf-8")
    return root


def _package(root: Path, output: Path):
    return package_project(
        project_root=str(root),
        project_name="Invoice",
        entry_file="main.py",
        output_dir=str(output),
        known_runtime_modules=_RUNTIME,
    )


def _payload_py(artifact: Path) -> str:
    app_files = artifact / "payload" / "app_files"
    chunks = []
    for path in sorted(app_files.rglob("*.py")):
        chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def test_package_payload_includes_generated_form_files(tmp_path: Path) -> None:
    root = _form_project(tmp_path)
    result = _package(root, tmp_path / "exports")
    assert result.success, [issue.summary for issue in result.validation.issue_report.issues]
    app_files = Path(result.artifact_root) / "payload" / "app_files"
    assert (app_files / "forms" / "ui_invoice.py").is_file()
    assert (app_files / "forms" / "icons_rc.py").is_file()
    assert (app_files / "cbcs_connections.py").is_file()
    assert not (app_files / "cbcs" / "form_builder").exists()
    report = json.loads((Path(result.artifact_root) / "package_report.json").read_text(encoding="utf-8"))
    paths = {item["path"] for item in report["forms"]}
    assert "forms/ui_invoice.py" in paths
    assert "forms/icons_rc.py" in paths
    assert "cbcs_connections.py" in paths
    packaged = _payload_py(Path(result.artifact_root))
    assert "QUiLoader(" not in packaged
    assert "loadUi(" not in packaged


def test_stale_generated_module_stops_export_until_save(tmp_path: Path) -> None:
    root = _form_project(tmp_path)
    ui_py = root / "forms" / "ui_invoice.py"
    ui_py.write_text(_zero_source_sha(ui_py.read_text(encoding="utf-8")), encoding="utf-8")
    stale = [issue for issue in form_packaging_issues(str(root)) if issue.issue_id == "package.form.stale"]
    if not form_builder_enabled():
        assert stale == []
        result = _package(root, tmp_path / "exports")
        assert result.success, [issue.summary for issue in result.validation.issue_report.issues]
        return
    assert [issue.summary for issue in stale] == ["ui_invoice.py is older than invoice.ui."]
    assert stale[0].evidence["fix_label"] == "Save the form now"
    assert stale[0].is_blocking
    failed = _package(root, tmp_path / "exports")
    assert failed.success is False
    assert save_packaged_form(str(root), str(root / "forms" / "invoice.ui")) == ""
    assert [issue for issue in form_packaging_issues(str(root)) if issue.issue_id == "package.form.stale"] == []


def test_missing_generated_module_stops_export_until_save(tmp_path: Path) -> None:
    root = _form_project(tmp_path)
    (root / "forms" / "ui_invoice.py").unlink()
    missing = [issue for issue in form_packaging_issues(str(root)) if issue.issue_id == "package.form.missing"]
    if not form_builder_enabled():
        assert missing == []
        result = _package(root, tmp_path / "exports")
        assert result.success, [issue.summary for issue in result.validation.issue_report.issues]
        return
    assert any(issue.summary == "ui_invoice.py is missing." for issue in missing)
    assert missing[0].evidence["fix_action"] == "save_form"
    assert save_packaged_form(str(root), str(root / "forms" / "invoice.ui")) == ""
    assert (root / "forms" / "ui_invoice.py").is_file()
    assert [issue for issue in form_packaging_issues(str(root)) if issue.summary == "ui_invoice.py is missing."] == []


_DESIGNER_UI = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QLabel" name="logo">
  <property name="pixmap">
   <pixmap>img/logo.png</pixmap>
  </property>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def test_pyside2_designer_ui_with_a_pixmap_path_adds_no_form_problems(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CBCS_QT_API", "pyside2")
    monkeypatch.delenv("CBCS_FORM_BUILDER", raising=False)
    assert form_builder_enabled() is False
    root = tmp_path / "project"
    (root / "forms").mkdir(parents=True)
    (root / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (root / "cbcs").mkdir()
    (root / "cbcs" / "project.json").write_text(
        '{"name":"Demo","schema_version":1}\n',
        encoding="utf-8",
    )
    (root / "forms" / "invoice.ui").write_text(_DESIGNER_UI, encoding="utf-8")
    assert form_packaging_issues(str(root)) == []
    result = _package(root, tmp_path / "exports")
    form_issues = [
        issue
        for issue in result.validation.issue_report.issues
        if issue.issue_id.startswith("package.form.")
    ]
    assert form_issues == []
    assert result.success, [issue.summary for issue in result.validation.issue_report.issues]


def test_save_packaged_form_returns_the_failure_message(tmp_path: Path) -> None:
    root = _form_project(tmp_path)
    ui = root / "forms" / "invoice.ui"
    ui.write_text("<not-ui>\n", encoding="utf-8")
    message = save_packaged_form(str(root), str(ui))
    assert message
    assert isinstance(message, str)


def test_form_scan_ignores_vendor_and_node_modules(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    for name in ("vendor", "node_modules"):
        folder = root / name
        folder.mkdir(parents=True)
        (folder / "old.ui").write_text("<ui/>\n", encoding="utf-8")
    assert inspect_forms(str(root)).files == ()


def test_runtime_ui_loader_is_a_warning_and_export_continues(tmp_path: Path) -> None:
    root = _form_project(tmp_path)
    (root / "main.py").write_text(
        "def open_form(path):\n    from PySide6.QtUiTools import loadUi\n    return loadUi(path)\n",
        encoding="utf-8",
    )
    loaders = [issue for issue in form_packaging_issues(str(root)) if issue.issue_id == "package.form.runtime_loader"]
    if form_builder_enabled():
        assert len(loaders) == 1
        assert loaders[0].severity == "degraded"
        assert "loadUi" in loaders[0].summary
    else:
        assert loaders == []
    result = _package(root, tmp_path / "exports")
    assert result.success, [issue.summary for issue in result.validation.issue_report.issues]


def _zero_source_sha(text: str) -> str:
    lines = []
    for line in text.splitlines(keepends=True):
        if line.startswith("## cbcs-source-sha256:"):
            newline = "\n" if line.endswith("\n") else ""
            line = "## cbcs-source-sha256: %s%s" % ("0" * 64, newline)
        lines.append(line)
    return "".join(lines)
