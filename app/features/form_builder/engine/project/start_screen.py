"""Whether Form from a table may rewrite the project's entry point.

The checkbox starts ticked when ``main.py`` is missing or still the blank
project placeholder. The dialog passes those placeholder bytes. A stock
template stays unticked and names the class that file already opens. A file
the person has edited stays put. The form command log is one step per form
file, so this write is not on that undo stack.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Optional

from app.features.form_builder.engine.project.names import class_name_for_stem

_ENTRY = "main.py"
_LABEL = "Open this screen when the app starts"
_WINDOW = re.compile(r"^\s*window\s*=\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(", re.MULTILINE)


@dataclass(frozen=True)
class StartScreen:
    """The screen F5 should open, and whether the checkbox may change ``main.py``."""

    enabled: bool
    sentence: str
    module: str
    class_name: str
    relative_path: str
    checked: bool = False
    label: str = _LABEL


def screen_for(stem: str, make: str) -> StartScreen:
    """The list screen when Make includes one, otherwise the record form."""

    leaf = "%s_list" % stem if make in ("list", "both") else stem
    class_name = "%sWindow" % class_name_for_stem(leaf)
    relative = "forms/%s_window.py" % leaf
    return StartScreen(
        True,
        "",
        "forms.%s_window" % leaf,
        class_name,
        relative,
    )


def main_kind(
    project_root: str,
    template_bytes: Optional[bytes] = None,
    placeholder_bytes: Optional[bytes] = None,
) -> str:
    """``missing``, ``stock``, or ``own``. Read once when the dialog opens.

    ``placeholder_bytes`` is the blank-project ``main.py``. A match counts as
    ``missing``, so the first form may replace it and the box starts ticked.
    """

    data = _entry_bytes(project_root)
    if data is None or _same_bytes(data, placeholder_bytes):
        return "missing"
    if template_bytes is not None and data == template_bytes:
        return "stock"
    return "own"


def launched_class(template_bytes: Optional[bytes]) -> str:
    """The class the stock ``main.py`` constructs, such as ``MainWindow``."""

    if not template_bytes:
        return ""
    text = template_bytes.decode("utf-8", "replace")
    found = _WINDOW.search(text)
    return "" if found is None else found.group(1)


def present(kind: str, replaces: str, stem: str, make: str) -> StartScreen:
    """The checkbox for a kind already read from disk."""

    screen = screen_for(stem, make)
    if kind == "missing":
        return StartScreen(
            True, "", screen.module, screen.class_name, screen.relative_path, True, _LABEL
        )
    if kind == "stock":
        label = _LABEL if not replaces else "%s (instead of %s)" % (_LABEL, replaces)
        return StartScreen(
            True, "", screen.module, screen.class_name, screen.relative_path, False, label
        )
    sentence = (
        "main.py has your own code, so it stays as it is. "
        "To start on this screen, open %s from %s in main.py."
        % (screen.class_name, screen.relative_path)
    )
    return StartScreen(False, sentence, screen.module, screen.class_name, screen.relative_path, False, _LABEL)


def offer(
    project_root: str,
    stem: str,
    make: str,
    template_bytes: Optional[bytes] = None,
    placeholder_bytes: Optional[bytes] = None,
) -> StartScreen:
    """The checkbox for the ``main.py`` on disk right now.

    ``template_bytes`` is ``templates/<id>/main.py``. ``placeholder_bytes`` is
    the blank-project entry. The engine does not look up either file.
    """

    kind = main_kind(project_root, template_bytes, placeholder_bytes)
    return present(kind, launched_class(template_bytes), stem, make)


def entry_is_stock(
    project_root: str,
    template_bytes: Optional[bytes] = None,
    placeholder_bytes: Optional[bytes] = None,
) -> bool:
    """True when ``main.py`` is missing or matches the bytes the caller passes."""

    data = _entry_bytes(project_root)
    if data is None or _same_bytes(data, placeholder_bytes):
        return True
    if template_bytes is None:
        return False
    return data == template_bytes


def project_template_id(project_root: str) -> str:
    """The manifest template id, or empty when it is missing or not a single name."""

    template_id = _template_id(project_root)
    if not template_id or "/" in template_id or template_id.startswith("."):
        return ""
    return template_id


def render_entry(module: str, class_name: str) -> str:
    """The Qt App ``main()`` shape, opening one screen."""

    return (
        "import sys\n"
        "from PySide.QtWidgets import QApplication\n"
        "\n"
        "from %s import %s\n"
        "\n"
        "\n"
        "def main() -> int:\n"
        "    app = QApplication.instance()\n"
        "    if app is None:\n"
        "        app = QApplication(sys.argv)\n"
        "    window = %s()\n"
        "    window.show()\n"
        '    return (getattr(app, "exec", None) or app.exec_)()\n'
        "\n"
        "\n"
        'if __name__ == "__main__":\n'
        "    raise SystemExit(main())\n"
    ) % (module, class_name, class_name)


def write_start_entry(project_root: str, module: str, class_name: str) -> str:
    """Replace ``main.py`` so the app opens ``class_name``."""

    path = os.path.join(project_root, _ENTRY)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(render_entry(module, class_name))
    return path


def apply_start_screen(project_root: str, dialog: object) -> None:
    """Write the entry when the dialog's checkbox is on. Create calls this."""

    wants = getattr(dialog, "wants_start_screen", None)
    if not callable(wants) or not wants():
        return
    module = dialog.start_module()
    class_name = dialog.start_class()
    if module and class_name:
        write_start_entry(project_root, module, class_name)


def _entry_bytes(project_root: str) -> Optional[bytes]:
    path = os.path.join(project_root, _ENTRY)
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as handle:
        return handle.read()


def _same_bytes(data: bytes, expected: Optional[bytes]) -> bool:
    return expected is not None and data == expected


def _template_id(project_root: str) -> str:
    manifest = os.path.join(project_root, "cbcs", "project.json")
    if not os.path.isfile(manifest):
        return ""
    try:
        with open(manifest, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    template = payload.get("template")
    return template if isinstance(template, str) else ""
