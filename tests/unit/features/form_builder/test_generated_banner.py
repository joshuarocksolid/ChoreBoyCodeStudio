"""The editor's banner reader agrees with the banner codegen writes (CONTRACTS.md section 9.2)."""

from __future__ import annotations

import hashlib
from typing import Optional

import pytest

from app.editors.generated_banner import GeneratedBanner, read_generated_banner
from app.features.form_builder.engine.codegen.header import render_header, render_resource_header

pytestmark = pytest.mark.unit

_BODY = "from app.qt import QtWidgets\n\n\nclass Ui_Invoice(object):\n    pass\n"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _module(*, has_logic: bool) -> str:
    header = render_header(
        ui_file_name="invoice.ui",
        window_file_name="invoice_window.py",
        has_logic=has_logic,
        source_sha256=_sha("<ui/>"),
        body_sha256=_sha(_BODY),
    )
    return header + _BODY


_RESOURCE = render_resource_header(qrc_file_name="icons.qrc", body_sha256=_sha(_BODY)) + _BODY
_INVOICE = GeneratedBanner(kind="module", source_name="invoice.ui", window_name="invoice_window.py")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (_module(has_logic=True), _INVOICE),
        (_module(has_logic=False), _INVOICE),
        (_module(has_logic=False) + "\nprint('added by hand')\n", _INVOICE),
        (_RESOURCE, GeneratedBanner(kind="resource", source_name="icons.qrc", window_name="")),
        ("def helper():\n    return 1\n", None),
    ],
    ids=["module-with-logic", "module-without-logic", "hand-edited-module", "resource", "no-banner"],
)
def test_reads_the_banner_codegen_writes(text: str, expected: Optional[GeneratedBanner]) -> None:
    assert read_generated_banner(text) == expected
