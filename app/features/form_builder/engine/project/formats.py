"""Project format settings from the top-level ``formats`` object in ``cbcs/project.json``."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional, Tuple

from app.features.form_builder.engine.codegen.logic_hooks import FormatSettings
from app.features.form_builder.engine.project.adoption import manifest_path

_GROUPING = ("1,234.50", "1.234,50", "1 234.50", "1234.50")
_DATES = ("MM/DD/YYYY", "DD/MM/YYYY", "YYYY-MM-DD")


@dataclass(frozen=True)
class FormatExpr:
    """The expression a leave handler and a Value write both emit."""

    source: str
    helpers: Tuple[str, ...]
    imports: Tuple[Tuple[str, str], ...] = ()


def read_formats(project_root: Optional[str]) -> FormatSettings:
    """Top-level ``formats`` in ``cbcs/project.json``. Never raises.

    A missing root, file, key, or a bad JSON value returns US defaults. A bad
    field keeps that field's US default.
    """
    if not project_root:
        return FormatSettings()
    try:
        with open(manifest_path(project_root), encoding="utf-8") as handle:
            payload = json.loads(handle.read())
    except Exception:
        return FormatSettings()
    if not isinstance(payload, dict):
        return FormatSettings()
    block = payload.get("formats")
    if not isinstance(block, dict):
        return FormatSettings()
    currency = block.get("currency", "$")
    grouping = block.get("grouping", "1,234.50")
    date = block.get("date", "MM/DD/YYYY")
    if not isinstance(currency, str) or not 1 <= len(currency) <= 4:
        currency = "$"
    if grouping not in _GROUPING:
        grouping = "1,234.50"
    if date not in _DATES:
        date = "MM/DD/YYYY"
    return FormatSettings(currency=currency, grouping=grouping, date=date)


def format_expr(code: str, value_expr: str, settings: FormatSettings) -> Optional[FormatExpr]:
    """The helper call for ``code``. None when ``code`` is not a format this lane writes.

    US money and dates call the helper directly. A non-US currency or grouping is
    applied by the formats expander as replacements around that call.
    """
    del settings
    if code == "money":
        return FormatExpr("_cbcs_money(%s)" % value_expr, ("_cbcs_money",))
    if code == "number" or _numbered(code, "number:"):
        token = code if code != "number" else "number:2"
        return FormatExpr("_cbcs_text(%s, %r)" % (value_expr, token), ("_cbcs_text",))
    if code == "percent" or _numbered(code, "percent:"):
        token = "percent:0" if code == "percent" else code
        return FormatExpr("_cbcs_text(%s, %r)" % (value_expr, token), ("_cbcs_text",))
    if code in ("date:short", "date:long", "date:iso"):
        return FormatExpr("_cbcs_text(%s, %r)" % (value_expr, code), ("_cbcs_text",))
    if code in ("text:upper", "text:proper"):
        return FormatExpr("_cbcs_text(%s, %r)" % (value_expr, code), ("_cbcs_text",))
    return None


def _numbered(code: str, prefix: str) -> bool:
    if not code.startswith(prefix):
        return False
    rest = code[len(prefix) :]
    return bool(rest) and rest.isdigit()
