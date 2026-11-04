"""Whether Form from a table may rewrite the project's entry point.

The checkbox is on when ``main.py`` is missing or still byte-identical to the
template the project was made from. A file the person has edited stays put.
The form command log is one step per form file, so this write sits with the
forms rather than on that undo stack.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

from app.features.form_builder.engine.project.names import class_name_for_stem

_ENTRY = "main.py"


@dataclass(frozen=True)
class StartScreen:
    """The screen F5 should open, and whether the checkbox may change ``main.py``."""

    enabled: bool
    sentence: str
    module: str
    class_name: str
    relative_path: str


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


def offer(
    project_root: str,
    stem: str,
    make: str,
    template_bytes: Optional[bytes] = None,
) -> StartScreen:
    """Enabled and silent when ``main.py`` is still the template. Otherwise the sentence.

    ``template_bytes`` is ``templates/<id>/main.py``. The engine does not look
    up the application root. The dialog passes the bytes.
    """

    screen = screen_for(stem, make)
    if entry_is_stock(project_root, template_bytes):
        return screen
    sentence = (
        "main.py has your own code, so it stays as it is. "
        "To start on this screen, open %s from %s in main.py."
        % (screen.class_name, screen.relative_path)
    )
    return StartScreen(False, sentence, screen.module, screen.class_name, screen.relative_path)


def entry_is_stock(project_root: str, template_bytes: Optional[bytes] = None) -> bool:
    """True when ``main.py`` is missing or matches the template bytes."""

    path = os.path.join(project_root, _ENTRY)
    if not os.path.isfile(path):
        return True
    if template_bytes is None:
        return False
    with open(path, "rb") as handle:
        return handle.read() == template_bytes


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
