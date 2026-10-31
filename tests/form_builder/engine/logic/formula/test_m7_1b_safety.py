"""Compiled formulas stay inside the expression allowlist."""

from __future__ import annotations

import ast
from typing import Optional, Set

import pytest

from tests.form_builder.engine.logic.formula.test_m7_1b_compile import iter_golden_sources
from tests.form_builder.engine.logic.formula.test_m7_1b_fuzz import fuzz_names, iter_fuzz_sources

_ALLOWED = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.IfExp,
    ast.Call,
    ast.Attribute,
    ast.Name,
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.Load,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.UAdd,
    ast.USub,
    ast.Not,
    ast.And,
    ast.Or,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
)
_ACCESSORS = {
    "text",
    "toPlainText",
    "value",
    "isChecked",
    "currentData",
    "currentText",
    "currentWidget",
}


def _parents(tree: ast.AST) -> dict:
    parent = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[child] = node
    return parent


def _allowed_attribute(node: ast.Attribute, self_name: str, parent: dict, allowed: set) -> bool:
    if isinstance(node.value, ast.Name) and node.value.id == self_name:
        if node.attr == "_form":
            method = parent.get(node)
            call = parent.get(method) if method is not None else None
            return (
                isinstance(method, ast.Attribute)
                and isinstance(call, ast.Call)
                and call.func is method
                and method.value is node
            )
        if node.attr.startswith("_") or node.attr not in allowed:
            return False
        return True
    if (
        isinstance(node.value, ast.Attribute)
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == self_name
    ):
        call = parent.get(node)
        if not (isinstance(call, ast.Call) and call.func is node):
            return False
        if node.value.attr == "_form":
            return True
        return (
            node.attr in _ACCESSORS
            and node.value.attr in allowed
            and not node.value.attr.startswith("_")
        )
    return False


def _allowed_call(node: ast.Call, self_name: str) -> bool:
    if node.keywords:
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "Decimal" or func.id.startswith("_cbcs_")
    if isinstance(func, ast.Attribute):
        if (
            isinstance(func.value, ast.Attribute)
            and isinstance(func.value.value, ast.Name)
            and func.value.value.id == self_name
        ):
            if func.value.attr == "_form":
                return True
            return func.attr in _ACCESSORS
    return False


def assert_safe(source: str, self_name: str = "self", allowed: Optional[Set[str]] = None) -> None:
    tree = ast.parse(source, mode="eval")
    parent = _parents(tree)
    names = set(allowed or ())
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED):
            raise AssertionError("%s is not allowed in %s" % (type(node).__name__, source))
        if isinstance(node, ast.Name):
            if node.id != self_name and node.id != "Decimal" and not node.id.startswith("_cbcs_"):
                raise AssertionError("name %s in %s" % (node.id, source))
            if not isinstance(node.ctx, ast.Load):
                raise AssertionError("name context in %s" % source)
        elif isinstance(node, ast.Attribute):
            if not _allowed_attribute(node, self_name, parent, names):
                raise AssertionError("attribute %s in %s" % (ast.dump(node), source))
        elif isinstance(node, ast.Call):
            if not _allowed_call(node, self_name):
                raise AssertionError("call %s in %s" % (ast.dump(node), source))


@pytest.mark.unit
def test_golden_sources_are_safe() -> None:
    count = 0
    for source, self_name, allowed in iter_golden_sources():
        assert_safe(source, self_name, allowed)
        count += 1
    assert count >= 150


@pytest.mark.unit
def test_fuzz_sources_are_safe() -> None:
    count = 0
    allowed = fuzz_names()
    for source in iter_fuzz_sources():
        assert_safe(source, "self", allowed)
        count += 1
    assert count == 40


@pytest.mark.unit
@pytest.mark.parametrize("source", ["self.__class__", "self._x", "self.w.__dict__"])
def test_hidden_and_dunder_attributes_are_rejected(source: str) -> None:
    with pytest.raises(AssertionError):
        assert_safe(source, "self", {"w", "qty"})
