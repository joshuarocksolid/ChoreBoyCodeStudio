"""AST-validated debugger expression evaluation."""

from __future__ import annotations

import ast
from typing import Any, Mapping

_MAX_EXPRESSION_LENGTH = 500
_ALLOWED_NODES = (
    ast.Expression,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.Attribute,
    ast.Subscript,
    ast.Slice,
    ast.Tuple,
    ast.List,
    ast.Dict,
    ast.UnaryOp,
    ast.UAdd,
    ast.USub,
    ast.Not,
    ast.BinOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Is,
    ast.IsNot,
    ast.In,
    ast.NotIn,
)


class UnsafeExpressionError(ValueError):
    """Raised when a debugger expression is outside the safe read-only subset."""


def safe_evaluate_expression(
    expression: str,
    globals_mapping: Mapping[str, Any],
    locals_mapping: Mapping[str, Any],
) -> Any:
    """Evaluate a read-only debugger expression after AST validation."""
    normalized = expression.strip()
    if not normalized:
        raise UnsafeExpressionError("Expression cannot be empty.")
    if len(normalized) > _MAX_EXPRESSION_LENGTH:
        raise UnsafeExpressionError("Expression is too long for safe evaluation.")
    try:
        tree = ast.parse(normalized, mode="eval")
    except SyntaxError as exc:
        raise UnsafeExpressionError(exc.msg) from exc
    _validate_tree(tree)
    code = compile(tree, "<debug-evaluate>", "eval")
    return eval(code, {"__builtins__": {}, **dict(globals_mapping)}, dict(locals_mapping))  # noqa: S307


def _validate_tree(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise UnsafeExpressionError(f"Unsupported expression element: {type(node).__name__}.")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise UnsafeExpressionError("Dunder names are not allowed in safe debugger evaluation.")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise UnsafeExpressionError("Dunder attributes are not allowed in safe debugger evaluation.")
