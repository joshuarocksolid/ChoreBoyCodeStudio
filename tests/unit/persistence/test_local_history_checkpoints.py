"""Unit tests for the local-history writer free functions.

The legacy version of this file hand-attached attributes to ``MainWindow.__new__``
to probe ``MainWindow._save_tab`` and ``MainWindow._record_local_history_transaction``.
That coupling has been replaced by the public seams in
``app.persistence.local_history_writer``; the persistence-pipeline behaviour is
exercised here against those free functions, and the GUI-coordination side of
``_save_tab`` is left to higher-level integration suites.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from app.persistence.local_history_store import LocalHistoryStore
from app.persistence.local_history_writer import (
    record_local_history_checkpoint,
    record_local_history_transaction,
    resolve_local_history_context,
)
from app.project.project_service import create_blank_project, open_project

pytestmark = pytest.mark.unit


def _setup_project(tmp_path: Path) -> tuple[LocalHistoryStore, str, str, Path]:
    state_root = tmp_path / "state"
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="History Writer Project")
    loaded_project = open_project(str(project_root.resolve()))
    history_store = LocalHistoryStore(state_root=state_root)
    return (
        history_store,
        loaded_project.metadata.project_id,
        loaded_project.project_root,
        project_root,
    )


def test_resolve_local_history_context_returns_none_when_project_missing(tmp_path: Path) -> None:
    file_path = str(tmp_path / "stray.py")

    assert resolve_local_history_context(file_path, project_id=None, project_root=None) == (
        None,
        None,
    )
    assert resolve_local_history_context(
        file_path, project_id="proj_x", project_root=None
    ) == (None, None)


def test_resolve_local_history_context_drops_files_outside_project_root(tmp_path: Path) -> None:
    project_root = tmp_path / "inside"
    project_root.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("noop\n", encoding="utf-8")

    project_id, resolved_root = resolve_local_history_context(
        str(outside),
        project_id="proj_x",
        project_root=str(project_root),
    )

    assert project_id is None
    assert resolved_root is None


def test_resolve_local_history_context_keeps_files_inside_project_root(tmp_path: Path) -> None:
    project_root = tmp_path / "inside"
    project_root.mkdir()
    nested = project_root / "pkg" / "module.py"
    nested.parent.mkdir()
    nested.write_text("noop\n", encoding="utf-8")

    project_id, resolved_root = resolve_local_history_context(
        str(nested),
        project_id="proj_x",
        project_root=str(project_root),
    )

    assert project_id == "proj_x"
    assert resolved_root == str(project_root.resolve())


def test_record_local_history_checkpoint_writes_single_entry(tmp_path: Path) -> None:
    history_store, project_id, project_root, project_dir = _setup_project(tmp_path)
    file_path = project_dir / "main.py"
    file_path.write_text("print('original')\n", encoding="utf-8")

    checkpoint = record_local_history_checkpoint(
        history_store,
        file_path=str(file_path),
        content="print('saved')\n",
        project_id=project_id,
        project_root=project_root,
        source="save",
    )

    assert checkpoint is not None
    checkpoints = history_store.list_checkpoints(
        str(file_path), project_id=project_id, project_root=project_root
    )
    assert len(checkpoints) == 1
    assert (
        history_store.load_checkpoint_content(checkpoints[0].revision_id) == "print('saved')\n"
    )


def test_record_local_history_checkpoint_returns_none_when_store_missing(tmp_path: Path) -> None:
    file_path = tmp_path / "main.py"
    file_path.write_text("noop\n", encoding="utf-8")

    result = record_local_history_checkpoint(
        None,
        file_path=str(file_path),
        content="noop\n",
        project_id="proj_x",
        project_root=str(tmp_path),
        source="save",
    )

    assert result is None


def test_record_local_history_checkpoint_logs_and_swallows_store_failures(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    class _FailingStore:
        def create_checkpoint(self, *_args, **_kwargs):
            raise RuntimeError("disk full")

    logger = logging.getLogger("test.local_history_writer")
    with caplog.at_level(logging.WARNING, logger=logger.name):
        result = record_local_history_checkpoint(
            _FailingStore(),  # type: ignore[arg-type]
            file_path=str(tmp_path / "main.py"),
            content="x\n",
            project_id="proj_x",
            project_root=str(tmp_path),
            source="save",
            logger=logger,
        )

    assert result is None
    assert any("Local history checkpoint failed" in record.message for record in caplog.records)


def test_record_local_history_checkpoint_logs_with_module_logger_when_logger_omitted(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Checkpoint persistence failures should remain observable without caller logging."""

    class _FailingStore:
        def create_checkpoint(self, *_args, **_kwargs):
            raise RuntimeError("disk full")

    with caplog.at_level(logging.WARNING, logger="app.persistence.local_history_writer"):
        result = record_local_history_checkpoint(
            _FailingStore(),  # type: ignore[arg-type]
            file_path=str(tmp_path / "main.py"),
            content="x\n",
            project_id="proj_x",
            project_root=str(tmp_path),
            source="save",
        )

    assert result is None
    assert any("Local history checkpoint failed" in record.message for record in caplog.records)


def test_record_local_history_transaction_groups_multi_file_entries(tmp_path: Path) -> None:
    history_store, project_id, project_root, project_dir = _setup_project(tmp_path)
    alpha = project_dir / "alpha.py"
    beta = project_dir / "beta.py"
    alpha.write_text("ALPHA = 1\n", encoding="utf-8")
    beta.write_text("BETA = 1\n", encoding="utf-8")

    record_local_history_transaction(
        history_store,
        {str(alpha): "ALPHA = 2\n", str(beta): "BETA = 2\n"},
        project_id=project_id,
        project_root=project_root,
        source="quick_fix",
        label="Apply Safe Fixes",
    )

    alpha_checkpoints = history_store.list_checkpoints(
        str(alpha), project_id=project_id, project_root=project_root
    )
    beta_checkpoints = history_store.list_checkpoints(
        str(beta), project_id=project_id, project_root=project_root
    )

    assert len(alpha_checkpoints) == 1
    assert len(beta_checkpoints) == 1
    assert alpha_checkpoints[0].transaction_id is not None
    assert alpha_checkpoints[0].transaction_id == beta_checkpoints[0].transaction_id
    assert alpha_checkpoints[0].label == "Apply Safe Fixes"


def test_record_local_history_transaction_skips_transaction_id_for_single_file(
    tmp_path: Path,
) -> None:
    history_store, project_id, project_root, project_dir = _setup_project(tmp_path)
    only = project_dir / "only.py"
    only.write_text("ONLY = 1\n", encoding="utf-8")

    record_local_history_transaction(
        history_store,
        {str(only): "ONLY = 2\n"},
        project_id=project_id,
        project_root=project_root,
        source="quick_fix",
        label="Apply Safe Fixes",
    )

    checkpoints = history_store.list_checkpoints(
        str(only), project_id=project_id, project_root=project_root
    )
    assert len(checkpoints) == 1
    assert checkpoints[0].transaction_id is None


def test_record_local_history_transaction_ignores_empty_payload_map(tmp_path: Path) -> None:
    history_store, project_id, project_root, _ = _setup_project(tmp_path)

    record_local_history_transaction(
        history_store,
        {},
        project_id=project_id,
        project_root=project_root,
        source="quick_fix",
        label="No-op",
    )
