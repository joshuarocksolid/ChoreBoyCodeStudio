"""Generated Python buffers are recognized without the form builder."""

from __future__ import annotations

import pytest

from app.editors.generated_file import excluded_from_lint, generated_banner, is_generated_module

pytestmark = pytest.mark.unit


_HEADER = "## Generated from invoice.ui by ChoreBoy Code Studio\n"


def test_ui_module_banner_names_the_form_and_the_window() -> None:
    banner = generated_banner("/work/ui_invoice.py", _HEADER)
    assert banner is not None
    assert banner.message == (
        "Generated from invoice.ui. Code Studio rewrites this file every time the form is saved. "
        "Put your code in invoice_window.py."
    )
    assert banner.source_path.endswith("invoice.ui")
    assert banner.logic_path.endswith("invoice_window.py")


def test_resource_module_banner_names_the_qrc() -> None:
    banner = generated_banner(
        "/work/icons_rc.py",
        "## Generated from icons.qrc by ChoreBoy Code Studio\n",
    )
    assert banner is not None
    assert "icons.qrc" in banner.message
    assert banner.logic_path == ""


def test_ui_helpers_without_a_form_or_header_is_ordinary_source(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "ui_helpers.py"
    path.write_text("def label(text):\n    return text\n", encoding="utf-8")
    text = path.read_text(encoding="utf-8")
    assert generated_banner(str(path), text) is None
    assert not excluded_from_lint(str(path), text)
    assert not is_generated_module(str(path), text)


def test_a_sibling_form_marks_the_module_generated(tmp_path) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "invoice.ui").write_text("<ui/>\n", encoding="utf-8")
    path = tmp_path / "ui_invoice.py"
    path.write_text("x = 1\n", encoding="utf-8")
    assert is_generated_module(str(path), "")
    banner = generated_banner(str(path), "")
    assert banner is not None
    assert banner.source_path.endswith("invoice.ui")


def test_generated_and_metadata_paths_are_left_out_of_lint() -> None:
    assert not excluded_from_lint("/work/ui_invoice.py")
    assert not excluded_from_lint("/work/icons_rc.py")
    assert excluded_from_lint("/work/cbcs/form_builder/hand_edits/ui_invoice.py")
    assert excluded_from_lint("/work/window.py", _HEADER)
    assert not excluded_from_lint("/work/invoice_window.py", "def open():\n    return None\n")
    assert is_generated_module("/work/window.py", _HEADER)
    assert not is_generated_module("/work/ui_invoice.py", "")


def test_a_markdown_file_quoting_the_header_stays_editable() -> None:
    assert not is_generated_module("/work/notes.md", "Saved forms start with:\n\n" + _HEADER)
    assert generated_banner("/work/notes.md", _HEADER) is None


def test_the_header_counts_only_at_the_start_of_the_file() -> None:
    late = "x = 1\n" * 200 + _HEADER
    assert not is_generated_module("/work/report.py", late)
    assert is_generated_module("/work/report.py", _HEADER + "x = 1\n" * 200)
