"""Integration performance checks for semantic intelligence warm paths."""
from __future__ import annotations

from pathlib import Path
import shutil
import time

import pytest

from app.intelligence.semantic_facade import SemanticFacade

pytestmark = pytest.mark.integration

FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "semantic"


def _copy_fixture(tmp_path: Path, fixture_name: str) -> Path:
    source = FIXTURES_ROOT / fixture_name
    target = tmp_path / fixture_name
    shutil.copytree(source, target)
    return target


def test_semantic_intelligence_warm_paths_stay_bounded(tmp_path: Path) -> None:
    project_root = _copy_fixture(tmp_path, "imported_project")
    state_root = (tmp_path / "state").resolve()
    state_root.mkdir(parents=True, exist_ok=True)
    facade = SemanticFacade(
        cache_db_path=str((state_root / "symbols.sqlite3").resolve()),
        state_root=str(state_root),
    )
    consumer_path = (project_root / "consumer.py").resolve()
    source = consumer_path.read_text(encoding="utf-8")
    helper_cursor = source.rfind("helper") + 2
    signature_cursor = source.index("compact=True") + len("compact=")

    # Warm up the project/session before measuring.
    facade.lookup_definition(
        project_root=str(project_root.resolve()),
        current_file_path=str(consumer_path),
        source_text=source,
        cursor_position=helper_cursor,
    )
    facade.complete(
        project_root=str(project_root.resolve()),
        current_file_path=str(consumer_path),
        source_text=source,
        cursor_position=helper_cursor,
        trigger_is_manual=True,
        min_prefix_chars=1,
        max_results=20,
    )

    completion_ms = _measure_ms(
        lambda: facade.complete(
            project_root=str(project_root.resolve()),
            current_file_path=str(consumer_path),
            source_text=source,
            cursor_position=helper_cursor,
            trigger_is_manual=True,
            min_prefix_chars=1,
            max_results=20,
        )
    )
    definition_ms = _measure_ms(
        lambda: facade.lookup_definition(
            project_root=str(project_root.resolve()),
            current_file_path=str(consumer_path),
            source_text=source,
            cursor_position=helper_cursor,
        )
    )
    signature_ms = _measure_ms(
        lambda: facade.resolve_signature_help(
            project_root=str(project_root.resolve()),
            current_file_path=str(consumer_path),
            source_text=source,
            cursor_position=signature_cursor,
        )
    )
    references_ms = _measure_ms(
        lambda: facade.find_references(
            project_root=str(project_root.resolve()),
            current_file_path=str(consumer_path),
            source_text=source,
            cursor_position=helper_cursor,
        )
    )
    rename_ms = _measure_ms(
        lambda: facade.plan_rename(
            project_root=str(project_root.resolve()),
            current_file_path=str(consumer_path),
            source_text=source,
            cursor_position=helper_cursor,
            new_symbol="renamed_helper",
        )
    )

    assert completion_ms <= 500.0
    assert definition_ms <= 600.0
    assert signature_ms <= 600.0
    assert references_ms <= 1500.0
    assert rename_ms <= 2500.0


def _measure_ms(callback) -> float:  # type: ignore[no-untyped-def]
    timings: list[float] = []
    for _ in range(5):
        started_at = time.perf_counter()
        callback()
        timings.append((time.perf_counter() - started_at) * 1000.0)
    return max(timings)
