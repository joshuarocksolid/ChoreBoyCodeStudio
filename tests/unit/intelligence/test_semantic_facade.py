"""Unit tests for trusted semantic facade behavior."""
from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from app.intelligence.semantic_facade import SemanticFacade
from app.intelligence.semantic_models import (
    CONFIDENCE_EXACT,
    CONFIDENCE_UNSUPPORTED,
)

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


# ---------------------------------------------------------------------------
# Deep import chain tests (AT-45)
# ---------------------------------------------------------------------------


def test_lookup_definition_resolves_deep_import_chain(tmp_path: Path) -> None:
    """Definition through pkg/__init__.py → pkg/sub/inner.py lands on real source."""
    project_root = _copy_fixture(tmp_path, "deep_import_project")
    facade = _build_facade(tmp_path)
    main_path = (project_root / "main.py").resolve()
    source = main_path.read_text(encoding="utf-8")

    result = facade.lookup_definition(
        project_root=str(project_root.resolve()),
        current_file_path=str(main_path),
        source_text=source,
        cursor_position=source.index("deep_function(42)") + 2,
    )

    assert result.found is True
    assert result.metadata.confidence == CONFIDENCE_EXACT
    target_path = str((project_root / "pkg" / "sub" / "inner.py").resolve())
    assert result.locations[0].file_path == target_path


def test_hover_resolves_deep_import_chain(tmp_path: Path) -> None:
    """Hover on deeply nested re-export returns the correct docstring."""
    project_root = _copy_fixture(tmp_path, "deep_import_project")
    facade = _build_facade(tmp_path)
    main_path = (project_root / "main.py").resolve()
    source = main_path.read_text(encoding="utf-8")

    hover = facade.resolve_hover_info(
        project_root=str(project_root.resolve()),
        current_file_path=str(main_path),
        source_text=source,
        cursor_position=source.index("deep_function(42)") + 2,
    )

    assert hover is not None
    assert hover.source == "semantic"
    assert "integer" in hover.doc_summary.lower() or "tagged" in hover.doc_summary.lower()


# ---------------------------------------------------------------------------
# Broken-project resilience tests (AT-48)
# ---------------------------------------------------------------------------


def test_lookup_definition_works_from_file_importing_broken_module(tmp_path: Path) -> None:
    """Consumer importing from a syntax-broken peer still resolves its own import."""
    project_root = _copy_fixture(tmp_path, "broken_project")
    facade = _build_facade(tmp_path)
    consumer_path = (project_root / "consumer.py").resolve()
    source = consumer_path.read_text(encoding="utf-8")

    result = facade.lookup_definition(
        project_root=str(project_root.resolve()),
        current_file_path=str(consumer_path),
        source_text=source,
        cursor_position=source.index("working_function") + 2,
    )

    # Jedi should be able to resolve the import even if broken.py has errors
    assert result.found is True
    assert result.metadata.source == "semantic"


# ---------------------------------------------------------------------------
# Confidence metadata tests (AT-47)
# ---------------------------------------------------------------------------


def test_completion_metadata_marks_source_as_semantic(tmp_path: Path) -> None:
    """Completion items from Jedi carry 'semantic' source and 'exact' confidence."""
    project_root = _copy_fixture(tmp_path, "imported_project")
    facade = _build_facade(tmp_path)
    source = "from lib import helper\nhelper."

    items = facade.complete(
        project_root=str(project_root.resolve()),
        current_file_path=str((project_root / "consumer.py").resolve()),
        source_text=source,
        cursor_position=len(source),
        trigger_is_manual=True,
        min_prefix_chars=0,
        max_results=20,
    )

    # String methods should be available since helper returns strings
    assert len(items) > 0
    for item in items:
        assert item.source == "semantic"
        assert item.confidence == CONFIDENCE_EXACT


def test_definition_metadata_marks_exact_confidence(tmp_path: Path) -> None:
    """Successful definition result carries exact confidence."""
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

    assert result.metadata.engine == "jedi"
    assert result.metadata.source == "semantic"
    assert result.metadata.confidence == CONFIDENCE_EXACT
    assert result.metadata.latency_ms >= 0.0


# ---------------------------------------------------------------------------
# Rename planning tests (AT-49)
# ---------------------------------------------------------------------------


def test_plan_rename_produces_valid_preview_patches(tmp_path: Path) -> None:
    """Rename plan includes per-file preview patches and reference hits."""
    project_root = _copy_fixture(tmp_path, "imported_project")
    facade = _build_facade(tmp_path)
    lib_path = (project_root / "lib.py").resolve()
    source = lib_path.read_text(encoding="utf-8")

    plan = facade.plan_rename(
        project_root=str(project_root.resolve()),
        current_file_path=str(lib_path),
        source_text=source,
        cursor_position=source.index("helper") + 2,
        new_symbol="build_summary",
    )

    assert plan is not None
    assert plan.old_symbol == "helper"
    assert plan.new_symbol == "build_summary"
    assert len(plan.hits) > 0
    assert len(plan.preview_patches) > 0
    # At least lib.py and consumer.py should be touched
    touched_files = {Path(p.file_path).name for p in plan.preview_patches}
    assert "lib.py" in touched_files
    assert "consumer.py" in touched_files


def test_plan_rename_rejects_invalid_identifier(tmp_path: Path) -> None:
    """Rename plan returns None for invalid new symbol name."""
    project_root = _copy_fixture(tmp_path, "imported_project")
    facade = _build_facade(tmp_path)
    lib_path = (project_root / "lib.py").resolve()
    source = lib_path.read_text(encoding="utf-8")

    plan = facade.plan_rename(
        project_root=str(project_root.resolve()),
        current_file_path=str(lib_path),
        source_text=source,
        cursor_position=source.index("helper") + 2,
        new_symbol="not-valid-identifier",
    )

    assert plan is None


def test_plan_rename_raises_for_dynamic_symbol(tmp_path: Path) -> None:
    """Rename plan raises when target is dynamic/unresolvable.

    The facade should convert engine-specific errors into a clean ValueError
    so callers never need to catch Rope-specific exceptions.
    """
    project_root = _copy_fixture(tmp_path, "dynamic_project")
    facade = _build_facade(tmp_path)
    main_path = (project_root / "main.py").resolve()
    source = main_path.read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="[Ss]emantic rename"):
        facade.plan_rename(
            project_root=str(project_root.resolve()),
            current_file_path=str(main_path),
            source_text=source,
            cursor_position=source.index("dynamic_value") + 2,
            new_symbol="renamed_value",
        )
