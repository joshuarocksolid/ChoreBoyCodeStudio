"""Integration timing checks for baseline responsiveness thresholds."""

from __future__ import annotations

import json
from pathlib import Path
import time

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication

from app.editors.editor_manager import EditorManager
from app.editors.search_panel import find_in_files
from app.project.project_service import create_blank_project, open_project
from app.shell.main_window import MainWindow

pytestmark = [pytest.mark.integration, pytest.mark.performance, pytest.mark.timeout(120)]


def _write_project_manifest(project_root: Path, name: str) -> None:
    (project_root / "cbcs").mkdir(parents=True, exist_ok=True)
    (project_root / "cbcs" / "project.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": name,
                "default_entry": "run.py",
                "working_directory": ".",
            }
        ),
        encoding="utf-8",
    )


def _ensure_qapplication(monkeypatch: pytest.MonkeyPatch) -> QApplication:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    import PySide2.QtGui as qt_gui
    import PySide2.QtWidgets as qt_widgets

    if not hasattr(qt_widgets, "QActionGroup"):
        qt_widgets.QActionGroup = qt_gui.QActionGroup  # type: ignore[attr-defined]

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _stub_background_project_open(window: MainWindow) -> None:
    window._start_symbol_indexing = lambda _project_root, exclude_patterns=None: None  # type: ignore[method-assign]
    test_runner_workflow = getattr(window, "_test_runner_workflow", None)
    if test_runner_workflow is not None:
        test_runner_workflow.refresh_discovery = lambda: None  # type: ignore[method-assign]


def _populate_vendor_tree(vendor_dir: Path, file_count: int) -> None:
    vendor_dir.mkdir(parents=True, exist_ok=True)
    per_package = max(1, file_count // 5)
    for package_index in range(5):
        package_dir = vendor_dir / f"pkg{package_index:02d}"
        package_dir.mkdir(parents=True, exist_ok=True)
        for file_index in range(per_package):
            (package_dir / f"mod_{file_index:05d}.py").write_text("def f() -> None:\n    pass\n", encoding="utf-8")


def test_open_project_500_files_under_one_second(tmp_path: Path) -> None:
    """Opening a medium project should remain within baseline threshold."""
    project_root = tmp_path / "medium_project"
    project_root.mkdir(parents=True)
    _write_project_manifest(project_root, "medium_project")
    for index in range(500):
        (project_root / f"file_{index:03d}.py").write_text(f"print({index})\n", encoding="utf-8")

    start = time.perf_counter()
    loaded_project = open_project(project_root)
    elapsed = time.perf_counter() - start

    assert len(loaded_project.entries) >= 500
    assert elapsed <= 1.0


def test_full_project_open_vendor_heavy_under_threshold(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Full shell open should stay fast when vendor/ is excluded by default."""
    _ensure_qapplication(monkeypatch)
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    project_root = tmp_path / "vendor_heavy_project"
    create_blank_project(str(project_root.resolve()), project_name="Vendor Heavy")
    _populate_vendor_tree(project_root / "vendor", 5000)

    window = MainWindow(state_root=str(state_root.resolve()))
    _stub_background_project_open(window)

    start = time.perf_counter()
    assert window._open_project_by_path(str(project_root.resolve())) is True
    elapsed = time.perf_counter() - start

    assert window._loaded_project is not None
    assert len(window._loaded_project.entries) <= 50
    assert elapsed <= 0.4


def test_open_2000_loc_file_under_250ms(tmp_path: Path) -> None:
    """Opening a large script should be near-instant for editor manager."""
    file_path = tmp_path / "large.py"
    file_path.write_text("\n".join(f"print({index})" for index in range(2000)), encoding="utf-8")
    manager = EditorManager()

    start = time.perf_counter()
    opened = manager.open_file(str(file_path))
    elapsed = time.perf_counter() - start

    assert opened.was_already_open is False
    assert elapsed <= 0.25


def test_find_in_files_500_files_first_results_under_1_5s(tmp_path: Path) -> None:
    """Project-wide search should return first chunk quickly."""
    project_root = tmp_path / "search_project"
    project_root.mkdir(parents=True)
    _write_project_manifest(project_root, "search_project")
    for index in range(500):
        content = "target\n" if index == 0 else f"line {index}\n"
        (project_root / f"file_{index:03d}.py").write_text(content, encoding="utf-8")

    start = time.perf_counter()
    matches = find_in_files(project_root, "target", max_results=10)
    elapsed = time.perf_counter() - start

    assert matches
    assert elapsed <= 1.5
