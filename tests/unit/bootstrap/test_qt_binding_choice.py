"""Unit tests for the Qt binding candidate list and selector."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.bootstrap import qt_binding_choice

pytestmark = pytest.mark.unit


def _forbid_import(name: str, package: object = None) -> object:
    _ = package
    raise AssertionError(name)


@pytest.fixture(autouse=True)
def _clear_binding_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(qt_binding_choice.ENV_VAR, raising=False)
    monkeypatch.setattr(qt_binding_choice.importlib, "import_module", _forbid_import)


def _patch_specs(monkeypatch: pytest.MonkeyPatch, specs: dict[str, object]) -> None:
    def find_spec(name: str, package: object = None) -> object:
        _ = package
        return specs.get(name)

    monkeypatch.setattr(qt_binding_choice.importlib.util, "find_spec", find_spec)


def test_select_binding_returns_pyside6_when_it_is_the_only_spec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    qt_binding_choice.reset_choice_state()
    _patch_specs(monkeypatch, {"PySide6": SimpleNamespace(origin=None)})

    assert qt_binding_choice.select_binding() == "PySide6"


def test_select_binding_returns_pyside2_when_it_is_the_only_spec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    qt_binding_choice.reset_choice_state()
    _patch_specs(monkeypatch, {"PySide2": SimpleNamespace(origin=None)})

    assert qt_binding_choice.select_binding() == "PySide2"


def test_select_binding_names_the_env_var_when_neither_spec_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    qt_binding_choice.reset_choice_state()
    _patch_specs(monkeypatch, {})

    with pytest.raises(ImportError) as caught:
        qt_binding_choice.select_binding()

    assert "CBCS_QT_API" in str(caught.value)


def test_env_pyside2_rejects_a_machine_that_only_has_pyside6(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    qt_binding_choice.reset_choice_state()
    monkeypatch.setenv(qt_binding_choice.ENV_VAR, "pyside2")
    _patch_specs(monkeypatch, {"PySide6": SimpleNamespace(origin=None)})

    assert qt_binding_choice.binding_candidates() == ("PySide2",)
    with pytest.raises(ImportError) as caught:
        qt_binding_choice.select_binding()

    assert "CBCS_QT_API" in str(caught.value)


def test_select_binding_prefers_pyside6_when_both_specs_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    qt_binding_choice.reset_choice_state()
    _patch_specs(
        monkeypatch,
        {
            "PySide6": SimpleNamespace(origin=None),
            "PySide2": SimpleNamespace(origin=None),
        },
    )

    assert qt_binding_choice.select_binding() == "PySide6"


def test_freecad_shim_under_ext_names_pyside6(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    qt_binding_choice.reset_choice_state()
    shim = tmp_path / "Ext" / "PySide" / "__init__.py"
    shim.parent.mkdir(parents=True)
    shim.write_text("from PySide6 import __version__\n", encoding="utf-8")
    _patch_specs(
        monkeypatch,
        {
            "PySide": SimpleNamespace(origin=str(shim)),
            "PySide2": SimpleNamespace(origin="PySide2"),
            "PySide6": SimpleNamespace(origin="PySide6"),
        },
    )

    assert qt_binding_choice.binding_candidates() == ("PySide6",)


def test_freecad_shim_under_ext_names_pyside2(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    qt_binding_choice.reset_choice_state()
    shim = tmp_path / "Ext" / "PySide" / "__init__.py"
    shim.parent.mkdir(parents=True)
    shim.write_text("from PySide2 import __version__\n", encoding="utf-8")
    _patch_specs(
        monkeypatch,
        {
            "PySide": SimpleNamespace(origin=str(shim)),
            "PySide2": SimpleNamespace(origin="PySide2"),
            "PySide6": SimpleNamespace(origin="PySide6"),
        },
    )

    assert qt_binding_choice.binding_candidates() == ("PySide2",)
    assert qt_binding_choice.select_binding() == "PySide2"


def test_forced_by_env_stays_false_until_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    qt_binding_choice.reset_choice_state()

    assert qt_binding_choice.forced_by_env() is False
    monkeypatch.setenv(qt_binding_choice.ENV_VAR, "pyside6")
    assert qt_binding_choice.forced_by_env() is False
    qt_binding_choice.reset_choice_state()
    assert qt_binding_choice.forced_by_env() is True
