"""F5 chooses run or preview, and the adopt scan finds runtime loaders."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.features.form_builder.engine.project.adopt_offer import prepare_adoption
from app.features.form_builder.engine.project.create import create_form
from app.features.form_builder.engine.project.fs import OsFileSystem
from app.features.form_builder.engine.project.loaders import scan_ui_loaders
from app.features.form_builder.integration.run_action import run_open_form

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[4]


class _Messages:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def showMessage(self, text: str) -> None:
        self.messages.append(text)


class _Surface:
    def __init__(self, path: str, text: str) -> None:
        self.path = path
        self.text = text
        self.preview: str | None = None

    def form_path(self) -> str:
        return self.path

    def current_text(self) -> str:
        return self.text

    def mark_saved(self, text: str) -> None:
        self.text = text

    def request_preview(self, path: str) -> None:
        self.preview = path


def _project(tmp_path: Path, entry: str) -> tuple[Path, str]:
    root = tmp_path / "project"
    created = create_form(str(root), "invoice", OsFileSystem(), template="widget")
    assert created.refused is None
    ui_path = root / "forms" / "invoice.ui"
    return root, str(ui_path)


def _run(root: Path, ui_path: str, entry: str) -> tuple[_Surface, _Messages, list[str]]:
    surface = _Surface(ui_path, Path(ui_path).read_text(encoding="utf-8"))
    bar = _Messages()
    ran: list[str] = []
    project = SimpleNamespace(project_root=str(root), metadata=SimpleNamespace(default_entry=entry))
    host = SimpleNamespace(loaded_project=lambda: project, status_bar=lambda: bar, _window=None)
    workflow = SimpleNamespace(
        _host=host,
        handle_run_project_action=lambda: ran.append("project") or True,
    )
    assert run_open_form(surface, workflow) is True
    return surface, bar, ran


def test_f5_on_a_project_form_saves_and_runs_the_entry(tmp_path: Path) -> None:
    root, ui_path = _project(tmp_path, "main.py")
    (root / "forms" / "ui_invoice.py").unlink()
    surface, bar, ran = _run(root, ui_path, "main.py")
    assert ran == ["project"]
    assert surface.preview is None
    assert bar.messages == ["Saved invoice.ui · Running main.py"]
    assert (root / "forms" / "ui_invoice.py").is_file()


def test_f5_outside_a_project_previews_the_form(tmp_path: Path) -> None:
    root, _ui_path = _project(tmp_path, "main.py")
    loose = root / "loose.ui"
    loose.write_text((root / "forms" / "invoice.ui").read_text(encoding="utf-8"), encoding="utf-8")
    surface, bar, ran = _run(root, str(loose), "main.py")
    assert ran == []
    assert surface.preview == str(loose)
    assert bar.messages == ["This form isn't part of a project, so F5 previews it."]
    assert not (root / "ui_loose.py").exists()


def test_f5_without_an_entry_point_previews_after_save(tmp_path: Path) -> None:
    root, ui_path = _project(tmp_path, "")
    (root / "forms" / "ui_invoice.py").unlink()
    surface, bar, ran = _run(root, ui_path, "")
    assert ran == []
    assert surface.preview == ui_path
    assert bar.messages == ["This project has no entry point, so F5 previews the form."]
    assert (root / "forms" / "ui_invoice.py").is_file()


def test_adopt_scan_finds_the_example_loaders() -> None:
    sites = scan_ui_loaders(str(_REPO / "example_projects"))
    smoke = [site for site in sites if site.path.endswith("smoke_qt_app/main.py")]
    assert {site.kind for site in smoke} == {"qui_loader", "load_ui", "pyside_uic"}
    before = (_REPO / "example_projects" / "smoke_qt_app" / "main.py").read_bytes()
    scan_ui_loaders(str(_REPO / "example_projects"))
    assert (_REPO / "example_projects" / "smoke_qt_app" / "main.py").read_bytes() == before


def test_prepare_adoption_suggests_setupui_and_leaves_user_python(tmp_path: Path) -> None:
    root, ui_path = _project(tmp_path, "main.py")
    caller = root / "main.py"
    caller.write_text('def open_form():\n    return loadUi("invoice.ui")\n', encoding="utf-8")
    original = caller.read_bytes()
    before, after = prepare_adoption(str(root), ui_path)
    assert 'loadUi("invoice.ui")' in before
    assert "self.ui.setupUi(self)" in after
    assert "Ui_Invoice" in after
    assert caller.read_bytes() == original
