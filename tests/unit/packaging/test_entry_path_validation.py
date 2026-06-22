"""Unit tests for packaging entry-path validation SSOT."""

from __future__ import annotations

import pytest

from app.packaging import launcher_bootstrap, layout

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("entry_path", "expected"),
    [
        ("main.py", "main.py"),
        ("pkg/module.py", "pkg/module.py"),
    ],
)
def test_validate_packaged_entry_relative_path_matches_between_layout_and_bootstrap(
    entry_path: str,
    expected: str,
) -> None:
    assert layout.validate_packaged_entry_relative_path(entry_path) == expected
    assert launcher_bootstrap.validate_packaged_entry_relative_path(entry_path) == expected


def test_validate_packaged_entry_relative_path_rejects_unsafe_values() -> None:
    with pytest.raises(ValueError, match="unsafe"):
        layout.validate_packaged_entry_relative_path('main"; rm -rf /')
    with pytest.raises(ValueError, match="unsafe"):
        launcher_bootstrap.validate_packaged_entry_relative_path('main"; rm -rf /')
