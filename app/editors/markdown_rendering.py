"""Markdown preview helpers for editor-integrated rendering."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


MARKDOWN_EXTENSIONS = frozenset({".md", ".markdown", ".mkd", ".mdx"})
MAX_LIVE_MARKDOWN_PREVIEW_CHARS = 300_000

LINK_KIND_ANCHOR = "anchor"
LINK_KIND_EXTERNAL = "external"
LINK_KIND_LOCAL_FILE = "local_file"
LINK_KIND_MISSING = "missing"
LINK_KIND_UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class ResolvedMarkdownLink:
    """Resolved target for a clicked Markdown preview link."""

    kind: str
    href: str
    target_path: str | None = None
    anchor: str | None = None


def is_markdown_path(file_path: str) -> bool:
    """Return whether a path should use the Markdown preview editor."""
    suffix = Path(file_path).suffix.lower()
    return suffix in MARKDOWN_EXTENSIONS


def qt_markdown_supported() -> bool:
    """Return whether the current PySide2 runtime exposes Qt Markdown APIs."""
    try:
        from PySide2.QtWidgets import QTextBrowser
    except ImportError:
        return False
    return hasattr(QTextBrowser, "setMarkdown")


def safe_markdown_features() -> Any | None:
    """Return Qt Markdown features that disable raw HTML when available."""
    try:
        from PySide2.QtGui import QTextDocument
    except ImportError:
        return None
    dialect = getattr(QTextDocument, "MarkdownDialectGitHub", None)
    no_html = getattr(QTextDocument, "MarkdownNoHTML", None)
    if dialect is None:
        return None
    if no_html is None:
        return dialect
    try:
        return dialect | no_html
    except TypeError:
        return int(dialect) | int(no_html)


def split_href_anchor(href: str) -> tuple[str, str | None]:
    """Split a Markdown href into path/URL and optional fragment."""
    before_hash, separator, after_hash = href.partition("#")
    anchor = unquote(after_hash) if separator else None
    return before_hash, anchor


def resolve_markdown_link(markdown_file_path: str, href: str) -> ResolvedMarkdownLink:
    """Resolve a Markdown link relative to its source file."""
    normalized_href = href.strip()
    if not normalized_href:
        return ResolvedMarkdownLink(kind=LINK_KIND_UNSUPPORTED, href=href)

    if normalized_href.startswith("#"):
        return ResolvedMarkdownLink(
            kind=LINK_KIND_ANCHOR,
            href=href,
            anchor=unquote(normalized_href[1:]),
        )

    parsed = urlparse(normalized_href)
    if parsed.scheme in {"http", "https", "mailto"}:
        return ResolvedMarkdownLink(kind=LINK_KIND_EXTERNAL, href=href)
    if parsed.scheme and parsed.scheme != "file":
        return ResolvedMarkdownLink(kind=LINK_KIND_UNSUPPORTED, href=href)

    path_part, anchor = split_href_anchor(normalized_href)
    if parsed.scheme == "file":
        target = Path(unquote(parsed.path)).expanduser()
    else:
        path_without_query = path_part.partition("?")[0]
        if not path_without_query:
            return ResolvedMarkdownLink(kind=LINK_KIND_ANCHOR, href=href, anchor=anchor)
        base_dir = Path(markdown_file_path).expanduser().resolve().parent
        target = base_dir / unquote(path_without_query)

    try:
        resolved = str(target.resolve())
    except OSError:
        resolved = str(target)

    if not target.exists():
        return ResolvedMarkdownLink(
            kind=LINK_KIND_MISSING,
            href=href,
            target_path=resolved,
            anchor=anchor,
        )
    return ResolvedMarkdownLink(
        kind=LINK_KIND_LOCAL_FILE,
        href=href,
        target_path=resolved,
        anchor=anchor,
    )
