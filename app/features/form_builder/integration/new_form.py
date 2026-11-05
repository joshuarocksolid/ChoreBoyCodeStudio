"""New form tab: virtual tab, create flow, and the adopt hook M2.4 binds.

After create, ``select_created_widget`` selects the template's first input
through ``FormSurface.select_object`` and focuses the canvas (UX-START-004).
"""

from __future__ import annotations

import os
from typing import Callable, Dict, Optional, Sequence

from app.qt.QtCore import QTimer
from app.qt.QtWidgets import QInputDialog, QLineEdit, QMessageBox, QWidget

from app.features.form_builder.engine.project.create import CreateResult, create_form
from app.features.form_builder.engine.project.fs import OsFileSystem, ProjectOpError
from app.features.form_builder.engine.project.recents import (
    recent_folder,
    recent_forms,
    recent_name,
    remember_form,
)
from app.features.form_builder.engine.project.names import class_name_for_stem
from app.features.form_builder.engine.project import user_templates as ut
from app.features.form_builder.engine.project.qrc_write import default_qrc_path
from app.features.form_builder.engine.project.template_use import create_from_template
from app.features.form_builder.engine.project.templates import first_useful_widget
from app.features.form_builder.engine.project.written_files import note_written_files
from app.features.form_builder.integration import settings_page, template_store
from app.features.form_builder.integration.settings_ext import connections_page as connections_settings
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.integration.provider import FormTabProvider
from app.features.form_builder.qtside.dialogs.from_table import FromTableDialog, locale_date_format
from app.features.form_builder.qtside.start.panel import NewFormPanel
from app.features.form_builder.qtside.start.wizard import WIZARD_KEY, wizard_document
from app.qt.qt_compat import exec_qt, wrapper_is_valid
from app.shell.tab_content_providers import TabMatchContext, TabSurfaceRequest
from app.shell.theme_tokens import ShellThemeTokens

NEW_FORM_PROVIDER_ID = "form-builder.new-form"
NEW_FORM_BASENAME = "new-form.cbcs-tab"
_ADOPT: Optional[Callable[[], None]] = None
#: Window-kind search rows (UX-CAT-015) and the New form card each one focuses.
WINDOW_KIND_CARDS = {
    "window:main": "main_window",
    "window:dialog": "dialog",
    "window:widget": "widget",
    "window:wizard": WIZARD_KEY,
}


def bind_adopt_entry(handler: Callable[[], None]) -> None:
    """M2.4 calls this with the adopt flow. The card does not reimplement it."""
    global _ADOPT
    _ADOPT = handler


def adopt_entry() -> Optional[Callable[[], None]]:
    return _ADOPT


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
    """Select ``object_name`` on the new form tab (UX-START-004).

    False when the tab has no ``select_object`` or no such widget; the form
    then opens with the root in place.
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
    saved_template: Optional[ut.TemplateInfo] = None,
) -> CreateResult:
    """Write the form with ``create_form``, then open the ``.ui`` tab.

    ``saved_template`` makes the form from a template the user saved
    (UX-TMPL-003): the root takes the name, its pictures are merged into the
    project, and the Workbench opens with the root selected.
    """
    project = getattr(window, "_loaded_project", None)
    if project is None:
        return CreateResult((), (), None, "Open a project first.")
    root = os.path.abspath(project.project_root)
    fs = OsFileSystem()
    notices: tuple = ()
    if saved_template is not None:
        made = create_from_template(root, saved_template, stem, fs, directory=directory)
        result, notices = made.result, made.notices
    else:
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
    if saved_template is not None:
        note_written_files((default_qrc_path(root),))
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
        if saved_template is not None:
            # UX-TMPL-003: the root is selected. Its object name is the class name the stem gives.
            chosen: Optional[str] = None
        else:
            chosen = first_widget if ui_text is not None else first_useful_widget(template)
        # UX-START-004: a blank form (and a saved template) opens with the root selected.
        select_created_widget(surface, chosen or class_name_for_stem(stem.strip()))
        say = getattr(surface, "show_plain", None)
        if notices and callable(say):
            say(notices[0])
    tree = getattr(window, "_project_tree_ui_workflow", None)
    refresh = getattr(tree, "refresh_project_tree_from_disk", None)
    if callable(refresh):
        refresh()
    QTimer.singleShot(0, lambda: _close_start_tab(window, root))
    return result


def _reload_open_main(window: object, root: str) -> None:
    """Show the rewritten ``main.py`` in a tab that is already open.

    The form undo step does not cover this file. The open tab is reloaded
    from disk so it matches what F5 will run.
    """

    path = os.path.abspath(os.path.join(root, "main.py"))
    if not os.path.isfile(path):
        return
    manager = getattr(window, "_editor_manager", None)
    getter = getattr(manager, "get_tab", None)
    if not callable(getter) or getter(path) is None:
        return
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    sync = getattr(window, "_editor_sync_workflow", None)
    apply = getattr(sync, "apply_disk_content", None)
    if not callable(apply):
        return
    from app.shell.editor_sync_workflow import EditorDiskSyncSource

    apply(path, text, source=EditorDiskSyncSource.EXTERNAL_RELOAD)


def open_new_form_tab(window: object, directory: Optional[str] = None) -> Optional[object]:
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
    return surface


def open_window_kind(window: object, kind_key: str) -> None:
    """Insert search row "Dialog · new form" and friends: open New form with that card focused (UX-CAT-015)."""
    card = WINDOW_KIND_CARDS.get(kind_key)
    if card is None:
        return
    surface = open_new_form_tab(window)
    focus = getattr(surface, "focus_card", None)
    if callable(focus):
        focus(card)


def attach_new_form(window: object) -> None:
    """Register the virtual tab and the File / tree callback. Menus read it later.

    The Welcome page has no extension point, so there is no Welcome-page
    button (UX-START-001).
    """
    registry = window._tab_content_registry  # type: ignore[attr-defined]
    registry.register(NewFormTabProvider(window))

    def open_new_form(directory: Optional[str] = None) -> None:
        open_new_form_tab(window, directory)

    settings_page.install()
    connections_settings.install()
    window._open_new_form = open_new_form  # type: ignore[attr-defined]
    window._open_new_form_card = lambda key: open_window_kind(window, key)  # type: ignore[attr-defined]


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
        self._saved: Dict[str, ut.TemplateInfo] = {}
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
        self._panel.template_action_requested.connect(self._template_action)
        self._reload_templates()
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

    def focus_card(self, key: str) -> None:
        self._panel.focus_card(key)

    def release(self) -> None:
        return None

    def set_directory(self, directory: Optional[str]) -> None:
        if directory:
            self._panel.set_directory(directory)
        self._panel.focus_name()

    def _create(self, key: str) -> None:
        saved = self._saved.get(key)
        if saved is not None:
            result = perform_create(
                self._host(),
                template="widget",
                stem=self._panel.stem(),
                directory=self._panel.directory(),
                saved_template=saved,
            )
        elif key == WIZARD_KEY:
            # The Wizard card is finished .ui text; create_form canonicalises it (see qtside/start/wizard.py).
            result = perform_create(
                self._host(),
                template="widget",
                stem=self._panel.stem(),
                directory=self._panel.directory(),
                ui_text=wizard_document(class_name_for_stem(self._panel.stem().strip())),
                first_widget=None,
            )
        else:
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

    def _project_root(self) -> Optional[str]:
        return self._request.project_root or None

    def _reload_templates(self) -> None:
        found = template_store.load_templates(self._project_root())
        self._saved = {info.card_key: info for info in found}
        self._panel.set_user_templates(found)

    def _template_action(self, action: str, key: str) -> None:
        """Rename, change the description or delete a saved template (UX-TMPL-004)."""
        info = self._saved.get(key)
        if info is None:
            return
        state, root = template_store.state_root(), self._project_root()
        try:
            if action == "delete":
                if not ask_delete_template(self._panel, info.title):
                    return
                ut.delete_template(info, state_root=state, project_root=root)
            elif action == "rename":
                name = ask_text(self._panel, "Rename template", "Name", info.name)
                if name is None:
                    return
                ut.rename_template(info, name, state_root=state, project_root=root)
            elif action == "describe":
                text = ask_text(self._panel, "Change description", "Description", info.description)
                if text is None:
                    return
                ut.change_description(info, text)
            else:
                return
        except ut.TemplateExists as exc:
            self._panel.show_status("A template named \u201c%s\u201d already exists." % exc.existing.name)
            return
        except ProjectOpError as exc:
            self._panel.show_status(str(exc))
            return
        self._panel.show_status("")
        self._reload_templates()
        self._panel.focus_card_near(key)

    def _from_table(self) -> None:
        root = self._request.project_root or os.getcwd()
        window = self._host()

        def add_connection() -> None:
            workflow = getattr(window, "_file_project_commands_workflow", None)
            opener = getattr(workflow, "_open_settings_dialog", None)
            if callable(opener):
                opener(page_key="connections")

        dialog = FromTableDialog(
            project_root=root,
            stem=self._panel.stem(),
            chrome=chrome_for(self._request.theme),
            date_format=locale_date_format(),
            name_reason=self._panel.name_reason,
            parent=window if isinstance(window, QWidget) else self._panel,
            add_connection=add_connection,
        )
        dialog.create_requested.connect(lambda: self._create_from_dialog(dialog))
        exec_qt(dialog)
        dialog.deleteLater()

    def _create_from_dialog(self, dialog: FromTableDialog) -> None:
        from app.features.form_builder.qtside.dialogs.table_apply import render_plans

        request = dialog.request()
        schema = dialog.schema()
        root = self._request.project_root or os.getcwd()
        if request is None or schema is None:
            self._panel.show_status(dialog.disabled_reason() or "Choose a connection")
            return
        made = render_plans(request, schema, root)
        if not made:
            self._panel.show_status(dialog.disabled_reason() or "Include at least one column")
            return
        folder = self._panel.directory()
        if not os.path.isabs(folder):
            folder = os.path.join(root, folder)
        from app.features.form_builder.engine.project.fs import OsFileSystem
        from app.features.form_builder.engine.project.names import first_name_clash

        clash = first_name_clash(folder, tuple(stem for stem, _text in made), OsFileSystem())
        if clash:
            self._panel.show_status(clash)
            return
        from app.features.form_builder.engine.project.from_table_plan import plan_forms

        planned = plan_forms(request, schema)
        kinds = {form.stem: form.kind for form in planned.forms}
        record_path = ""
        ordered = tuple(sorted(made, key=lambda item: (0 if kinds.get(item[0]) == "list" else 1, item[0])))
        for stem, text in ordered:
            result = self._create_planned(stem, text, kinds.get(stem, ""), planned, schema)
            if result.refused:
                report_status(self._panel, self._host(), result.refused)
                return
            if result.scope is not None and kinds.get(stem) != "list":
                record_path = result.scope.ui_path
            elif result.scope is not None and not record_path:
                record_path = result.scope.ui_path
        # Accept while the dialog still exists. Opening the new form can close
        # the New form tab, and the dialog was parented there.
        if dialog.wants_start_screen():
            from app.features.form_builder.engine.project.start_screen import apply_start_screen

            apply_start_screen(root, dialog)
            _reload_open_main(self._host(), root)
        if dialog.isVisible():
            dialog.accept()
        self._focus_data(record_path)
        self._reload_recents()

    def _create_planned(self, stem: str, text: str, kind: str, planned: object, schema: object) -> CreateResult:
        """Write one file and leave its undo step on the editor tab that opens."""

        from app.features.form_builder.engine.project.names import class_name_for_stem
        from app.features.form_builder.qtside.dialogs.table_apply import apply_plan, empty_form

        window = self._host()
        registry = getattr(window, "_tab_content_registry", None)
        forms = getattr(planned, "forms", ())
        plan = next((form for form in forms if form.stem == stem), None)
        on_tab = registry is not None and plan is not None
        layout = "QFormLayout" if kind == "record" else "QVBoxLayout"
        ui_text = empty_form(class_name_for_stem(stem), layout) if on_tab else text
        result = perform_create(
            window,
            template="widget",
            stem=stem,
            directory=self._panel.directory(),
            ui_text=ui_text,
            first_widget=None,
        )
        if result.refused or result.scope is None or registry is None or plan is None:
            return result
        from app.qt.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.processEvents()
        surface = registry.surface_for_path(os.path.abspath(result.scope.ui_path))
        session = getattr(surface, "session", None) if surface is not None else None
        from app.features.form_builder.engine.data.schema import Schema

        if session is None or not isinstance(schema, Schema):
            return self._write_rendered(result, text)
        try:
            apply_plan(session, plan, schema)
        except Exception:
            written = self._write_rendered(result, text)
            self._drop_empty_tab(surface, result, written)
            return written
        from app.features.form_builder.engine.project.fs import OsFileSystem
        from app.features.form_builder.engine.project.save import write_generated
        from app.features.form_builder.engine.ui4.writer import write_ui

        finished = write_ui(session.document).text
        OsFileSystem().write_bytes(result.scope.ui_path, finished.encode("utf-8"))
        write_generated(result.scope, session.document, finished.encode("utf-8"), OsFileSystem())
        mark = getattr(surface, "mark_saved", None)
        if callable(mark):
            mark(finished)
        return result

    def _drop_empty_tab(self, surface: object, result: CreateResult, written: CreateResult) -> None:
        """The tab was opened on the empty skeleton. Disk has the rendered form, or nothing.

        A later save of the empty document would overwrite the rendered file.
        Reload the tab from disk. If that fails, or the write itself failed, close the tab.
        """

        scope = result.scope
        if scope is None:
            return
        path = os.path.abspath(scope.ui_path)
        if written.refused or written.scope is None:
            self._close_tab(path)
            return
        try:
            with open(path, encoding="utf-8") as handle:
                disk = handle.read()
        except OSError:
            self._close_tab(path)
            return
        session = getattr(surface, "session", None)
        log = getattr(session, "log", None)
        execute = getattr(log, "execute", None)
        if not callable(execute):
            self._close_tab(path)
            return
        from app.features.form_builder.engine.commands.catalog import ReplaceDocument

        try:
            execute(ReplaceDocument(disk, reason="reload"))
        except Exception:
            self._close_tab(path)
            return
        mark = getattr(surface, "mark_saved", None)
        if callable(mark):
            mark(disk)

    def _close_tab(self, path: str) -> None:
        workflow = getattr(self._host(), "_editor_tab_workflow", None)
        closer = getattr(workflow, "close_tab_discarding_edits", None)
        if callable(closer):
            closer(path)

    def _write_rendered(self, result: CreateResult, text: str) -> CreateResult:
        """Replace the empty skeleton with the rendered form. Remove it if that write fails."""

        scope = result.scope
        if scope is None:
            return result
        from app.features.form_builder.engine.ids import IdAllocator
        from app.features.form_builder.engine.project.fs import OsFileSystem, ProjectOpError
        from app.features.form_builder.engine.project.save import write_generated
        from app.features.form_builder.engine.ui4.reader import read_ui
        from app.features.form_builder.engine.ui4.writer import write_ui

        fs = OsFileSystem()
        try:
            document = read_ui(text, allocator=IdAllocator()).document
            finished = write_ui(document).text
            data = finished.encode("utf-8")
            fs.write_bytes(scope.ui_path, data)
            written = write_generated(scope, document, data, fs)
            if not written.text_written and not any(item.code == "FB510" for item in written.diagnostics):
                detail = written.diagnostics[0].message if written.diagnostics else "the form could not be generated"
                raise ProjectOpError(detail)
        except Exception as exc:
            self._remove_created(result)
            reason = "The form could not be created: %s" % exc
            self._panel.show_status(reason)
            return CreateResult((), (), None, reason)
        return result

    def _remove_created(self, result: CreateResult) -> None:
        from app.features.form_builder.engine.project.fs import OsFileSystem

        fs = OsFileSystem()
        for path in result.files:
            try:
                if path and os.path.lexists(path):
                    fs.remove(path)
            except OSError:
                pass

    def _focus_data(self, path: str) -> None:
        from app.features.form_builder.qtside.inspector import TabId

        window = self._host()
        registry = getattr(window, "_tab_content_registry", None)
        if registry is None or not path:
            return
        surface = registry.surface_for_path(os.path.abspath(path))
        workbench = getattr(surface, "workbench", None)
        if workbench is None:
            return
        focus_tab = getattr(workbench, "focus_inspector_tab", None)
        focus_section = getattr(workbench, "focus_section", None)
        if callable(focus_tab):
            focus_tab(TabId.DATA)
        if callable(focus_section):
            focus_section("data")

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
        try:
            if not root:
                self._panel.set_recents(())
                return
            self._panel.set_recents(recent_entries(root, OsFileSystem()))
        except ProjectOpError as exc:
            try:
                self._panel.show_status(str(exc))
            except RuntimeError:
                return
        except RuntimeError:
            # Create closes the New form tab, and the recent list goes with it.
            return

    def _host(self) -> object:
        return self._window


def report_status(panel: object, window: object, text: str) -> None:
    """Show ``text`` on the New form panel, or on the main window once that panel is gone."""

    if wrapper_is_valid(panel):
        show = getattr(panel, "show_status", None)
        if callable(show):
            try:
                show(text)
                return
            except RuntimeError:
                pass
    status = getattr(window, "statusBar", None)
    if callable(status):
        status().showMessage(text)


def ask_delete_template(parent: QWidget, name: str) -> bool:
    """UX-TMPL-004: [Delete template] [Cancel]. Cancel is the default, so Enter alone never deletes."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle("Delete template")
    box.setText("Delete the template \u201c%s\u201d? Forms made from it don't change." % name)
    delete = box.addButton("Delete template", QMessageBox.ButtonRole.DestructiveRole)
    cancel = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel)
    box.setEscapeButton(cancel)
    exec_qt(box)
    return box.clickedButton() is delete


def ask_text(parent: QWidget, title: str, label: str, value: str) -> Optional[str]:
    """One line of text for Rename… and Change description…, or None when cancelled."""
    text, accepted = QInputDialog.getText(parent, title, label, QLineEdit.EchoMode.Normal, value)
    return text if accepted else None


def _close_start_tab(window: object, project_root: str) -> None:
    workflow = getattr(window, "_editor_tab_workflow", None)
    if workflow is None:
        return
    close = getattr(workflow, "close_tab_discarding_edits", None)
    if not callable(close):
        return
    close(new_form_tab_path(project_root), skip_close_blockers=True)
