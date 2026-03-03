"""Unit tests for the CRUD showcase SQLite repository.

The example project lives under ``example_projects/crud_showcase/`` and has its
own ``app/`` package that would collide with the editor's ``app/`` package on
sys.path.  We use importlib's spec-based import directly from the file path to
avoid that collision.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_PY = (
    Path(__file__).resolve().parents[3]
    / "example_projects"
    / "crud_showcase"
    / "app"
    / "repository.py"
)


def _load_repository_module():  # type: ignore[no-untyped-def]
    """Import repository.py from the bundled example project without touching sys.path."""
    module_name = "_crud_showcase_repository"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, str(_REPO_PY))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _load_repository_module()
TaskRepository = _mod.TaskRepository


@pytest.fixture
def repo(tmp_path: Path):  # type: ignore[no-untyped-def]
    r = TaskRepository(tmp_path)
    yield r
    r.close()


def test_create_and_read(repo) -> None:  # type: ignore[no-untyped-def]
    task = repo.create("Buy milk", description="2% milk", status="pending")
    assert task.task_id > 0
    assert task.title == "Buy milk"

    all_tasks = repo.read_all()
    assert len(all_tasks) == 1
    assert all_tasks[0].title == "Buy milk"
    assert all_tasks[0].description == "2% milk"
    assert all_tasks[0].status == "pending"


def test_update(repo) -> None:  # type: ignore[no-untyped-def]
    task = repo.create("Draft email")
    assert repo.update(task.task_id, "Send email", "urgent", "done")

    updated = repo.read_all()
    assert updated[0].title == "Send email"
    assert updated[0].status == "done"


def test_delete(repo) -> None:  # type: ignore[no-untyped-def]
    task = repo.create("Temp task")
    assert repo.delete(task.task_id)
    assert repo.read_all() == []


def test_filter_by_status(repo) -> None:  # type: ignore[no-untyped-def]
    repo.create("A", status="pending")
    repo.create("B", status="done")
    repo.create("C", status="in_progress")

    pending = repo.read_all(status_filter="pending")
    assert len(pending) == 1
    assert pending[0].title == "A"

    done = repo.read_all(status_filter="done")
    assert len(done) == 1
    assert done[0].title == "B"


def test_search(repo) -> None:  # type: ignore[no-untyped-def]
    repo.create("Feed the cat", description="morning routine")
    repo.create("Walk the dog")

    results = repo.read_all(search="cat")
    assert len(results) == 1
    assert results[0].title == "Feed the cat"


def test_count_by_status(repo) -> None:  # type: ignore[no-untyped-def]
    repo.create("A", status="pending")
    repo.create("B", status="pending")
    repo.create("C", status="done")

    counts = repo.count_by_status()
    assert counts["pending"] == 2
    assert counts["done"] == 1
    assert counts["in_progress"] == 0


def test_invalid_status_raises(repo) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError, match="Invalid status"):
        repo.create("Bad", status="bogus")

    task = repo.create("OK")
    with pytest.raises(ValueError, match="Invalid status"):
        repo.update(task.task_id, "OK", "", "bogus")
