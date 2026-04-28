"""Integration timing checks for completion latency budgets."""

from __future__ import annotations

from pathlib import Path
import statistics
import time

import pytest

from app.intelligence.completion_service import CompletionRequest, CompletionService

pytestmark = [pytest.mark.integration, pytest.mark.performance, pytest.mark.timeout(120)]


def _request(source: str, tmp_path: Path) -> CompletionRequest:
    return CompletionRequest(
        source_text=source,
        cursor_position=len(source),
        current_file_path=str(tmp_path / "main.py"),
        project_root=None,
        trigger_is_manual=False,
        min_prefix_chars=2,
    )


def test_pyside_import_fast_completion_warm_p95_under_75ms(tmp_path: Path) -> None:
    service = CompletionService(cache_db_path=str(tmp_path / "symbols.sqlite3"))
    request = _request("from PySide2 import QtWi", tmp_path)
    service.complete_fast(request)
    durations: list[float] = []

    for _ in range(20):
        started_at = time.perf_counter()
        envelope = service.complete_fast(request)
        durations.append((time.perf_counter() - started_at) * 1000.0)
        assert any(item.label == "QtWidgets" for item in envelope.items)

    p95 = statistics.quantiles(durations, n=20)[18]
    assert p95 <= 75.0


def test_result_reuse_for_rapid_typing_under_20ms(tmp_path: Path) -> None:
    service = CompletionService(cache_db_path=str(tmp_path / "symbols.sqlite3"))
    first = _request("from PySide2 import QtW", tmp_path)
    second = _request("from PySide2 import QtWi", tmp_path)
    service.complete_fast(first)

    started_at = time.perf_counter()
    envelope = service.complete_fast(second)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0

    assert envelope.source_phase == "reuse"
    assert [item.label for item in envelope.items] == ["QtWidgets"]
    assert elapsed_ms <= 20.0
