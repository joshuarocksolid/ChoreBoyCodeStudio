"""What the window file says (CONTRACTS.md section 16.1, M6.0s stub).

Frozen values only. ``engine/project/window_file.py`` (M6.2a) reads a window
file into a ``WindowRead`` whose ``facts`` is a ``WindowFacts``; the code
bridge, the handler service, the checks and the Behavior tab all take these
types, so they can be written against them before the reader exists. Nothing
here reads a file, imports user code or parses anything.

``WindowFacts.EMPTY`` is the answer for "nothing known": a missing, refused or
unparsable file. ``status`` and ``reason`` on ``WindowRead`` say why.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Tuple

ReadStatus = Literal["ok", "missing", "refused", "syntax_error"]
MethodKind = Literal["method", "staticmethod", "classmethod", "property"]


@dataclass(frozen=True)
class MethodFacts:
    """One method of the window class, as the reader found it.

    ``line`` is the 1-based ``def`` line (the first decorator's line is not
    included), ``end_line`` the last line of its body. ``params`` are the names
    after ``self``. ``required`` counts those with no default. ``slot_types``
    are the argument types of a ``@Slot(...)`` decorator, ``None`` when the
    method has none. ``source_hash`` is the sha256 of the lines from ``def`` to
    ``end_line``, LF-normalised.
    """

    name: str
    line: int
    end_line: int
    params: Tuple[str, ...] = ()
    required: int = 0
    has_varargs: bool = False
    decorators: Tuple[str, ...] = ()
    slot_types: Optional[Tuple[str, ...]] = None
    kind: MethodKind = "method"
    body_is_empty: bool = False
    source_hash: str = ""


@dataclass(frozen=True)
class WindowFacts:
    """The window class and its methods. ``class_name`` is ``""`` when there is none.

    ``end_line`` is the class's last line (UX-CODE-005). ``indent`` is one
    indent unit as written in the file, ``blank_lines`` the blank lines the file
    puts between methods, ``newline`` the file's line ending.

    ``base_methods`` are methods of project base classes the reader could open.
    ``unread_bases`` are project bases named by ``from`` that it could not.
    """

    class_name: str = ""
    line: int = 0
    end_line: int = 0
    bases: Tuple[str, ...] = ()
    indent: str = "    "
    blank_lines: int = 1
    newline: str = "\n"
    methods: Tuple[MethodFacts, ...] = ()
    base_methods: Tuple[MethodFacts, ...] = ()
    unread_bases: Tuple[str, ...] = ()

    def method(self, name: str) -> Optional[MethodFacts]:
        for found in self.methods:
            if found.name == name:
                return found
        return None


@dataclass(frozen=True)
class WindowRead:
    """``read_window``'s result. ``line`` is the line of a refusal or syntax error, else 0.

    ``relative`` is the project path used in problem sentences. ``source`` is the
    text a stub plan edits, set only when ``status`` is ``ok``.
    """

    status: ReadStatus
    reason: str = ""
    line: int = 0
    facts: WindowFacts = WindowFacts()
    relative: str = ""
    source: Optional[str] = None


__all__ = ["MethodFacts", "MethodKind", "ReadStatus", "WindowFacts", "WindowRead"]
