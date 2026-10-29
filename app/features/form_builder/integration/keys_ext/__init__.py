"""Lane key registration (M5.0s, UX-KEY-001 .. 004).

A lane adds keys by adding a module here. Modules are discovered in sorted
name order. Each one exposes ``register(registry)`` and calls
``registry.key(...)`` (or ``registry.add(FormCommand(...))``) once per key. A
module whose name starts with an underscore is a helper and is not imported.

The rows are ``FormCommand`` values, the same type as the command table in
``engine/shell_commands.py``, so a key reads the same wherever it is listed.
``collisions(shell_shortcuts)`` is what the KEY-001 test runs over every row
of the table and of this package together: a repeated key in contexts that
overlap, a key that collides with a shell shortcut, a window-manager key, a
reserved inert key, and a repeated command id. A lane never edits the table.

Order: by module name, then registration order. That only decides which of two
rows with the same key is named first in a problem line.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
import sys
from types import ModuleType
from typing import List, Mapping, Optional, Sequence, Tuple

from app.features.form_builder.engine.layout_actions import request_for
from app.features.form_builder.engine.shell_commands import (
    _WM_FORBIDDEN,  # pyright: ignore[reportPrivateUsage]
    FORM_COMMANDS,
    FORM_SHORTCUT_CATEGORY,
    INERT_SHORTCUTS,
    FormCommand,
    contexts_overlap,
    normalize_form_shortcut,
    shell_command_contexts,
)

logger = logging.getLogger(__name__)


class KeyRegistry:
    def __init__(self) -> None:
        self._rows: List[Tuple[str, FormCommand]] = []

    def add(self, command: FormCommand, *, module: str = "") -> None:
        self._rows.append((module, command))

    def key(
        self,
        command_id: str,
        label: str,
        shortcut: str,
        contexts: Tuple[str, ...],
        *,
        menu: Tuple[str, ...] = (),
        available: bool = False,
        kind: str = "new",
        shell_action_id: str = "",
        module: str = "",
    ) -> None:
        """One key row. ``available`` stays False until the gesture exists, as in the table."""
        self.add(
            FormCommand(
                command_id=command_id,
                label=label,
                shortcut=shortcut,
                contexts=contexts,
                menu_path=menu,
                available=available or request_for(command_id) is not None,
                kind=kind,
                shell_action_id=shell_action_id,
            ),
            module=module,
        )

    def scope(self, module: str) -> "_ModuleScope":
        return _ModuleScope(self, module)

    def commands(self) -> Tuple[FormCommand, ...]:
        ordered = sorted(enumerate(self._rows), key=lambda pair: (pair[1][0], pair[0]))
        return tuple(command for _index, (_module, command) in ordered)


class _ModuleScope:
    def __init__(self, registry: KeyRegistry, module: str) -> None:
        self._registry = registry
        self._module = module

    def add(self, command: FormCommand) -> None:
        self._registry.add(command, module=self._module)

    def key(
        self,
        command_id: str,
        label: str,
        shortcut: str,
        contexts: Tuple[str, ...],
        *,
        menu: Tuple[str, ...] = (),
        available: bool = False,
        kind: str = "new",
        shell_action_id: str = "",
    ) -> None:
        self._registry.key(
            command_id,
            label,
            shortcut,
            contexts,
            menu=menu,
            available=available,
            kind=kind,
            shell_action_id=shell_action_id,
            module=self._module,
        )


def load_keys(*packages: ModuleType) -> KeyRegistry:
    registry = KeyRegistry()
    for package in packages:
        for info in sorted(pkgutil.iter_modules(package.__path__), key=lambda found: found.name):
            if info.name.startswith("_"):
                continue
            try:
                module = importlib.import_module("%s.%s" % (package.__name__, info.name))
                register = getattr(module, "register", None)
                if callable(register):
                    register(registry.scope(module.__name__))
            except Exception:
                logger.exception("form key module %s failed", info.name)
    return registry


_DEFAULT: Optional[KeyRegistry] = None


def default_registry() -> KeyRegistry:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = load_keys(sys.modules[__name__])
    return _DEFAULT


def extra_commands(registry: Optional[KeyRegistry] = None) -> Tuple[FormCommand, ...]:
    """The lanes' rows, after the command table's."""
    return (registry or default_registry()).commands()


def all_commands(registry: Optional[KeyRegistry] = None) -> Tuple[FormCommand, ...]:
    return FORM_COMMANDS + extra_commands(registry)


def extra_shortcut_rows(registry: Optional[KeyRegistry] = None) -> Tuple[Tuple[str, str, str, str], ...]:
    """``(action id, label, shortcut, category)`` for the shell's shortcut list, like ``shortcut_rows``.

    Only ``new`` rows with a key, and one row per key text: a key the table or
    an earlier lane row already lists is left out, as ``registered_commands`` does.
    """
    seen = {
        normalize_form_shortcut(command.shortcut)
        for command in FORM_COMMANDS
        if command.kind == "new" and command.shortcut
    }
    rows = []
    for command in extra_commands(registry):
        if command.kind != "new" or not command.shortcut:
            continue
        key = normalize_form_shortcut(command.shortcut)
        if key in seen:
            continue
        seen.add(key)
        rows.append((command.command_id, command.label, command.shortcut, FORM_SHORTCUT_CATEGORY))
    return tuple(rows)


def collisions(
    shell_shortcuts: Mapping[str, str],
    registry: Optional[KeyRegistry] = None,
) -> Tuple[str, ...]:
    """Problems with the lanes' rows against the table, each other and the shell.

    ``shell_shortcuts`` maps a shell action id to its portable key text, as in
    ``shortcut_collisions``. Empty means KEY-001 holds for the whole table.
    """
    extra = extra_commands(registry)
    problems: List[str] = []
    known = {command.command_id for command in FORM_COMMANDS}
    inert = {normalize_form_shortcut(key) for key in INERT_SHORTCUTS}
    earlier: List[FormCommand] = [
        command for command in FORM_COMMANDS if command.kind == "new" and command.shortcut
    ]
    for command in extra:
        if command.command_id in known:
            problems.append("%s is already a row of the command table or of another module" % command.command_id)
        known.add(command.command_id)
        key = normalize_form_shortcut(command.shortcut)
        if not key:
            continue
        if key in _WM_FORBIDDEN:
            problems.append("%s uses forbidden key %s" % (command.command_id, key))
        if key in inert:
            problems.append("%s uses %s, which the form designer reserves as inert" % (command.command_id, key))
        if command.kind != "new":
            continue
        for other in earlier:
            if normalize_form_shortcut(other.shortcut) == key and contexts_overlap(command.contexts, other.contexts):
                problems.append("%s and %s both use %s" % (other.command_id, command.command_id, key))
        for action_id, shell_key in shell_shortcuts.items():
            if normalize_form_shortcut(shell_key) != key or command.shell_action_id == action_id:
                continue
            if contexts_overlap(command.contexts, shell_command_contexts(action_id)):
                problems.append("%s collides with %s on %s" % (command.command_id, action_id, key))
        earlier.append(command)
    return tuple(problems)


__all__: Sequence[str] = [
    "KeyRegistry",
    "all_commands",
    "collisions",
    "default_registry",
    "extra_commands",
    "extra_shortcut_rows",
    "load_keys",
]
