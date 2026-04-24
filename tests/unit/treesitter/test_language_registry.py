"""Unit tests for tree-sitter language resolution contracts."""

from __future__ import annotations

import pytest

from app.treesitter.language_registry import TreeSitterLanguageRegistry

pytestmark = pytest.mark.unit


@pytest.fixture
def patched_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TreeSitterLanguageRegistry, object]:
    """Registry with stubbed grammar/query loaders to isolate resolution policy."""
    registry = TreeSitterLanguageRegistry()
    sentinel = object()
    monkeypatch.setattr(registry, "_language_for_key", lambda _key: sentinel)
    monkeypatch.setattr(
        registry,
        "_query_source_for_key",
        lambda *, language_key, query_file: f"{query_file}:{language_key}",
    )
    return registry, sentinel


@pytest.mark.parametrize(
    ("file_path", "sample_text", "expected_key"),
    [
        ("/tmp/main.py", "", "python"),
        ("/tmp/script", "#!/usr/bin/env python3\nprint('ok')\n", "python"),
        ("/tmp/CHANGELOG", "", "markdown"),
        ("/tmp/my_macro.FCMacro", "", "python"),
    ],
)
def test_resolve_for_path_resolves_known_inputs(
    patched_registry: tuple[TreeSitterLanguageRegistry, object],
    file_path: str,
    sample_text: str,
    expected_key: str,
) -> None:
    registry, sentinel = patched_registry

    resolved = registry.resolve_for_path(file_path=file_path, sample_text=sample_text)

    assert resolved is not None
    assert resolved.language_key == expected_key
    assert resolved.language is sentinel
    assert resolved.highlights_query_source == f"{expected_key}.scm:{expected_key}"


def test_resolve_for_path_returns_none_when_sniff_fails() -> None:
    registry = TreeSitterLanguageRegistry()

    resolved = registry.resolve_for_path(file_path="/tmp/blob.bin", sample_text="opaque data")

    assert resolved is None
