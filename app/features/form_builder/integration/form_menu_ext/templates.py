"""Form > Save as template… (UX-TMPL-001, UX-M5-010).

Opens the popover under the tab toolbar. Saving writes the template folder
(``engine/project/user_templates.py``); the files are not on the form's undo
stack, and the toast says where the template went.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.qt.QtCore import QBuffer, QByteArray, QIODevice, QPoint, Qt
from app.qt.QtWidgets import QMessageBox, QWidget

from app.features.form_builder.engine.project import user_templates as ut
from app.features.form_builder.engine.project.fs import ProjectOpError
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.integration import template_store
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.integration.form_menu_ext import FormMenuItem
from app.features.form_builder.qtside.dialogs.save_template import SaveTemplatePopover
from app.qt.qt_compat import exec_qt
from app.shell.theme_tokens import tokens_from_palette

COMMAND_ID = "form.action.saveAsTemplate"
THUMBNAIL_SIZE = (200, 120)

SAVED_TOAST = "Saved the template “%s”. It's on the New form tab."


def default_name(surface: Any) -> str:
    """The window title, else the file name in words (UX-TMPL-001)."""
    session = surface.session
    title = session.document.root.prop("windowTitle")
    if title is not None and isinstance(title.value, StringValue) and title.value.text.strip():
        return title.value.text.strip()
    stem = re.sub(r"\.ui$", "", str(session.path).replace("\\", "/").rsplit("/", 1)[-1])
    words = " ".join(part for part in stem.replace("_", " ").split())
    return words[:1].upper() + words[1:] if words else "My form"


def project_root_of(surface: Any) -> Optional[str]:
    scope = getattr(surface.session, "scope", None)
    root = getattr(scope, "project_root", None)
    return str(root) if root and getattr(scope, "kind", "external") != "external" else None


def ask_replace(parent: QWidget, name: str) -> bool:
    """UX-TMPL-001: Replace the template “{name}”? [Replace] [Cancel]. Cancel is the default."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle("Save as template")
    box.setText("Replace the template “%s”?" % name)
    replace = box.addButton("Replace", QMessageBox.ButtonRole.AcceptRole)
    cancel = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel)
    box.setEscapeButton(cancel)
    exec_qt(box)
    return box.clickedButton() is replace


def thumbnail_png(surface: Any) -> bytes:
    """The canvas page at 200 x 120 without overlays, as PNG bytes. Empty when there is no page to draw."""
    page = surface.page_widget()
    if page is None or page.width() < 1 or page.height() < 1:
        return b""
    picture = page.grab()
    if picture.isNull():
        return b""
    scaled = picture.scaled(
        THUMBNAIL_SIZE[0], THUMBNAIL_SIZE[1], Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
    )
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    scaled.save(buffer, "PNG")
    buffer.close()
    return bytes(data.data())


def save_now(surface: Any, name: str, description: str, scope: str, *, replace: bool = False) -> Optional[ut.TemplateInfo]:
    """Write the template and toast. Asks before replacing one with the same name; None when nothing was saved."""
    root = project_root_of(surface)
    session = surface.session
    try:
        info = ut.save_template(
            scope=scope,
            state_root=template_store.state_root(),
            project_root=root,
            name=name,
            description=description,
            ui_text=session.text,
            ui_path=str(session.path),
            thumbnail=thumbnail_png(surface),
            replace=replace,
        )
    except ut.TemplateExists as exists:
        if replace or not ask_replace(surface, exists.existing.name):
            return None
        return save_now(surface, name, description, scope, replace=True)
    except ProjectOpError as exc:
        surface.show_plain(str(exc))
        return None
    surface.show_plain(SAVED_TOAST % info.name)
    return info


def open_popover(
    surface: Any,
    *,
    name: Optional[str] = None,
    description: str = "",
    scope: Optional[str] = None,
) -> SaveTemplatePopover:
    """The popover under the tab toolbar. Saving runs ``save_now``; a declined Replace brings it back."""
    root = project_root_of(surface)
    chosen_scope = scope or template_store.default_scope()
    tokens = getattr(surface, "_tokens", None) or tokens_from_palette(surface.palette())

    def commit(final_name: str, final_description: str, final_scope: str) -> None:
        if save_now(surface, final_name, final_description, final_scope) is None and _name_taken(
            surface, final_name, final_scope
        ):
            open_popover(surface, name=final_name, description=final_description, scope=final_scope)

    popover = SaveTemplatePopover(
        surface,
        chrome_for(tokens),
        name=name if name is not None else default_name(surface),
        description=description,
        scope=chosen_scope,
        project_available=root is not None,
        on_save=commit,
    )
    popover.open_at(_anchor(surface, popover))
    return popover


def _name_taken(surface: Any, name: str, scope: str) -> bool:
    try:
        taken = ut.find_by_name(
            ut.list_templates(template_store.state_root(), project_root_of(surface)), name, scope
        )
    except OSError:
        return False
    return taken is not None


def _anchor(surface: Any, popover: QWidget) -> QPoint:
    bar = surface.findChild(QWidget, "formBuilder.toolbar")
    if bar is not None:
        corner = bar.mapToGlobal(QPoint(16, bar.height() + 4))
    else:
        corner = surface.mapToGlobal(QPoint(16, 40))
    return corner


def _run(surface: Any) -> None:
    open_popover(surface)


def _offered(surface: Any) -> bool:
    return getattr(surface, "session", None) is not None


def register(registry: object) -> None:
    registry.add(  # type: ignore[attr-defined]
        FormMenuItem(COMMAND_ID, ("Save as template…",), _run, offered=_offered)
    )
