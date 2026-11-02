"""Password dialog for a PostgreSQL connection. The secret never goes to the child env."""

from __future__ import annotations

import os
import threading
from dataclasses import replace
from typing import Optional, Tuple

from app.bootstrap.paths import project_manifest_path, resolve_global_state_root
from app.features.form_builder.engine.data.connections import Connection
from app.features.form_builder.engine.data.machine import (
    MachineEntry,
    load_machine,
    machine_path,
    save_machine,
)
from app.project.project_manifest import load_project_manifest
from app.qt.QtCore import QObject, Qt, QThread, Signal
from app.qt.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)
from app.qt.qt_compat import enum_value, exec_qt
from app.support.preflight_paths import sanitize_project_name

# qtside cannot import integration.connection_paths, which owns the same rule.
def project_slug(project_root: str) -> str:
    """Manifest name, slugified. A missing manifest uses the directory name."""

    name = ""
    path = project_manifest_path(project_root)
    if os.path.isfile(str(path)):
        try:
            name = load_project_manifest(path).name or ""
        except Exception:
            name = ""
    if not name:
        name = os.path.basename(os.path.abspath(project_root))
    return sanitize_project_name(name)


_BRIDGE: Optional["_PromptBridge"] = None


class _PromptBridge(QObject):
    """Lives on the GUI thread. The worker emits; it does not call ``QTimer.singleShot``."""

    request = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        queued = getattr(getattr(Qt, "ConnectionType", Qt), "QueuedConnection")
        self.request.connect(self._run, queued)

    def _run(self, box: object) -> None:
        if not isinstance(box, dict):
            return
        try:
            box["secret"] = _ask_here(str(box.get("root") or ""), box.get("connection"))
        finally:
            done = box.get("done")
            if isinstance(done, threading.Event):
                done.set()


def install_secret_marshal() -> None:
    """Create the bridge on the GUI thread, before a worker calls ``ask_connection_secret``."""

    global _BRIDGE
    if _BRIDGE is not None:
        return
    app = QApplication.instance()
    if app is not None and QThread.currentThread() is not app.thread():
        return
    _BRIDGE = _PromptBridge()


def ask_connection_secret(project_root: str, connection: Connection) -> str:
    """The password, or ``""`` when the user cancels or the policy stores none."""

    app = QApplication.instance()
    if app is not None and QThread.currentThread() is not app.thread():
        bridge = _BRIDGE
        if bridge is None:
            return ""
        box = {
            "root": project_root,
            "connection": connection,
            "secret": "",
            "done": threading.Event(),
        }
        bridge.request.emit(box)
        box["done"].wait()
        secret = box.get("secret")
        return secret if isinstance(secret, str) else ""
    return _ask_here(project_root, connection)


def stored_machine_password(project_root: str, connection: Connection) -> str:
    path = _machine_file(project_root)
    loaded = load_machine(path)
    for name, entry in loaded.entries:
        if name == connection.name and isinstance(entry.password, str) and entry.password:
            return entry.password
    return ""


def remember_machine_password(project_root: str, connection_name: str, secret: str) -> None:
    path = _machine_file(project_root)
    current = load_machine(path)
    entries = []
    replaced = False
    for name, entry in current.entries:
        if name == connection_name:
            entries.append((name, replace(entry, password=secret)))
            replaced = True
        else:
            entries.append((name, entry))
    if not replaced:
        entries.append((connection_name, MachineEntry(password=secret)))
    save_machine(path, tuple(entries), project_root=project_root)


def _ask_here(project_root: str, connection: object) -> str:
    if not isinstance(connection, Connection):
        return ""
    policy = connection.password or "ask"
    if policy == "none":
        return ""
    if policy == "machine":
        stored = stored_machine_password(project_root, connection)
        if stored:
            return stored
    secret, remember = _dialog(connection, policy == "machine")
    if secret and policy == "machine" and remember:
        remember_machine_password(project_root, connection.name, secret)
    return secret


def _dialog(connection: Connection, remember: bool) -> Tuple[str, bool]:
    dialog = QDialog()
    dialog.setWindowTitle("Password")
    layout = QVBoxLayout(dialog)
    layout.addWidget(
        QLabel("Password for %s on %s" % (connection.user or "", connection.title or ""))
    )
    field = QLineEdit(dialog)
    echo = getattr(getattr(QLineEdit, "EchoMode", QLineEdit), "Password")
    field.setEchoMode(echo)
    layout.addWidget(field)
    box = None
    if remember:
        box = QCheckBox("Remember on this machine", dialog)
        layout.addWidget(box)
    standard = getattr(QDialogButtonBox, "StandardButton", QDialogButtonBox)
    buttons = QDialogButtonBox(standard.Ok | standard.Cancel, parent=dialog)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    accepted = getattr(getattr(QDialog, "DialogCode", QDialog), "Accepted")
    if enum_value(exec_qt(dialog)) != enum_value(accepted):
        return "", False
    checked = bool(box is not None and box.isChecked())
    return field.text(), checked


def _machine_file(project_root: str) -> str:
    return machine_path(str(resolve_global_state_root()), project_slug(project_root))


__all__ = [
    "ask_connection_secret",
    "install_secret_marshal",
    "project_slug",
    "remember_machine_password",
    "stored_machine_password",
]
