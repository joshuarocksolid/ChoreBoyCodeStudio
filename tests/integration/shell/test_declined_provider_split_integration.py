"""A text tab opened after a provider declines can still be split."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.project.project_service import create_blank_project  # noqa: E402
from app.shell.editor_tab_page import page_editor  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from app.shell.tab_content_providers import ProviderDeclined, TabMatchContext  # noqa: E402
from testing.main_window_shutdown import shutdown_main_window_for_test  # noqa: E402
from testing.main_window_test_helpers import prepare_main_window_for_test  # noqa: E402

pytestmark = pytest.mark.integration


class _DecliningProvider:
    provider_id = "round2-decline"
    priority = 50

    def matches(self, file_path: str, context: TabMatchContext) -> bool:
        del context
        return file_path.endswith(".declined")

    def create_surface(self, request: object) -> object:
        del request
        raise ProviderDeclined("Opened as text.")


def test_declined_provider_text_tab_can_split(tmp_path: Path, shell_qapp) -> None:  # type: ignore[no-untyped-def]
    app = shell_qapp
    project_root = tmp_path / "project"
    create_blank_project(str(project_root.resolve()), project_name="Groups")
    anchor = project_root / "alpha.py"
    anchor.write_text("# alpha.py\n", encoding="utf-8")
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    prepare_main_window_for_test(window, app=app)
    window.resize(1400, 800)
    window.show()
    assert window._file_project_commands_workflow.open_project_by_path(str(project_root.resolve())) is True
    assert window._editor_tab_factory.open_file_in_editor(str(anchor.resolve())) is True

    window._tab_content_registry.register(_DecliningProvider())  # type: ignore[arg-type]
    declined = project_root / "notes.declined"
    declined.write_text("keep me\n", encoding="utf-8")
    declined_path = str(declined.resolve())
    assert window._editor_tab_factory.open_file_in_editor(declined_path) is True

    groups = window._editor_groups
    page = groups.tab_widgets()[0].currentWidget()
    content = page.content()
    assert groups.split_right() is True
    second = page_editor(groups.tab_widgets()[1].currentWidget())
    first = page_editor(page)
    assert first is not None and second is not None and second is not first
    assert second.document() is first.document()
    assert callable(getattr(content, "source_editor", None))
    assert not callable(getattr(content, "apply_theme", None))
    assert not callable(getattr(content, "set_mode", None))
    assert not callable(getattr(content, "toggle_preview", None))
    shutdown_main_window_for_test(window, app)
