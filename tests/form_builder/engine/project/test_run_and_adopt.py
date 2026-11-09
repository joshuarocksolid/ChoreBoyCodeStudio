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


def test_f5_on_a_form_outside_forms_previews_without_calling_it_projectless(tmp_path: Path) -> None:
    root, _ui_path = _project(tmp_path, "main.py")
    loose = root / "loose.ui"
    loose.write_text((root / "forms" / "invoice.ui").read_text(encoding="utf-8"), encoding="utf-8")
    surface, bar, ran = _run(root, str(loose), "main.py")
    assert ran == []
    assert surface.preview == str(loose)
    assert bar.messages == ["This form isn't in forms/ or adopted, so F5 previews it."]
    assert not (root / "ui_loose.py").exists()


def test_f5_with_no_open_project_previews(tmp_path: Path) -> None:
    ui = tmp_path / "loose.ui"
    ui.write_text("unused\n", encoding="utf-8")
    surface = _Surface(str(ui), "unused\n")
    bar = _Messages()
    host = SimpleNamespace(loaded_project=lambda: None, status_bar=lambda: bar, _window=None)
    workflow = SimpleNamespace(_host=host, handle_run_project_action=lambda: False)
    assert run_open_form(surface, workflow) is True
    assert surface.preview == str(ui)
    assert bar.messages == ["This form isn't part of a project, so F5 previews it."]


def test_f5_for_a_file_outside_the_project_tree_previews(tmp_path: Path) -> None:
    root, _ui_path = _project(tmp_path, "main.py")
    outside = tmp_path / "outside.ui"
    outside.write_text("unused\n", encoding="utf-8")
    surface, bar, ran = _run(root, str(outside), "main.py")
    assert ran == []
    assert surface.preview == str(outside)
    assert bar.messages == ["This form isn't part of a project, so F5 previews it."]


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
    caller.write_text(
        "from PySide6.QtUiTools import QUiLoader\n"
        "def open_form():\n"
        "    return QUiLoader().load('invoice.ui')\n",
        encoding="utf-8",
    )
    original = caller.read_bytes()
    before, after = prepare_adoption(str(root), ui_path)
    assert "QUiLoader().load('invoice.ui')" in before
    assert "QUiLoader.load" in before
    assert "qui_loader" not in before
    assert "# At the top of the file" in after
    assert "# In __init__" in after
    assert "self.ui.setupUi(self)" in after
    assert "Ui_Invoice" in after
    assert caller.read_bytes() == original
    assert not (root / "cbcs" / "project.json").exists()


def test_prepare_adoption_records_a_form_that_is_not_in_forms(tmp_path: Path) -> None:
    root, ui_path = _project(tmp_path, "main.py")
    views = root / "views"
    views.mkdir()
    target = views / "invoice.ui"
    target.write_text(Path(ui_path).read_text(encoding="utf-8"), encoding="utf-8")
    _before, after = prepare_adoption(str(root), str(target))
    manifest = (root / "cbcs" / "project.json").read_text(encoding="utf-8")
    assert "views/invoice.ui" in manifest
    assert (views / "ui_invoice.py").is_file()
    assert (views / "invoice_window.py").is_file()
    assert "views.ui_invoice" in after


def test_loader_scan_skips_vendor_and_node_modules(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    for name in ("vendor", "node_modules"):
        folder = root / name
        folder.mkdir(parents=True)
        (folder / "load.py").write_text("QUiLoader().load('widget.ui')\n", encoding="utf-8")
    (root / "app").mkdir()
    (root / "app" / "open.py").write_text("loadUi('invoice.ui')\n", encoding="utf-8")
    sites = scan_ui_loaders(str(root))
    assert [Path(site.path).name for site in sites] == ["open.py"]


class _ShellSave:
    """The shell's save_tab: writes the file and runs the form's after_save codegen."""

    def __init__(self, surface: "_Surface", notice: object) -> None:
        self.surface = surface
        self.notice = notice
        self.calls = 0

    def save_tab(self, path: str) -> bool:
        self.calls += 1
        Path(path).write_text(self.surface.text, encoding="utf-8")
        return True


def _shell_run(root: Path, ui_path: str, notice: object, monkeypatch: pytest.MonkeyPatch):
    surface = _Surface(ui_path, Path(ui_path).read_text(encoding="utf-8"))
    surface.content_source = lambda: SimpleNamespace(save_notice=notice)  # type: ignore[attr-defined]
    saver = _ShellSave(surface, notice)
    generated: list[str] = []
    import app.features.form_builder.integration.run_action as run_action

    real = run_action.write_generated
    monkeypatch.setattr(
        run_action, "write_generated", lambda *a, **k: generated.append("x") or real(*a, **k)
    )
    bar = _Messages()
    ran: list[str] = []
    project = SimpleNamespace(project_root=str(root), metadata=SimpleNamespace(default_entry="main.py"))
    window = SimpleNamespace(_save_workflow=saver)
    host = SimpleNamespace(loaded_project=lambda: project, status_bar=lambda: bar, _window=window)
    workflow = SimpleNamespace(_host=host, handle_run_project_action=lambda: ran.append("project") or True)
    result = run_open_form(surface, workflow)
    return result, saver, generated, bar, ran


def test_f5_through_the_shell_save_does_not_generate_twice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, ui_path = _project(tmp_path, "main.py")
    notice = SimpleNamespace(error=False, text="Saved")
    result, saver, generated, bar, ran = _shell_run(root, ui_path, notice, monkeypatch)
    assert result is True and saver.calls == 1
    assert generated == []
    assert ran == ["project"]


def test_f5_does_not_run_when_the_save_could_not_generate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, ui_path = _project(tmp_path, "main.py")
    notice = SimpleNamespace(error=True, text="Could not write ui_invoice.py.")
    result, saver, generated, bar, ran = _shell_run(root, ui_path, notice, monkeypatch)
    assert result is False
    assert ran == []
    assert bar.messages == ["Could not write ui_invoice.py."]
