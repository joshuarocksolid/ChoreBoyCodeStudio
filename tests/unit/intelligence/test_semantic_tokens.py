"""Unit tests for tree-sitter language resolution contracts."""

from __future__ import annotations

import pytest

from app.treesitter.language_registry import TreeSitterLanguageRegistry

pytestmark = pytest.mark.unit


def test_resolve_for_path_uses_extension_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = TreeSitterLanguageRegistry()
    sentinel = object()
    monkeypatch.setattr(registry, "_language_for_key", lambda _key: sentinel)
    monkeypatch.setattr(registry, "_query_source_for_key", lambda key: f"query:{key}")

    resolved = registry.resolve_for_path(file_path="/tmp/main.py", sample_text="")

    assert resolved == ("python", sentinel, "query:python")


def test_resolve_for_path_sniffs_python_shebang(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = TreeSitterLanguageRegistry()
    sentinel = object()
    monkeypatch.setattr(registry, "_language_for_key", lambda _key: sentinel)
    monkeypatch.setattr(registry, "_query_source_for_key", lambda key: f"query:{key}")

    resolved = registry.resolve_for_path(
        file_path="/tmp/script",
        sample_text="#!/usr/bin/env python3\nprint('ok')\n",
    )

    assert resolved == ("python", sentinel, "query:python")


def test_resolve_for_path_sniffs_markdown_basename(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = TreeSitterLanguageRegistry()
    sentinel = object()
    monkeypatch.setattr(registry, "_language_for_key", lambda _key: sentinel)
    monkeypatch.setattr(registry, "_query_source_for_key", lambda key: f"query:{key}")

    resolved = registry.resolve_for_path(file_path="/tmp/CHANGELOG", sample_text="")

    assert resolved == ("markdown", sentinel, "query:markdown")


def test_resolve_for_path_fcmacro_extension(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = TreeSitterLanguageRegistry()
    sentinel = object()
    monkeypatch.setattr(registry, "_language_for_key", lambda _key: sentinel)
    monkeypatch.setattr(registry, "_query_source_for_key", lambda key: f"query:{key}")

    resolved = registry.resolve_for_path(file_path="/tmp/my_macro.FCMacro", sample_text="")

    assert resolved == ("python", sentinel, "query:python")


def test_resolve_for_path_returns_none_when_sniff_fails() -> None:
    registry = TreeSitterLanguageRegistry()

    resolved = registry.resolve_for_path(file_path="/tmp/blob.bin", sample_text="opaque data")

    assert resolved is None
