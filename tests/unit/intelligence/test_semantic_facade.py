"""Unit tests for trusted semantic facade behavior."""
from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from app.intelligence.semantic_facade import SemanticFacade

pytestmark = pytest.mark.unit

FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "semantic"


def _copy_fixture(tmp_path: Path, fixture_name: str) -> Path:
    source = FIXTURES_ROOT / fixture_name
    target = tmp_path / fixture_name
    shutil.copytree(source, target)
    return target


def _build_facade(tmp_path: Path) -> SemanticFacade:
    state_root = (tmp_path / "state").resolve()
    state_root.mkdir(parents=True, exist_ok=True)
    cache_db_path = state_root / "symbols.sqlite3"
    return SemanticFacade(cache_db_path=str(cache_db_path), state_root=str(state_root))


def test_lookup_definition_resolves_imported_symbol_semantically(tmp_path: Path) -> None:
    project_root = _copy_fixture(tmp_path, "imported_project")
    facade = _build_facade(tmp_path)
    consumer_path = (project_root / "consumer.py").resolve()
    source = consumer_path.read_text(encoding="utf-8")

    result = facade.lookup_definition(
        project_root=str(project_root.resolve()),
        current_file_path=str(consumer_path),
        source_text=source,
        cursor_position=source.rfind("helper") + 2,
    )

    assert result.found is True
    assert result.metadata.source == "semantic"
    assert result.metadata.confidence == "exact"
    assert result.locations[0].file_path == str((project_root / "lib.py").resolve())


def test_lookup_definition_prefers_shadowed_local_binding(tmp_path: Path) -> None:
    project_root = _copy_fixture(tmp_path, "shadowing_project")
    facade = _build_facade(tmp_path)
    main_path = (project_root / "main.py").resolve()
    source = main_path.read_text(encoding="utf-8")

    result = facade.lookup_definition(
        project_root=str(project_root.resolve()),
        current_file_path=str(main_path),
        source_text=source,
        cursor_position=source.index("calculate(1)") + 2,
    )

    assert result.found is True
    assert result.locations[0].file_path == str(main_path)
    assert result.locations[0].line_number == 4


def test_find_references_excludes_unrelated_homonyms(tmp_path: Path) -> None:
    project_root = _copy_fixture(tmp_path, "shadowing_project")
    facade = _build_facade(tmp_path)
    main_path = (project_root / "main.py").resolve()
    source = main_path.read_text(encoding="utf-8")

    result = facade.find_references(
        project_root=str(project_root.resolve()),
        current_file_path=str(main_path),
        source_text=source,
        cursor_position=source.index("calculate(1)") + 2,
    )

    assert result.metadata.source == "semantic"
    assert result.found is True
    assert all(not hit.file_path.endswith("unrelated.py") for hit in result.hits)
    assert any(hit.file_path.endswith("main.py") and hit.is_definition for hit in result.hits)


def test_completion_resolves_vendored_module_members(tmp_path: Path) -> None:
    project_root = _copy_fixture(tmp_path, "vendor_project")
    facade = _build_facade(tmp_path)
    source = "import vendored_lib\nvendored_lib."

    items = facade.complete(
        project_root=str(project_root.resolve()),
        current_file_path=str((project_root / "main.py").resolve()),
        source_text=source,
        cursor_position=len(source),
        trigger_is_manual=True,
        min_prefix_chars=1,
        max_results=20,
    )

    candidate = next(item for item in items if item.insert_text == "vendored_helper")
    assert candidate.source == "semantic"
    assert candidate.confidence == "exact"


def test_hover_and_signature_use_imported_definition_metadata(tmp_path: Path) -> None:
    project_root = _copy_fixture(tmp_path, "imported_project")
    facade = _build_facade(tmp_path)
    consumer_path = (project_root / "consumer.py").resolve()
    source = consumer_path.read_text(encoding="utf-8")

    hover = facade.resolve_hover_info(
        project_root=str(project_root.resolve()),
        current_file_path=str(consumer_path),
        source_text=source,
        cursor_position=source.rfind("helper") + 2,
    )
    signature = facade.resolve_signature_help(
        project_root=str(project_root.resolve()),
        current_file_path=str(consumer_path),
        source_text=source,
        cursor_position=source.index("compact=True") + len("compact="),
    )

    assert hover is not None
    assert hover.source == "semantic"
    assert hover.doc_summary == "Build report summary."
    assert signature is not None
    assert signature.source == "semantic"
    assert signature.signature_text == "helper(name, *, compact=False)"


def test_lookup_definition_handles_package_reexports(tmp_path: Path) -> None:
    project_root = _copy_fixture(tmp_path, "reexport_project")
    facade = _build_facade(tmp_path)
    main_path = (project_root / "main.py").resolve()
    source = main_path.read_text(encoding="utf-8")

    result = facade.lookup_definition(
        project_root=str(project_root.resolve()),
        current_file_path=str(main_path),
        source_text=source,
        cursor_position=source.rfind("package_helper") + 2,
    )

    assert result.found is True
    assert result.locations[0].file_path == str((project_root / "pkg" / "helpers.py").resolve())


def test_signature_help_survives_syntax_broken_buffer(tmp_path: Path) -> None:
    project_root = _copy_fixture(tmp_path, "imported_project")
    facade = _build_facade(tmp_path)
    source = "from lib import helper\nif True:\n    broken =\nhelper("

    signature = facade.resolve_signature_help(
        project_root=str(project_root.resolve()),
        current_file_path=str((project_root / "consumer.py").resolve()),
        source_text=source,
        cursor_position=len(source),
    )

    assert signature is not None
    assert signature.signature_text.startswith("helper(")


def test_dynamic_code_returns_explicit_degradation_reason(tmp_path: Path) -> None:
    project_root = _copy_fixture(tmp_path, "dynamic_project")
    facade = _build_facade(tmp_path)
    main_path = (project_root / "main.py").resolve()
    source = main_path.read_text(encoding="utf-8")

    result = facade.lookup_definition(
        project_root=str(project_root.resolve()),
        current_file_path=str(main_path),
        source_text=source,
        cursor_position=source.index("dynamic_value") + 2,
    )

    assert result.found is False
    assert result.metadata.source == "semantic"
    assert result.metadata.unsupported_reason != ""
