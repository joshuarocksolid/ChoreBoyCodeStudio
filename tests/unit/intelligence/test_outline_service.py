"""Unit tests for hierarchical Python outline extraction."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.intelligence import outline_service
from app.intelligence.outline_service import (
    OutlineSymbol,
    build_file_outline,
    build_outline_from_source,
    find_innermost_symbol,
    flatten_symbols,
)

pytestmark = pytest.mark.unit


def test_build_outline_extracts_classes_and_functions_hierarchically() -> None:
    source = (
        "class Alpha:\n"
        "    def first(self):\n"
        "        return 1\n"
        "\n"
        "    def second(self):\n"
        "        return 2\n"
        "\n"
        "def standalone():\n"
        "    return 3\n"
    )
    outline = build_outline_from_source(source)

    assert [s.name for s in outline] == ["Alpha", "standalone"]
    assert outline[0].kind == "class"
    assert [c.name for c in outline[0].children] == ["first", "second"]
    assert all(c.kind == "method" for c in outline[0].children)
    assert outline[1].kind == "function"


def test_build_file_outline_returns_empty_for_non_python(tmp_path: Path) -> None:
    file_path = tmp_path / "README.md"
    file_path.write_text("# title\n", encoding="utf-8")
    assert build_file_outline(str(file_path)) == ()


def test_build_file_outline_reads_python_file(tmp_path: Path) -> None:
    file_path = tmp_path / "module.py"
    file_path.write_text("class A:\n    pass\n", encoding="utf-8")
    outline = build_file_outline(str(file_path))
    assert len(outline) == 1
    assert outline[0].name == "A"
    assert outline[0].kind == "class"


def test_async_function_kind() -> None:
    source = "async def fetch():\n    return 1\n"
    outline = build_outline_from_source(source)
    assert len(outline) == 1
    assert outline[0].kind == "async_function"
    assert outline[0].name == "fetch"


def test_async_method_kind_inside_class() -> None:
    source = (
        "class Service:\n"
        "    async def fetch(self):\n"
        "        return 1\n"
    )
    outline = build_outline_from_source(source)
    method = outline[0].children[0]
    assert method.kind == "async_method"


def test_property_decorator_recognized() -> None:
    source = (
        "class Thing:\n"
        "    @property\n"
        "    def value(self):\n"
        "        return self._value\n"
    )
    outline = build_outline_from_source(source)
    children = outline[0].children
    assert len(children) == 1
    assert children[0].kind == "property"
    assert children[0].name == "value"


def test_property_setter_merged_into_property_entry() -> None:
    source = (
        "class Thing:\n"
        "    @property\n"
        "    def value(self):\n"
        "        return self._value\n"
        "\n"
        "    @value.setter\n"
        "    def value(self, new):\n"
        "        self._value = new\n"
    )
    outline = build_outline_from_source(source)
    children = outline[0].children
    assert len(children) == 1
    assert children[0].kind == "property"
    assert children[0].end_line_number >= 7


def test_staticmethod_and_classmethod_get_detail_prefix() -> None:
    source = (
        "class Box:\n"
        "    @staticmethod\n"
        "    def make(x):\n"
        "        return Box()\n"
        "    @classmethod\n"
        "    def from_iter(cls, items):\n"
        "        return cls()\n"
    )
    outline = build_outline_from_source(source)
    methods = {child.name: child for child in outline[0].children}
    assert methods["make"].detail.startswith("static")
    assert methods["from_iter"].detail.startswith("class")


def test_module_level_constant_recognized() -> None:
    source = "FOO = 1\nbar = 2\n"
    outline = build_outline_from_source(source)
    names = [(s.name, s.kind) for s in outline]
    assert ("FOO", "constant") in names
    assert all(name != "bar" for name, _kind in names)


def test_imports_excluded() -> None:
    source = "import os\nfrom pathlib import Path\nclass A:\n    pass\n"
    outline = build_outline_from_source(source)
    assert [s.name for s in outline] == ["A"]


def test_nested_class_qualified_name() -> None:
    source = (
        "class Outer:\n"
        "    class Inner:\n"
        "        def method(self):\n"
        "            return 1\n"
    )
    outline = build_outline_from_source(source)
    inner = outline[0].children[0]
    assert inner.qualified_name == "Outer.Inner"
    assert inner.children[0].qualified_name == "Outer.Inner.method"


def test_class_field_recognized_for_annotated_assignment() -> None:
    source = (
        "class Config:\n"
        "    name: str = \"\"\n"
        "    value = 1\n"
    )
    outline = build_outline_from_source(source)
    field_names = [c.name for c in outline[0].children if c.kind == "field"]
    assert field_names == ["name"]


def test_class_slots_excluded_from_fields() -> None:
    source = (
        "class Compact:\n"
        "    __slots__: tuple = ()\n"
    )
    outline = build_outline_from_source(source)
    assert outline[0].children == ()


def test_syntax_error_partial_parse_returns_what_we_can() -> None:
    source = (
        "class Alpha:\n"
        "    def foo(self):\n"
        "        return 1\n"
        "\n"
        "def broken(\n"
    )
    outline = build_outline_from_source(source)
    names = [s.name for s in outline]
    assert "Alpha" in names


def test_empty_source_returns_empty_tuple() -> None:
    assert build_outline_from_source("") == ()


def test_function_detail_contains_parameters() -> None:
    source = "def foo(a, b, c=1):\n    return a\n"
    outline = build_outline_from_source(source)
    assert "a" in outline[0].detail
    assert outline[0].detail.startswith("(")


def test_class_detail_lists_base_classes() -> None:
    source = "class Child(Base, Mixin):\n    pass\n"
    outline = build_outline_from_source(source)
    assert "Base" in outline[0].detail
    assert "Mixin" in outline[0].detail


def test_find_innermost_symbol_returns_deepest_match() -> None:
    inner_method = OutlineSymbol(
        name="method",
        qualified_name="Outer.Inner.method",
        kind="method",
        line_number=4,
        end_line_number=5,
    )
    inner_cls = OutlineSymbol(
        name="Inner",
        qualified_name="Outer.Inner",
        kind="class",
        line_number=2,
        end_line_number=5,
        children=(inner_method,),
    )
    outer = OutlineSymbol(
        name="Outer",
        qualified_name="Outer",
        kind="class",
        line_number=1,
        end_line_number=5,
        children=(inner_cls,),
    )
    found = find_innermost_symbol((outer,), 4)
    assert found is inner_method


def test_find_innermost_symbol_returns_none_outside_any_symbol() -> None:
    sym = OutlineSymbol(
        name="foo",
        qualified_name="foo",
        kind="function",
        line_number=1,
        end_line_number=2,
    )
    assert find_innermost_symbol((sym,), 50) is None


def test_flatten_symbols_preserves_depth_first_order() -> None:
    method = OutlineSymbol(
        name="m",
        qualified_name="C.m",
        kind="method",
        line_number=2,
        end_line_number=3,
    )
    cls = OutlineSymbol(
        name="C",
        qualified_name="C",
        kind="class",
        line_number=1,
        end_line_number=3,
        children=(method,),
    )
    fn = OutlineSymbol(
        name="f",
        qualified_name="f",
        kind="function",
        line_number=4,
        end_line_number=5,
    )
    flat = flatten_symbols((cls, fn))
    assert [s.qualified_name for s in flat] == ["C", "C.m", "f"]


def test_build_outline_when_treesitter_unavailable_falls_back_to_ast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.treesitter.loader import TreeSitterRuntimeStatus

    unavailable = TreeSitterRuntimeStatus(False, "forced unavailable for test")
    monkeypatch.setattr(outline_service, "runtime_status", lambda: unavailable)
    monkeypatch.setattr(
        outline_service, "initialize_tree_sitter_runtime", lambda *a, **k: unavailable
    )

    source = (
        "class A:\n"
        "    def m(self):\n"
        "        return 1\n"
        "\n"
        "def f():\n"
        "    return 2\n"
    )
    outline = build_outline_from_source(source)
    names = [s.name for s in outline]
    assert "A" in names
    assert "f" in names


def test_ast_fallback_returns_empty_for_syntax_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.treesitter.loader import TreeSitterRuntimeStatus

    unavailable = TreeSitterRuntimeStatus(False, "forced unavailable for test")
    monkeypatch.setattr(outline_service, "runtime_status", lambda: unavailable)
    monkeypatch.setattr(
        outline_service, "initialize_tree_sitter_runtime", lambda *a, **k: unavailable
    )

    source = "def broken(\n"
    assert build_outline_from_source(source) == ()
