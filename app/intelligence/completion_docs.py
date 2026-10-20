"""Text for the completion docs pane: signatures, first paragraph, owner line.

Only user-facing facts are shown. Internal fields such as
``side_effect_risk``, ``source`` or ``confidence`` never reach the pane.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import List

from app.intelligence.completion_models import CompletionItem, CompletionKind

MAX_SIGNATURES = 3
SUMMARY_LIMIT = 400

_NOISE_DETAIL_PARTS = frozenset({"", "approximate", "semantic", "live runtime", "runtime", "static"})
_SIGNATURE_LINE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_.]*)\s*\((.*)\)\s*(->\s*.+)?$")
_QT_MODULE_PREFIX = re.compile(r"\b(?:PySide2|shiboken2)\.(?:Qt[A-Za-z]+\.)?")


@dataclass(frozen=True)
class CompletionDocs:
    signatures: tuple[str, ...]
    summary: str
    owner_line: str


def clean_signature(name: str, text: str) -> str:
    """Make one signature read like Python: no ``self``, no ``arg__1``, short Qt names."""

    text = text.strip()
    if not text:
        return ""
    if text.startswith("("):
        text = name + text
    text = re.sub(r"\(self(?:\s*,\s*)?", "(", text)
    text = re.sub(r"\barg__(\d+)\b", lambda found: "arg" + found.group(1), text)
    text = _QT_MODULE_PREFIX.sub("", text)
    text = re.sub(r",\s*/\s*\)", ")", text).replace("(/)", "()")
    return text.replace("typing.", "")


def first_paragraph(text: str) -> str:
    lines: List[str] = []
    for line in text.strip().splitlines():
        if not line.strip():
            if lines:
                break
            continue
        lines.append(line.strip())
    joined = " ".join(lines)
    if len(joined) > SUMMARY_LIMIT:
        return joined[: SUMMARY_LIMIT - 3].rstrip() + "..."
    return joined


def owner_line(item: CompletionItem) -> str:
    parts = [part.strip() for part in (item.detail or "").split("•")]
    kept = [part for part in parts if part.lower() not in _NOISE_DETAIL_PARTS]
    return " · ".join(kept)


def completion_docs(item: CompletionItem) -> CompletionDocs:
    """Build the docs pane text for ``item``."""

    signatures: List[str] = []
    for line in (item.signature or "").splitlines():
        cleaned = clean_signature(item.label, line)
        if cleaned and "(" in cleaned and cleaned not in signatures:
            signatures.append(cleaned)
    doc_lines = (item.documentation or "").strip().splitlines()
    while True:
        while doc_lines and not doc_lines[0].strip():
            doc_lines.pop(0)
        if not doc_lines or not _SIGNATURE_LINE.match(doc_lines[0]):
            break
        cleaned = clean_signature(item.label, doc_lines.pop(0))
        if cleaned not in signatures:
            signatures.append(cleaned)
    if len(signatures) > MAX_SIGNATURES:
        extra = len(signatures) - MAX_SIGNATURES
        signatures = signatures[:MAX_SIGNATURES] + ["(+{} more)".format(extra)]
    if not signatures and item.kind not in (CompletionKind.KEYWORD, CompletionKind.TEXT):
        signatures = [item.label]
    return CompletionDocs(
        signatures=tuple(signatures),
        summary=first_paragraph("\n".join(doc_lines)),
        owner_line=owner_line(item),
    )


__all__ = ["CompletionDocs", "clean_signature", "completion_docs", "first_paragraph", "owner_line"]
