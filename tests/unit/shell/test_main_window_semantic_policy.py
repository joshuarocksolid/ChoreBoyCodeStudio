"""Unit tests for semantic token scheduling policy gates."""

from __future__ import annotations

from typing import Any, cast

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.core import constants
from app.intelligence.cache_controls import IntelligenceRuntimeSettings
from app.shell.main_window import MainWindow

pytestmark = pytest.mark.unit


def _window_with_settings(settings: IntelligenceRuntimeSettings) -> MainWindow:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._intelligence_runtime_settings = settings
    return window


def test_policy_accepts_python_extensions_and_shebang() -> None:
    settings = IntelligenceRuntimeSettings(
        highlighting_adaptive_mode=constants.HIGHLIGHTING_MODE_NORMAL,
        highlighting_reduced_threshold_chars=250_000,
        highlighting_lexical_only_threshold_chars=600_000,
    )
    window = _window_with_settings(settings)
    assert window._should_enable_python_semantic_tokens(file_path="/tmp/main.py", source_text="x = 1\n") is True
    assert window._should_enable_python_semantic_tokens(file_path="/tmp/gui.pyw", source_text="x = 1\n") is True
    assert (
        window._should_enable_python_semantic_tokens(
            file_path="/tmp/tool",
            source_text="#!/usr/bin/env python3\nprint('ok')\n",
        )
        is True
    )


def test_policy_rejects_non_python_files() -> None:
    settings = IntelligenceRuntimeSettings()
    window = _window_with_settings(settings)
    assert window._should_enable_python_semantic_tokens(file_path="/tmp/data.json", source_text='{"x": 1}\n') is False


def test_policy_rejects_large_source_and_non_normal_mode() -> None:
    settings = IntelligenceRuntimeSettings(
        highlighting_adaptive_mode=constants.HIGHLIGHTING_MODE_REDUCED,
        highlighting_reduced_threshold_chars=10,
        highlighting_lexical_only_threshold_chars=20,
    )
    window = _window_with_settings(settings)
    assert window._should_enable_python_semantic_tokens(file_path="/tmp/main.py", source_text="x = 1\n") is False

    normal_window = _window_with_settings(
        IntelligenceRuntimeSettings(
            highlighting_adaptive_mode=constants.HIGHLIGHTING_MODE_NORMAL,
            highlighting_reduced_threshold_chars=5,
            highlighting_lexical_only_threshold_chars=10,
        )
    )
    assert normal_window._should_enable_python_semantic_tokens(file_path="/tmp/main.py", source_text="x = 123456\n") is False
