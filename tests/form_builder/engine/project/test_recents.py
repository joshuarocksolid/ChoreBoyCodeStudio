from __future__ import annotations

import json
from pathlib import Path

from app.features.form_builder.engine.project.adoption import adopted_forms
from app.features.form_builder.engine.project.fs import OsFileSystem
from app.features.form_builder.engine.project.recents import recent_forms, remember_form


def test_recent_forms_keep_the_eight_newest(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    forms = root / "forms"
    forms.mkdir(parents=True)
    fs = OsFileSystem()
    for index in range(10):
        path = forms / ("form_%d.ui" % index)
        path.write_text("<ui/>\n", encoding="utf-8")
        remember_form(str(root), str(path), fs)
    found = recent_forms(str(root), fs)
    assert found[0] == "forms/form_9.ui"
    assert len(found) == 8
    assert "forms/form_0.ui" not in found
    assert "forms/form_1.ui" not in found
    remember_form(str(root), str(forms / "form_5.ui"), fs)
    assert recent_forms(str(root), fs)[0] == "forms/form_5.ui"
    assert not (root / "cbcs" / "project.json").exists()


def test_remembering_a_form_keeps_adopted_forms(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    forms = root / "forms"
    forms.mkdir(parents=True)
    ui_path = forms / "invoice.ui"
    ui_path.write_text("<ui/>\n", encoding="utf-8")
    manifest = root / "cbcs" / "project.json"
    manifest.parent.mkdir()
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "name": "Shop",
                "form_builder": {"adopted_forms": ["src/legacy.ui"]},
            }
        ),
        encoding="utf-8",
    )
    before = manifest.read_text(encoding="utf-8")
    fs = OsFileSystem()
    remember_form(str(root), str(ui_path), fs)
    assert manifest.read_text(encoding="utf-8") == before
    assert adopted_forms(str(root), fs) == ("src/legacy.ui",)
    assert recent_forms(str(root), fs) == ("forms/invoice.ui",)
    assert (root / "cbcs" / "recent_forms.json").is_file()
    assert "project.json" not in (root / "cbcs" / "recent_forms.json").read_text(encoding="utf-8")
