"""Unit tests for built-in workflow job cancellation."""

from __future__ import annotations

import pytest

from app.plugins import builtin_workflows

pytestmark = pytest.mark.unit


def test_builtin_pytest_job_raises_when_cancelled_before_start() -> None:
    with pytest.raises(RuntimeError, match="cancelled"):
        builtin_workflows._run_builtin_pytest_job(  # type: ignore[attr-defined]
            {"project_root": "/tmp/project"},
            emit_event=lambda *_args, **_kwargs: None,
            is_cancelled=lambda: True,
        )


def test_builtin_packaging_job_raises_when_cancelled_before_start() -> None:
    with pytest.raises(RuntimeError, match="cancelled"):
        builtin_workflows._run_builtin_packaging_job(  # type: ignore[attr-defined]
            {
                "project_root": "/tmp/project",
                "project_name": "demo",
                "entry_file": "main.py",
                "output_dir": "/tmp/out",
            },
            emit_event=lambda *_args, **_kwargs: None,
            is_cancelled=lambda: True,
        )
