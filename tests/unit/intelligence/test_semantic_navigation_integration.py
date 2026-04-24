"""Integration tests for semantic navigation service cutover."""
from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from app.intelligence.navigation_service import lookup_definition_with_cache
from app.intelligence.reference_service import find_references

pytestmark = pytest.mark.unit

FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "semantic"


def _copy_fixture(tmp_path: Path, fixture_name: str) -> Path:
    source = FIXTURES_ROOT / fixture_name
    target = tmp_path / fixture_name
    shutil.copytree(source, target)
    return target


def test_lookup_definition_with_cache_resolves_imported_symbol_from_source_context(tmp_path: Path) -> None:
    project_root = _copy_fixture(tmp_path, "imported_project")
    consumer_path = (project_root / "consumer.py").resolve()
    source = consumer_path.read_text(encoding="utf-8")

    result = lookup_definition_with_cache(
        project_root=str(project_root.resolve()),
        current_file_path=str(consumer_path),
        symbol_name="helper",
        cache_db_path=str((tmp_path / "state" / "symbols.sqlite3").resolve()),
        source_text=source,
        cursor_position=source.rfind("helper") + 2,
    )

    assert result.found is True
    assert result.metadata.source == "semantic"
    assert result.locations[0].file_path == str((project_root / "lib.py").resolve())


def test_find_references_uses_semantic_binding_identity(tmp_path: Path) -> None:
    project_root = _copy_fixture(tmp_path, "shadowing_project")
    main_path = (project_root / "main.py").resolve()
    source = main_path.read_text(encoding="utf-8")

    result = find_references(
        project_root=str(project_root.resolve()),
        current_file_path=str(main_path),
        source_text=source,
        cursor_position=source.index("calculate(1)") + 2,
    )

    assert result.metadata.source == "semantic"
    assert result.found is True
    assert all(not hit.file_path.endswith("unrelated.py") for hit in result.hits)
