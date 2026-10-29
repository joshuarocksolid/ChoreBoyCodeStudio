"""form_builder.* project settings: other keys survive, a write is a temp file plus a swap, a bad manifest is left alone."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List

import pytest

from app.features.form_builder.engine.project.adoption import adopted_forms
from app.features.form_builder.engine.project.fs import OsFileSystem, ProjectOpError
from app.features.form_builder.integration import project_settings as settings

pytestmark = [pytest.mark.unit]


def _manifest(root: Path) -> Path:
    return root / "cbcs" / "project.json"


def _seed(root: Path, payload: object) -> None:
    _manifest(root).parent.mkdir(parents=True)
    _manifest(root).write_text(json.dumps(payload), encoding="utf-8")


def test_a_write_keeps_every_other_key_and_the_other_form_builder_keys(tmp_path: Path) -> None:
    _seed(
        tmp_path,
        {"name": "Shop", "run_configs": [{"id": "a"}], "form_builder": {"adopted_forms": ["x/y.ui"], "grid": 8}},
    )
    settings.set_setting(str(tmp_path), "custom_widgets", [{"class": "TillDisplay"}])
    stored = json.loads(_manifest(tmp_path).read_text(encoding="utf-8"))
    assert stored["name"] == "Shop" and stored["run_configs"] == [{"id": "a"}]
    assert stored["form_builder"] == {
        "adopted_forms": ["x/y.ui"],
        "grid": 8,
        "custom_widgets": [{"class": "TillDisplay"}],
    }
    assert adopted_forms(str(tmp_path), OsFileSystem()) == ("x/y.ui",)
    assert settings.get_setting(str(tmp_path), "grid") == 8
    assert settings.get_setting(str(tmp_path), "missing", "fallback") == "fallback"
    settings.update_settings(str(tmp_path), {"grid": None, "custom_widgets": None, "adopted_forms": None})
    assert "form_builder" not in json.loads(_manifest(tmp_path).read_text(encoding="utf-8"))


def test_a_project_without_a_manifest_gets_one_with_only_the_new_setting(tmp_path: Path) -> None:
    assert settings.read_settings(str(tmp_path)) == {}
    settings.set_setting(str(tmp_path), "grid", 4)
    stored = json.loads(_manifest(tmp_path).read_text(encoding="utf-8"))
    assert stored["form_builder"] == {"grid": 4} and stored["name"] == tmp_path.name


class _CrashesBeforeTheSwap(OsFileSystem):
    """The temporary file is fully written, then the process dies before ``os.replace``."""

    def __init__(self) -> None:
        self.temporary: List[str] = []

    def write_bytes(self, path: str, data: bytes) -> None:
        tmp = path + ".crash.tmp"
        with open(tmp, "wb") as handle:
            handle.write(data)
        self.temporary.append(tmp)
        raise OSError("power cut")


def test_a_crash_between_the_write_and_the_swap_leaves_the_old_file_whole(tmp_path: Path) -> None:
    _seed(tmp_path, {"name": "Shop", "form_builder": {"grid": 8}})
    before = _manifest(tmp_path).read_bytes()
    crashing = _CrashesBeforeTheSwap()
    with pytest.raises(OSError):
        settings.set_setting(str(tmp_path), "grid", 16, crashing)
    assert _manifest(tmp_path).read_bytes() == before
    assert json.loads(Path(crashing.temporary[0]).read_text(encoding="utf-8"))["form_builder"]["grid"] == 16


def test_the_real_write_goes_through_a_temporary_file_and_a_replace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed(tmp_path, {"name": "Shop"})
    calls: List[tuple] = []
    real = os.replace
    monkeypatch.setattr(os, "replace", lambda source, target: (calls.append((source, target)), real(source, target))[1])
    settings.set_setting(str(tmp_path), "grid", 8)
    assert len(calls) == 1 and calls[0][1] == str(_manifest(tmp_path)) and calls[0][0] != calls[0][1]
    assert sorted(os.listdir(_manifest(tmp_path).parent)) == ["project.json"]


def test_an_unreadable_manifest_or_a_wrong_block_is_never_replaced(tmp_path: Path) -> None:
    _manifest(tmp_path).parent.mkdir(parents=True)
    _manifest(tmp_path).write_text("{ not json", encoding="utf-8")
    with pytest.raises(ProjectOpError):
        settings.set_setting(str(tmp_path), "grid", 4)
    assert _manifest(tmp_path).read_text(encoding="utf-8") == "{ not json"
    _manifest(tmp_path).write_text(json.dumps({"form_builder": ["oops"]}), encoding="utf-8")
    with pytest.raises(ProjectOpError):
        settings.set_setting(str(tmp_path), "grid", 4)
    assert json.loads(_manifest(tmp_path).read_text(encoding="utf-8")) == {"form_builder": ["oops"]}
    _manifest(tmp_path).write_text("{}", encoding="utf-8")
    with pytest.raises(ProjectOpError):
        settings.set_setting(str(tmp_path), "grid", object())
    with pytest.raises(ValueError):
        settings.set_setting(str(tmp_path), "form_builder.grid", 4)
    assert _manifest(tmp_path).read_text(encoding="utf-8") == "{}"
