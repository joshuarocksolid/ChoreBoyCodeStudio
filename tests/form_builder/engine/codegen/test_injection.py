"""XML names stay out of generated Python syntax (CONTRACTS.md section 9.3)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.codegen.window_template import render_window_class
from app.features.form_builder.engine.diagnostics import Severity
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui

_DIR = Path(__file__).resolve().parents[2] / "corpus" / "adversarial" / "codegen"

# Names a safe form may add on top of the base template.
_EXTRA = frozenset(
    {
        "AlignLeft",
        "QWidget",
        "Qt",
        "RightToLeft",
        "clear",
        "clicked",
        "connect",
        "setAlignment",
        "setBuddy",
        "setFlat",
        "setLayoutDirection",
        "setProperty",
        "setTabOrder",
    }
)

_CASES = (
    ("attr.ui", "refuse"),
    ("buddy.ui", "drop"),
    ("cls.ui", "refuse"),
    ("comment.ui", "reader"),
    ("comment_escaped.ui", "clean"),
    ("conn.ui", "clean"),
    ("conn2.ui", "clean"),
    ("conn_stmt.ui", "refuse"),
    ("cpp.ui", "refuse"),
    ("cursor.ui", "refuse"),
    ("enum.ui", "refuse"),
    ("extends.ui", "refuse"),
    ("lclass.ui", "refuse"),
    ("objname_dyn.ui", "clean"),
    ("promo.ui", "refuse"),
    ("promo2.ui", "clean"),
    ("propname.ui", "refuse"),
    ("res.ui", "reader"),
    ("res_wellformed.ui", "refuse"),
    ("set.ui", "refuse"),
    ("strval.ui", "clean"),
    ("tabstop.ui", "drop"),
    ("wclass.ui", "refuse"),
)


def _scope(path: Path) -> FormScope:
    stem = path.stem
    return FormScope(
        kind="project",
        ui_path=str(path),
        project_root=str(path.parent),
        generated_path=str(path.with_name("ui_%s.py" % stem)),
        window_path=str(path.with_name("%s_window.py" % stem)),
        module_name="forms.ui_%s" % stem,
    )


def _idents(text: str) -> set:
    tree = ast.parse(text, feature_version=(3, 9))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.alias):
            names.add(node.name)
            if node.asname:
                names.add(node.asname)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
    return names


def _allowlist() -> set:
    base = (_DIR / "base.tmpl").read_text(encoding="utf-8")
    path = _DIR / "base.ui"
    document = read_ui(base, allocator=IdAllocator()).document
    scope = _scope(path)
    result = generate_form_module(document, scope=scope, source_bytes=base.encode("utf-8"))
    assert result.text is not None
    return _idents(result.text) | set(_EXTRA)


def _generate(filename: str):
    path = _DIR / filename
    text = path.read_text(encoding="utf-8")
    document = read_ui(text, allocator=IdAllocator()).document
    return generate_form_module(document, scope=_scope(path), source_bytes=text.encode("utf-8"))


@pytest.mark.parametrize("filename,outcome", _CASES)
def test_injection_site_does_not_become_python(filename: str, outcome: str) -> None:
    path = _DIR / filename
    text = path.read_text(encoding="utf-8")
    if outcome == "reader":
        with pytest.raises(UiReadError):
            read_ui(text, allocator=IdAllocator())
        return
    result = _generate(filename)
    if outcome == "refuse":
        assert result.text is None
        assert any(
            item.code == "FB502" and item.severity is Severity.ERROR for item in result.diagnostics
        )
        return
    assert result.text is not None
    extra = _idents(result.text) - _allowlist()
    assert not extra
    if outcome == "drop":
        assert any(
            item.code == "FB502" and item.severity is Severity.WARNING for item in result.diagnostics
        )


def test_newline_in_the_ui_basename_is_not_a_module() -> None:
    ui = '<?xml version="1.0" encoding="UTF-8"?><ui version="4.0"><class>Form</class><widget class="QWidget" name="Form"/><resources/><connections/></ui>'
    document = read_ui(ui, allocator=IdAllocator()).document
    scope = FormScope(
        kind="project",
        ui_path="/proj/forms/ok.ui\nimport os",
        project_root="/proj",
        generated_path="/proj/forms/ui_ok.py",
        window_path="/proj/forms/ok_window.py",
        module_name="forms.ui_ok",
    )
    result = generate_form_module(document, scope=scope, source_bytes=ui.encode("utf-8"))
    assert result.text is None
    assert any(item.code == "FB507" for item in result.diagnostics)


def test_window_class_refuses_a_class_that_is_not_a_cpp_name() -> None:
    text = (_DIR / "cls.ui").read_text(encoding="utf-8")
    document = read_ui(text, allocator=IdAllocator()).document
    with pytest.raises(ValueError):
        render_window_class(document, scope=_scope(_DIR / "cls.ui"))
