"""Your own widget classes: the project registry and the ``ast`` resolver (M5.4, UX-CUST-003, 004, 006).

Qt-free. Nothing here imports or runs project code (CONTRACTS section 10.4).
A module path such as ``widgets.till_display`` is looked up as a file under
the project root, read as text and parsed with ``ast.parse``; its top-level
classes and their base-class names are listed. Imports are not followed, so a
class whose base lives in another module is "found" with bases the check can't
judge. Results are cached by path, mtime and size.

The registry is a list of ``RegistryEntry`` stored under
``form_builder.custom_widgets`` in ``cbcs/project.json``. This module only
parses and writes that list; the caller reads and saves it (a ``RegistryStore``).
"""

from __future__ import annotations

import ast
import keyword
import os
import threading
from dataclasses import dataclass, replace
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from app.features.form_builder.engine.codegen.names import header_module
from app.features.form_builder.engine.project.fs import inside_project
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.nodes import CustomWidgetNode
from app.features.form_builder.engine.ui4.schema import HeaderDecl
from app.features.form_builder.engine.ui4.spec import NodeSpec
from app.features.form_builder.engine.ui4.values import SizeValue

SETTING = "custom_widgets"

#: The largest module file the check reads. A bigger one is treated as unreadable.
MAX_BYTES = 1_000_000
DEFAULT_SIZE = (120, 40)

# The seven lines of UX-CUST-003 (UX_SPEC 13.2.10).
SENTENCE_FOUND = "Found %s in %s."
SENTENCE_OTHER_BASE = "%s in %s is based on %s, not %s. The form may look different when it runs."
SENTENCE_NO_CLASS = "%s has no class called %s."
SENTENCE_NO_FILE = "There's no %s in this project yet. You can still use the name."
SENTENCE_BAD_MODULE = "Use a module path like widgets.till_display."
SENTENCE_BAD_CLASS = "Use a class name like TillDisplay: letters, digits and _, starting with a letter."
SENTENCE_NO_PROJECT = "This form isn't in a project, so Preview shows a stand-in."

FOUND = "found"
OTHER_BASE = "other_base"
NO_CLASS = "no_class"
NO_FILE = "no_file"
BAD_MODULE = "bad_module"
BAD_CLASS = "bad_class"
NO_PROJECT = "no_project"

#: States that stop [Use {Class}] (UX-CUST-002: not a name).
BLOCKING = frozenset({BAD_MODULE, BAD_CLASS})


def valid_class_name(text: str) -> bool:
    """Letters, digits and ``_``, starting with a letter (ASCII), and not a Python keyword."""
    return (
        bool(text)
        and text[0].isascii()
        and text[0].isalpha()
        and all(ch.isascii() and (ch.isalnum() or ch == "_") for ch in text)
        and not keyword.iskeyword(text)
    )


def module_parts(module: str) -> Optional[Tuple[str, ...]]:
    """The dotted parts of ``module``, or None when it is not a module path."""
    text = module.strip()
    if not text:
        return None
    parts = tuple(text.split("."))
    if any(not part.isidentifier() or keyword.iskeyword(part) or not part.isascii() for part in parts):
        return None
    return parts


def header_for_module(module: str) -> str:
    """``widgets.till_display`` -> ``widgets/till_display.h``, as Designer and uic expect."""
    parts = module_parts(module)
    if parts is None:
        raise ValueError("%r is not a module path" % (module,))
    return "/".join(parts) + ".h"


def module_for_header(header: str) -> Optional[str]:
    """The module a ``customwidget`` header names, or None (``header_module``)."""
    return header_module(header) if header else None


# ----------------------------------------------------------------------------- ast resolver


@dataclass(frozen=True)
class ClassFacts:
    """A top-level class as the file spells it: base names (last attribute) and line."""

    name: str
    bases: Tuple[str, ...]
    line: int


@dataclass(frozen=True)
class ModuleCheck:
    state: str
    #: Project-relative file with ``/``, or "" when there is none.
    path: str = ""
    #: The class's own base names when found.
    bases: Tuple[str, ...] = ()
    line: int = 0


_CACHE: Dict[Tuple[str, int, int], Tuple[ClassFacts, ...]] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_LIMIT = 256


def module_file(project_root: str, module: str) -> str:
    """The project-relative file for ``module`` (``a/b.py``, else ``a/b/__init__.py``), or "".

    Only names are looked at; a path that leaves the project (a symlink out) is refused.
    """
    parts = module_parts(module)
    if parts is None or not project_root:
        return ""
    base = "/".join(parts)
    for relative in (base + ".py", base + "/__init__.py"):
        full = os.path.join(project_root, *relative.split("/"))
        if os.path.isfile(full) and inside_project(full, project_root):
            return relative
    return ""


def classes_in(project_root: str, relative: str) -> Tuple[ClassFacts, ...]:
    """The top-level classes of a project file, read with ``ast`` and never run."""
    full = os.path.join(project_root, *relative.split("/"))
    try:
        info = os.stat(full)
    except OSError:
        return ()
    if info.st_size > MAX_BYTES:
        return ()
    key = (os.path.abspath(full), info.st_mtime_ns, info.st_size)
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
    if cached is not None:
        return cached
    try:
        with open(full, "rb") as handle:
            data = handle.read(MAX_BYTES + 1)
        tree = ast.parse(data, filename=relative)
    except (OSError, SyntaxError, ValueError, RecursionError, MemoryError):
        found: Tuple[ClassFacts, ...] = ()
    else:
        found = tuple(
            ClassFacts(node.name, tuple(_base_name(base) for base in node.bases), node.lineno)
            for node in tree.body
            if isinstance(node, ast.ClassDef)
        )
    with _CACHE_LOCK:
        if len(_CACHE) >= _CACHE_LIMIT:
            _CACHE.clear()
        _CACHE[key] = found
    return found


def _base_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def check_module(
    project_root: Optional[str],
    module: str,
    class_name: str,
    expected_base: str,
    classes: Optional[QtClassTable] = None,
) -> ModuleCheck:
    """UX-CUST-003. ``expected_base`` is the Qt class of the widget the class replaces."""
    if not valid_class_name(class_name):
        return ModuleCheck(BAD_CLASS)
    if module_parts(module) is None:
        return ModuleCheck(BAD_MODULE)
    if not project_root:
        return ModuleCheck(NO_PROJECT)
    relative = module_file(project_root, module)
    if not relative:
        parts = module_parts(module) or ()
        return ModuleCheck(NO_FILE, "/".join(parts) + ".py")
    for facts in classes_in(project_root, relative):
        if facts.name != class_name:
            continue
        table = classes if classes is not None else QtClassTable.shared()
        state = FOUND if _base_fits(facts.bases, expected_base, table) else OTHER_BASE
        return ModuleCheck(state, relative, facts.bases, facts.line)
    return ModuleCheck(NO_CLASS, relative)


#: Parent of each stock widget class, for when the class table has no data file.
_PARENTS: Dict[str, str] = {
    "QFrame": "QWidget", "QLabel": "QFrame", "QAbstractButton": "QWidget", "QPushButton": "QAbstractButton",
    "QToolButton": "QAbstractButton", "QCheckBox": "QAbstractButton", "QRadioButton": "QAbstractButton",
    "QCommandLinkButton": "QPushButton", "QLineEdit": "QWidget", "QAbstractScrollArea": "QFrame",
    "QTextEdit": "QAbstractScrollArea", "QPlainTextEdit": "QAbstractScrollArea", "QTextBrowser": "QTextEdit",
    "QAbstractItemView": "QAbstractScrollArea", "QListView": "QAbstractItemView", "QTableView": "QAbstractItemView",
    "QTreeView": "QAbstractItemView", "QListWidget": "QListView", "QTableWidget": "QTableView",
    "QTreeWidget": "QTreeView", "QScrollArea": "QAbstractScrollArea", "QMdiArea": "QAbstractScrollArea",
    "QAbstractSpinBox": "QWidget", "QSpinBox": "QAbstractSpinBox", "QDoubleSpinBox": "QAbstractSpinBox",
    "QDateTimeEdit": "QAbstractSpinBox", "QDateEdit": "QDateTimeEdit", "QTimeEdit": "QDateTimeEdit",
    "QComboBox": "QWidget", "QFontComboBox": "QComboBox", "QAbstractSlider": "QWidget", "QSlider": "QAbstractSlider",
    "QDial": "QAbstractSlider", "QScrollBar": "QAbstractSlider", "QProgressBar": "QWidget", "QGroupBox": "QWidget",
    "QTabWidget": "QWidget", "QStackedWidget": "QFrame", "QToolBox": "QFrame", "QSplitter": "QFrame",
    "QLCDNumber": "QFrame", "QDialog": "QWidget", "QMainWindow": "QWidget", "QWizard": "QDialog",
    "QDialogButtonBox": "QWidget", "QCalendarWidget": "QWidget", "QDockWidget": "QWidget", "QMenuBar": "QWidget",
    "QStatusBar": "QWidget", "QToolBar": "QWidget", "QMenu": "QWidget", "QKeySequenceEdit": "QWidget",
    "QOpenGLWidget": "QWidget", "QTabBar": "QWidget",
}

#: Names a file may use for a Qt base that are not in ``_PARENTS`` or the class table but are widgets.
_ROOTS = frozenset({"QWidget"})


def qt_chain(class_name: str, table: Optional[QtClassTable] = None) -> Tuple[str, ...]:
    """``class_name`` and its Qt ancestors, leaf first. Empty when it is not a stock widget class."""
    known = table if table is not None else QtClassTable.shared()
    found = tuple(info.name for info in known.chain(class_name))
    if found:
        return found
    if class_name not in _PARENTS and class_name not in _ROOTS:
        return ()
    names = [class_name]
    while names[-1] in _PARENTS and len(names) < 12:
        names.append(_PARENTS[names[-1]])
    return tuple(names)


def _base_fits(bases: Sequence[str], expected: str, table: QtClassTable) -> bool:
    """True when some base is the expected class or a subclass of it, or no base is a Qt class.

    A base the file takes from another module can't be judged without following
    imports, so a class with only such bases is accepted.
    """
    known = [base for base in bases if qt_chain(base, table)]
    if not known or not expected:
        return True
    return any(expected in qt_chain(base, table) for base in known)


def check_sentence(check: ModuleCheck, class_name: str, module: str, expected_friendly: str, base_friendly: Callable[[str], str]) -> str:
    """The check line for ``check`` (UX_SPEC 13.2.10)."""
    if check.state == FOUND:
        return SENTENCE_FOUND % (class_name, check.path)
    if check.state == OTHER_BASE:
        shown = base_friendly(_first_known(check.bases)) if check.bases else expected_friendly
        return SENTENCE_OTHER_BASE % (class_name, check.path, shown, expected_friendly)
    if check.state == NO_CLASS:
        return SENTENCE_NO_CLASS % (check.path, class_name)
    if check.state == NO_FILE:
        return SENTENCE_NO_FILE % check.path
    if check.state == BAD_MODULE:
        return SENTENCE_BAD_MODULE
    if check.state == BAD_CLASS:
        return SENTENCE_BAD_CLASS
    return SENTENCE_NO_PROJECT


def _first_known(bases: Sequence[str]) -> str:
    for base in bases:
        if qt_chain(base):
            return base
    return bases[0] if bases else ""


# ----------------------------------------------------------------------------- registry


@dataclass(frozen=True)
class RegistryEntry:
    """One class of the project (UX-CUST-006). The fields stand in for Designer's plugin interface."""

    class_name: str
    module: str
    extends: str
    container: bool = False
    description: str = ""
    #: Size on the canvas (width, height) for a stand-in, or None for the declaration's hint.
    size: Optional[Tuple[int, int]] = None
    add_page_method: str = ""
    signals: Tuple[str, ...] = ()
    slots: Tuple[str, ...] = ()

    def to_json(self) -> Dict[str, Any]:
        found: Dict[str, Any] = {
            "class": self.class_name,
            "module": self.module,
            "base": self.extends,
            "container": self.container,
        }
        if self.description:
            found["description"] = self.description
        if self.size is not None:
            found["size"] = [self.size[0], self.size[1]]
        if self.add_page_method:
            found["add_page_method"] = self.add_page_method
        if self.signals:
            found["signals"] = list(self.signals)
        if self.slots:
            found["slots"] = list(self.slots)
        return found

    @property
    def label(self) -> str:
        """The popover row: "TillDisplay · widgets.till_display"."""
        return "%s · %s" % (self.class_name, self.module)

    @property
    def header(self) -> str:
        return header_for_module(self.module)


def entry_from_json(raw: object) -> Optional[RegistryEntry]:
    """One stored entry, or None when it is not usable. Unknown keys are dropped."""
    if not isinstance(raw, Mapping):
        return None
    class_name = raw.get("class")
    module = raw.get("module")
    base = raw.get("base")
    if not (isinstance(class_name, str) and isinstance(module, str) and isinstance(base, str)):
        return None
    if not valid_class_name(class_name) or module_parts(module) is None or not base:
        return None
    size = raw.get("size")
    parsed_size: Optional[Tuple[int, int]] = None
    if (
        isinstance(size, (list, tuple))
        and len(size) == 2
        and all(isinstance(item, int) and not isinstance(item, bool) and 0 < item <= 20000 for item in size)
    ):
        parsed_size = (int(size[0]), int(size[1]))
    return RegistryEntry(
        class_name=class_name,
        module=module.strip(),
        extends=base,
        container=raw.get("container") is True,
        description=str(raw["description"]) if isinstance(raw.get("description"), str) else "",
        size=parsed_size,
        add_page_method=str(raw["add_page_method"]) if isinstance(raw.get("add_page_method"), str) else "",
        signals=_strings(raw.get("signals")),
        slots=_strings(raw.get("slots")),
    )


def _strings(raw: object) -> Tuple[str, ...]:
    if not isinstance(raw, (list, tuple)):
        return ()
    return tuple(item for item in raw if isinstance(item, str))


def parse_entries(raw: object) -> Tuple[RegistryEntry, ...]:
    """The stored list as entries. A bad entry and a repeated class are left out."""
    if not isinstance(raw, (list, tuple)):
        return ()
    found: List[RegistryEntry] = []
    seen = set()
    for item in raw:
        entry = entry_from_json(item)
        if entry is None or entry.class_name in seen:
            continue
        seen.add(entry.class_name)
        found.append(entry)
    return tuple(found)


class RegistryStore:
    """Where the list lives. The integration layer binds it to ``cbcs/project.json``."""

    def load(self) -> Any:  # pragma: no cover - interface
        raise NotImplementedError

    def save(self, value: Any) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class MemoryStore(RegistryStore):
    def __init__(self, value: Any = None) -> None:
        self.value = value

    def load(self) -> Any:
        return self.value

    def save(self, value: Any) -> None:
        self.value = value


class CustomWidgetRegistry:
    """The project's classes. Reads on every call, so another form tab's edit shows at once."""

    def __init__(self, store: RegistryStore) -> None:
        self._store = store

    def entries(self) -> Tuple[RegistryEntry, ...]:
        return parse_entries(self._store.load())

    def find(self, class_name: str) -> Optional[RegistryEntry]:
        for entry in self.entries():
            if entry.class_name == class_name:
                return entry
        return None

    def compatible(self, widget_class: str, classes: Optional[QtClassTable] = None) -> Tuple[RegistryEntry, ...]:
        """Entries based on ``widget_class`` or on a class that can stand in for it (a subclass)."""
        table = classes if classes is not None else QtClassTable.shared()
        found = []
        for entry in self.entries():
            if entry.extends == widget_class or widget_class in qt_chain(entry.extends, table):
                found.append(entry)
        return tuple(found)

    def upsert(self, entry: RegistryEntry) -> bool:
        """Add or replace ``entry``. False when nothing changed."""
        current = list(self.entries())
        for index, other in enumerate(current):
            if other.class_name == entry.class_name:
                if other == entry:
                    return False
                current[index] = entry
                break
        else:
            current.append(entry)
        self._store.save([item.to_json() for item in current])
        return True

    def remove(self, class_name: str) -> bool:
        current = [item for item in self.entries() if item.class_name != class_name]
        if len(current) == len(self.entries()):
            return False
        self._store.save([item.to_json() for item in current] or None)
        return True


# ----------------------------------------------------------------------------- declarations


def declaration_spec(entry: RegistryEntry, size: Optional[Tuple[int, int]] = None) -> NodeSpec:
    """The ``customwidget`` for ``entry`` as uic and Designer read it (UX-CUST-004).

    ``<header location="local">widgets/till_display.h</header>``; ``<container>1</container>``
    when the class holds other widgets; the entry's size hint and add-page method when it has them.
    """
    fields: List[Tuple[str, object]] = [("class_name", entry.class_name), ("extends", entry.extends)]
    fields.append(("header", HeaderDecl(entry.header, "local")))
    hint = size if size is not None else entry.size
    if hint is not None:
        fields.append(("sizehint", SizeValue(hint[0], hint[1])))
    if entry.add_page_method:
        fields.append(("addpagemethod", entry.add_page_method))
    if entry.container:
        fields.append(("container", 1))
    return NodeSpec("customwidget", None, tuple(fields))


def entry_from_declaration(node: CustomWidgetNode) -> Optional[RegistryEntry]:
    """What a form's declaration says, as an entry (a header that is not a Python module gives None)."""
    header = node.field("header")
    text = header.text if isinstance(header, HeaderDecl) else ""
    module = module_for_header(text)
    if not module or not node.class_name or not node.extends:
        return None
    hint = node.field("sizehint")
    size = (hint.width, hint.height) if isinstance(hint, SizeValue) and hint.width > 0 and hint.height > 0 else None
    method = node.field("addpagemethod")
    return RegistryEntry(
        node.class_name,
        module,
        node.extends,
        container=node.field("container") == 1,
        size=size,
        add_page_method=method if isinstance(method, str) else "",
    )


def stand_in_size(node: Optional[CustomWidgetNode], entry: Optional[RegistryEntry]) -> Tuple[int, int]:
    """The canvas size of a stand-in: the registry's, else the declaration's hint, else 120 x 40 (UX-CUST-007)."""
    if entry is not None and entry.size is not None:
        return entry.size
    if node is not None:
        hint = node.field("sizehint")
        if isinstance(hint, SizeValue) and hint.width > 0 and hint.height > 0:
            return (hint.width, hint.height)
    return DEFAULT_SIZE


def with_size(entry: RegistryEntry, size: Optional[Tuple[int, int]]) -> RegistryEntry:
    return replace(entry, size=size)


__all__ = [
    "BAD_CLASS",
    "BAD_MODULE",
    "BLOCKING",
    "ClassFacts",
    "CustomWidgetRegistry",
    "DEFAULT_SIZE",
    "FOUND",
    "MemoryStore",
    "ModuleCheck",
    "NO_CLASS",
    "NO_FILE",
    "NO_PROJECT",
    "OTHER_BASE",
    "RegistryEntry",
    "RegistryStore",
    "SETTING",
    "check_module",
    "check_sentence",
    "classes_in",
    "declaration_spec",
    "entry_from_declaration",
    "entry_from_json",
    "header_for_module",
    "module_file",
    "module_for_header",
    "module_parts",
    "parse_entries",
    "qt_chain",
    "stand_in_size",
    "valid_class_name",
    "with_size",
]
