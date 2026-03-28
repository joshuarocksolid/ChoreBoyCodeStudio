"""Unit tests for vendored Python tooling runtime validation."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.python_tools import vendor_runtime

pytestmark = pytest.mark.unit


def test_initialize_python_tooling_runtime_marks_missing_black_api_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_import_module(name: str):  # type: ignore[no-untyped-def]
        if name == "black":
            return SimpleNamespace(__version__="24.10.0")
        if name == "isort":
            return SimpleNamespace(
                __version__="6.1.0",
                Config=object,
                api=SimpleNamespace(sort_code_string=lambda *_args, **_kwargs: "ok"),
            )
        if name == "tomli":
            return SimpleNamespace(__version__="2.3.0")
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(vendor_runtime.importlib, "import_module", fake_import_module)

    status = vendor_runtime.initialize_python_tooling_runtime()

    assert status.is_available is False
    assert status.black_available is False
    assert status.black_missing_apis == (
        "Mode",
        "format_file_contents",
        "NothingChanged",
        "InvalidInput",
    )
    assert "black missing APIs" in status.message


def test_initialize_python_tooling_runtime_marks_missing_isort_api_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_import_module(name: str):  # type: ignore[no-untyped-def]
        if name == "black":
            return SimpleNamespace(
                __version__="24.10.0",
                Mode=object,
                format_file_contents=lambda *_args, **_kwargs: "formatted",
                NothingChanged=type("NothingChanged", (Exception,), {}),
                InvalidInput=type("InvalidInput", (Exception,), {}),
            )
        if name == "isort":
            return SimpleNamespace(__version__="6.1.0", Config=object)
        if name == "tomli":
            return SimpleNamespace(__version__="2.3.0")
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(vendor_runtime.importlib, "import_module", fake_import_module)

    status = vendor_runtime.initialize_python_tooling_runtime()

    assert status.is_available is False
    assert status.isort_available is False
    assert status.isort_missing_apis == ("api", "api.sort_code_string")
    assert "isort missing APIs" in status.message


def test_import_python_tooling_modules_raises_when_runtime_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        vendor_runtime,
        "initialize_python_tooling_runtime",
        lambda app_root=None: SimpleNamespace(  # noqa: ARG005
            is_available=False,
            message="Python tooling runtime unavailable: black missing APIs (format_file_contents)",
        ),
    )

    with pytest.raises(RuntimeError, match="black missing APIs"):
        vendor_runtime.import_python_tooling_modules()
