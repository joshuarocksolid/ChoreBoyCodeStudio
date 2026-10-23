"""New form tab: virtual tab, create flow, and the adopt hook M2.4 binds.

The form tab does not expose a selection method yet. ``select_created_widget``
calls ``select_object`` when that method appears.
"""

from __future__ import annotations

import os
from typing import Callable, Optional, Sequence

from app.qt.QtCore import QTimer
from app.qt.QtWidgets import QMessageBox, QWidget

from app.features.form_builder.engine.project.create import CreateResult, create_form
from app.features.form_builder.engine.project.fs import OsFileSystem, ProjectOpError
from app.features.form_builder.engine.project.recents import (
    recent_folder,
    recent_forms,
    recent_name,
    remember_form,
)
from app.features.form_builder.engine.project.templates import first_useful_widget
from app.features.form_builder.integration.provider import FormTabProvider
from app.features.form_builder.qtside.dialogs.from_table import FromTableDialog, locale_date_format
from app.features.form_builder.qtside.start.panel import NewFormPanel
from app.features.form_builder.qtside.theme.chrome import FormChrome, chrome_from_values
from app.qt.qt_compat import exec_qt
from app.shell.tab_content_providers import TabMatchContext, TabSurfaceRequest
from app.shell.theme_tokens import ShellThemeTokens

NEW_FORM_PROVIDER_ID = "form-builder.new-form"
NEW_FORM_BASENAME = "new-form.cbcs-tab"
_ADOPT: Optional[Callable[[], None]] = None


def bind_adopt_entry(handler: Callable[[], None]) -> None:
    """M2.4 calls this with the adopt flow. The card does not reimplement it."""
    global _ADOPT
    _ADOPT = handler


def adopt_entry() -> Optional[Callable[[], None]]:
    return _ADOPT


def chrome_for(tokens: ShellThemeTokens) -> FormChrome:
    return chrome_from_values(
        window=tokens.window_bg,
        panel=tokens.panel_bg,
        text=tokens.text_primary,
        muted=tokens.text_muted,
        faint=tokens.gutter_text,
        border=tokens.border,
        accent=tokens.accent,
        row_hover=tokens.tree_hover_bg,
        input_bg=tokens.input_bg,
        error=tokens.diag_error_color,
        focus_width=tokens.focus_border_width,
    )


def new_form_tab_path(project_root: str) -> str:
    return os.path.join(os.path.abspath(project_root), "cbcs", NEW_FORM_BASENAME)


def is_new_form_tab(file_path: str) -> bool:
    return os.path.basename(file_path) == NEW_FORM_BASENAME


def recent_entries(project_root: str, fs: OsFileSystem) -> tuple:
    found = []
    for relative in recent_forms(project_root, fs):
        found.append((recent_name(relative), recent_folder(relative), relative))
    return tuple(found)


def select_created_widget(surface: object, object_name: Optional[str]) -> bool:
    """Select ``object_name`` when the form tab grows ``select_object``.

    The form tab has no selection API yet, so the new form opens with the
    root in place (UX-START-004).
    """
    if surface is None or not object_name:
        return False
    select = getattr(surface, "select_object", None)
    if not callable(select):
        return False
    select(object_name)
    return True


def perform_create(
    window: object,
    *,
    template: str,
    stem: str,
    directory: str,
    ui_text: Optional[str] = None,
    first_widget: Optional[str] = None,
) -> CreateResult:
    """Write the form with ``create_form``, then open the ``.ui`` tab."""
    project = getattr(window, "_loaded_project", None)
    if project is None:
        return CreateResult((), (), None, "Open a project first.")
    root = os.path.abspath(project.project_root)
    fs = OsFileSystem()
    result = create_form(
        root,
        stem,
        fs,
        template=template,
        directory=directory,
        ui_text=ui_text,
    )
    if result.refused or result.scope is None:
        return result
    ui_path = result.scope.ui_path
    try:
        remember_form(root, ui_path, fs)
    except ProjectOpError:
        pass
    factory = getattr(window, "_editor_tab_factory", None)
    if factory is not None:
        factory.open_file_in_editor(ui_path)
    registry = getattr(window, "_tab_content_registry", None)
    if registry is not None:
        surface = registry.surface_for_path(os.path.abspath(ui_path))
        chosen = first_widget if ui_text is not None else first_useful_widget(template)
        select_created_widget(surface, chosen)
    tree = getattr(window, "_project_tree_ui_workflow", None)
    refresh = getattr(tree, "refresh_project_tree_from_disk", None)
    if callable(refresh):
        refresh()
    QTimer.singleShot(0, lambda: _close_start_tab(window, root))
    return result


def open_new_form_tab(window: object, directory: Optional[str] = None) -> None:
    project = getattr(window, "_loaded_project", None)
    if project is None:
        QMessageBox.information(window, "New form", "Open a project first.")  # type: ignore[arg-type]
        return
    root = os.path.abspath(project.project_root)
    setattr(window, "_new_form_directory", directory)
    path = new_form_tab_path(root)
    manager = window._editor_manager  # type: ignore[attr-defined]
    opened = manager.open_file_with_content(
        path,
        "",
        original_content="",
        last_known_mtime=None,
    )
    opened.tab.display_name = "New form"
    opened.tab.virtual_tab = True
    factory = window._editor_tab_factory  # type: ignore[attr-defined]
    factory._materialize_opened_editor_tab(opened, started_at=None, restore_draft=False)
    registry = window._tab_content_registry  # type: ignore[attr-defined]
    surface = registry.surface_for_path(opened.tab.file_path)
    if surface is not None and hasattr(surface, "set_directory"):
        surface.set_directory(directory)
    if surface is not None:
        surface.focus_primary()


def attach_new_form(window: object) -> None:
    """Register the virtual tab and the File / tree callback. Menus read it later.

    The Welcome page has no extension point, so there is no Welcome-page
    button (UX-START-001).
    """
    registry = window._tab_content_registry  # type: ignore[attr-defined]
    registry.register(NewFormTabProvider(window))

    def open_new_form(directory: Optional[str] = None) -> None:
        open_new_form_tab(window, directory)

    window._open_new_form = open_new_form  # type: ignore[attr-defined]


class RememberingFormTabProvider:
    """The ``.ui`` provider, plus a recent-forms update when a form opens."""

    def __init__(self) -> None:
        self._inner = FormTabProvider()
        self.provider_id = self._inner.provider_id
        self.priority = self._inner.priority

    def matches(self, file_path: str, context: TabMatchContext) -> bool:
        return self._inner.matches(file_path, context)

    def create_surface(self, request: TabSurfaceRequest) -> object:
        surface = self._inner.create_surface(request)
        root = request.project_root
        if root and request.file_path.lower().endswith(".ui"):
            try:
                remember_form(root, request.file_path, OsFileSystem())
            except ProjectOpError:
                pass
        return surface


class NewFormTabProvider:
    """Matches the virtual New form path and nothing else."""

    provider_id = NEW_FORM_PROVIDER_ID
    priority = 80

    def __init__(self, window: object) -> None:
        self._window = window

    def matches(self, file_path: str, context: TabMatchContext) -> bool:
        del context
        return is_new_form_tab(file_path)

    def create_surface(self, request: TabSurfaceRequest) -> "NewFormSurface":
        return NewFormSurface(request, self._window)


class NewFormSurface:
    def __init__(self, request: TabSurfaceRequest, window: object) -> None:
        self._request = request
        self._window = window
        root = request.project_root or os.getcwd()
        preferred = os.path.join(root, "forms")
        self._panel = NewFormPanel(
            project_root=root,
            directory=preferred,
            fs=OsFileSystem(),
            chrome=chrome_for(request.theme),
            parent=request.parent,
        )
        self._panel.create_requested.connect(self._create)
        self._panel.from_table_requested.connect(self._from_table)
        self._panel.adopt_requested.connect(self._adopt)
        self._panel.open_recent_requested.connect(self._open_recent)
        self._reload_recents()

    def widget(self) -> QWidget:
        return self._panel

    def content_source(self) -> None:
        return None

    def source_editor(self) -> None:
        return None

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self._panel.apply_chrome(chrome_for(tokens))

    def set_diagnostics(self, diagnostics: Sequence[object]) -> None:
        del diagnostics

    def reveal(self, line: int, detail: object) -> bool:
        del line, detail
        return False

    def restore_text(self, text: str, reason: object) -> None:
        del text, reason

    def close_blockers(self) -> tuple:
        return ()

    def file_path_changed(self, new_path: str) -> None:
        del new_path

    def focus_primary(self) -> None:
        self._panel.focus_name()

    def release(self) -> None:
        return None

    def set_directory(self, directory: Optional[str]) -> None:
        if directory:
            self._panel.set_directory(directory)
        self._panel.focus_name()

    def _create(self, key: str) -> None:
        result = perform_create(
            self._host(),
            template=key,
            stem=self._panel.stem(),
            directory=self._panel.directory(),
            first_widget=first_useful_widget(key),
        )
        if result.refused:
            self._panel.show_status(result.refused)
            return
        self._reload_recents()

    def _from_table(self) -> None:
        root = self._request.project_root or os.getcwd()
        dialog = FromTableDialog(
            project_root=root,
            stem=self._panel.stem(),
            chrome=chrome_for(self._request.theme),
            date_format=locale_date_format(),
            name_reason=self._panel.name_reason,
            parent=self._panel,
        )
        dialog.create_requested.connect(lambda: self._create_from_dialog(dialog))
        exec_qt(dialog)

    def _create_from_dialog(self, dialog: FromTableDialog) -> None:
        built = dialog.built_form()
        result = perform_create(
            self._host(),
            template="widget",
            stem=self._panel.stem(),
            directory=self._panel.directory(),
            ui_text=built.text,
            first_widget=built.first_widget,
        )
        if result.refused:
            self._panel.show_status(result.refused)
            return
        dialog.accept()
        self._reload_recents()

    def _adopt(self) -> None:
        handler = adopt_entry()
        if handler is None:
            self._panel.show_status(
                "Adopt a form your code already loads is not available in this build."
            )
            return
        handler()

    def _open_recent(self, relative: str) -> None:
        root = self._request.project_root
        if not root:
            return
        path = os.path.normpath(os.path.join(root, relative))
        factory = getattr(self._host(), "_editor_tab_factory", None)
        if factory is not None:
            factory.open_file_in_editor(path)

    def _reload_recents(self) -> None:
        root = self._request.project_root
        if not root:
            self._panel.set_recents(())
            return
        try:
            self._panel.set_recents(recent_entries(root, OsFileSystem()))
        except ProjectOpError as exc:
            self._panel.show_status(str(exc))

    def _host(self) -> object:
        return self._window


def _close_start_tab(window: object, project_root: str) -> None:
    workflow = getattr(window, "_editor_tab_workflow", None)
    if workflow is None:
        return
    close = getattr(workflow, "close_tab_discarding_edits", None)
    if not callable(close):
        return
    close(new_form_tab_path(project_root), skip_close_blockers=True)
