"""Unit tests for Markdown preview helper behavior."""

from __future__ import annotations

import pytest

from app.editors.markdown_rendering import (
    LINK_KIND_ANCHOR,
    LINK_KIND_EXTERNAL,
    LINK_KIND_LOCAL_FILE,
    LINK_KIND_MISSING,
    is_markdown_path,
    resolve_markdown_link,
)

pytestmark = pytest.mark.unit


def test_is_markdown_path_matches_supported_extensions() -> None:
    assert is_markdown_path("README.md")
    assert is_markdown_path("guide.MARKDOWN")
    assert is_markdown_path("notes.mkd")
    assert is_markdown_path("component.mdx")
    assert not is_markdown_path("main.py")


def test_resolve_anchor_link() -> None:
    resolved = resolve_markdown_link("/tmp/README.md", "#usage")

    assert resolved.kind == LINK_KIND_ANCHOR
    assert resolved.anchor == "usage"


def test_resolve_external_link() -> None:
    resolved = resolve_markdown_link("/tmp/README.md", "https://example.com/docs")

    assert resolved.kind == LINK_KIND_EXTERNAL


def test_resolve_relative_local_file(tmp_path) -> None:  # type: ignore[no-untyped-def]
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    readme = docs_dir / "README.md"
    target = docs_dir / "guide.md"
    readme.write_text("[guide](guide.md)", encoding="utf-8")
    target.write_text("# Guide", encoding="utf-8")

    resolved = resolve_markdown_link(str(readme), "guide.md")

    assert resolved.kind == LINK_KIND_LOCAL_FILE
    assert resolved.target_path == str(target.resolve())


def test_resolve_missing_relative_file(tmp_path) -> None:  # type: ignore[no-untyped-def]
    readme = tmp_path / "README.md"
    readme.write_text("[missing](missing.md)", encoding="utf-8")

    resolved = resolve_markdown_link(str(readme), "missing.md#section")

    assert resolved.kind == LINK_KIND_MISSING
    assert resolved.anchor == "section"
