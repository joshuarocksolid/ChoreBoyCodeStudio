"""Hostile window files (CONTRACTS 16.1, UX-CODE-006).

Two promises: no window file crashes, hangs or stalls the editor, and a stub
never moves or changes a byte of the person's code. The crash cases run in a
child process, because on Python 3.9 (ChoreBoy) the failure is a segfault.
"""

from __future__ import annotations

import ast
import os
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import List

import pytest

from app.features.form_builder.engine.codegen.window_template import plan_stub, plan_unstub
from app.features.form_builder.engine.project.handler_checks import _closest, _parse_on
from app.features.form_builder.engine.project.window_file import read_window

_ROOT = Path(__file__).resolve().parents[4]
_HEAD = "from forms.ui_x import Ui_X\n"
_INIT = "    def __init__(self):\n        self.ui = Ui_X()\n        self.ui.setupUi(self)\n"

#: Each of these crashed Python 3.9's ``ast.parse`` (segfault) or slipped
#: past the token pre-scan before the f-string field limit and the CR rule.
_HOSTILE = {
    "f-string sum": 'x = f"{' + "1+" * 200000 + '1}"\n',
    "f-string attribute chain": 'x = f"{a' + ".b" * 200000 + '}"\n',
    "f-string subscript chain": 'x = f"{a' + "[0]" * 100000 + '}"\n',
    "f-string with a quoted brace": "x = f\"{'}' + " + "1+" * 200000 + '1}"\n',
    "f-string format spec": 'x = f"{x:{' + "1+" * 200000 + '1}}"\n',
    "comment ended by a lone CR": "# c\rx = " + "1+" * 200000 + "1\n",
    "decorator call chain": "class XWindow(QWidget):\n" + _INIT + "    @d" + "()" * 998 + "\n    def f(self): pass\n",
    "assignment to a deep attribute": "class XWindow(QWidget):\n" + _INIT + "        a" + ".b" * 995 + " = Ui_X()\n",
}

_CHILD = (
    "import sys, time\n"
    "sys.setrecursionlimit(1000)\n"
    "from app.features.form_builder.engine.project.window_file import read_window\n"
    "text = sys.stdin.read()\n"
    "start = time.monotonic()\n"
    "read = read_window('/proj', 'forms/x_window.py', text=text)\n"
    "print(read.status, round(time.monotonic() - start, 2))\n"
)


@pytest.mark.parametrize("name", sorted(_HOSTILE))
def test_a_hostile_window_file_neither_crashes_nor_hangs_the_reader(name: str) -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(_ROOT)] + [p for p in sys.path if p])
    done = subprocess.run(
        [sys.executable, "-c", _CHILD],
        input=_HEAD + _HOSTILE[name],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        cwd=str(_ROOT),
    )
    assert done.returncode == 0, done.stderr[-400:]
    status, seconds = done.stdout.split()
    assert status in ("ok", "refused"), done.stdout
    assert float(seconds) < 10


def test_a_short_f_string_is_still_read() -> None:
    text = _HEAD + "class XWindow(QWidget):\n" + _INIT + '        print(f"{self.ui!r:>{10}} {{x}}")\n'
    read = read_window("/proj", "forms/x_window.py", text=text)
    assert read.status == "ok"
    assert read.facts.class_name == "XWindow"


def test_a_window_with_hundreds_of_project_bases_reads_a_few_files(tmp_path: Path) -> None:
    body = "class Base:\n" + "".join("    def m%d(self):\n        pass\n" % i for i in range(3000))
    (tmp_path / "base.py").write_text(body, encoding="utf-8")
    names = ["B%d" % i for i in range(300)]
    imports = "".join("from base import Base as %s\n" % name for name in names)
    forms = tmp_path / "forms"
    forms.mkdir()
    (forms / "x_window.py").write_text(
        imports + _HEAD + "class XWindow(%s):\n" % ", ".join(names) + _INIT, encoding="utf-8"
    )
    start = time.monotonic()
    read = read_window(str(tmp_path), "forms/x_window.py")
    assert time.monotonic() - start < 10
    assert read.status == "ok"
    assert read.facts.unread_bases, "bases past the follow limit are reported unread"


def test_editing_a_base_file_refreshes_the_cached_window(tmp_path: Path) -> None:
    (tmp_path / "base.py").write_text("class Base:\n    def old(self):\n        pass\n", encoding="utf-8")
    forms = tmp_path / "forms"
    forms.mkdir()
    (forms / "x_window.py").write_text(
        "from base import Base\n" + _HEAD + "class XWindow(Base):\n" + _INIT, encoding="utf-8"
    )
    first = read_window(str(tmp_path), "forms/x_window.py")
    assert [m.name for m in first.facts.base_methods] == ["old"]
    (tmp_path / "base.py").write_text("class Base:\n    def newer(self):\n        pass\n", encoding="utf-8")
    second = read_window(str(tmp_path), "forms/x_window.py")
    assert [m.name for m in second.facts.base_methods] == ["newer"]


def test_spelling_hints_skip_huge_method_names() -> None:
    names = tuple("w%d" % i for i in range(500))
    start = time.monotonic()
    assert _parse_on("on_" + "q_" * 200000 + "x", names) is None
    assert _closest("a" * 100000, ["a" * 100001], 2) is None
    assert time.monotonic() - start < 2


# --- Stubs never damage code -------------------------------------------------

_SEP_TRAPS = ("\x0c", "\u2028", "\x85", "\x1c")


def _random_window(rng: random.Random) -> str:
    unit = rng.choice(["    ", "  ", "\t", "\t  "])
    blank = rng.choice([1, 2])
    trap = rng.choice(_SEP_TRAPS)
    header = rng.choice(
        [
            "",
            "# -*- coding: utf-8 -*-\n",
            "# café ☕ %s\n" % trap,
            "from PySide6.QtCore import Slot\n",
        ]
    )
    lines: List[str] = [header + _HEAD]
    if rng.random() < 0.3:
        lines.append("class XWindow(\n        QWidget):\n")
    else:
        lines.append("class XWindow(QWidget):\n")
    if rng.random() < 0.4:
        lines.append(unit + '"""Doc %s with ⚙ and %s."""\n' % (trap, trap))
    lines.append(
        unit + "def __init__(self):\n"
        + unit * 2 + "self.ui = Ui_X()\n"
        + unit * 2 + "self.ui.setupUi(self)\n"
    )
    pieces = [
        lambda: unit + "def m%d(self):\n" + unit * 2 + "return 'é%s'\n",
        lambda: unit + "async def m%d(self):\n" + unit * 2 + "await x\n",
        lambda: unit + "@Slot()\n" + unit + "def m%d(self):\n" + unit * 2 + "pass\n",
        lambda: unit + "class Inner%d:\n" + unit * 2 + "def m(self):\n" + unit * 3 + "pass\n",
        lambda: unit + "# note %d " + trap + " ✓\n",
        lambda: unit + "s%d = '''a\nb " + trap + "\n'''\n",
        lambda: unit + "def m%d(self): return 1\n",
    ]
    for index in range(rng.randint(0, 5)):
        lines.append("\n" * blank)
        piece = rng.choice(pieces)()
        lines.append(piece.replace("%d", str(index)).replace("%s", trap))
    if rng.random() < 0.4:
        lines.append(unit + "# end of class\n")
    tail = rng.choice(["", "\n\nif __name__ == '__main__':\n    XWindow()\n", "\n\nclass Other:\n    pass\n"])
    text = "".join(lines) + tail
    if rng.random() < 0.3:
        text = text.rstrip("\n")
    ending = rng.choice(["\n", "\r\n", "\r"])
    return text.replace("\n", ending)


def _class_dump(text: str, skip: str = "") -> str:
    tree = ast.parse(text)
    node = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "XWindow")
    body = [item for item in node.body if not skip or getattr(item, "name", "") != skip]
    return "\n".join(ast.dump(item) for item in body)


@pytest.mark.parametrize("seed", range(300))
def test_stub_then_unstub_gives_back_the_exact_text(seed: int) -> None:
    rng = random.Random(seed)
    source = _random_window(rng)
    read = read_window("/proj", "forms/x_window.py", text=source)
    assert read.status == "ok", (read.status, read.reason, source)
    plan = plan_stub(read, method_name="go_clicked", params=("checked",), sender="go", event_words="clicked")
    assert plan.edit.start == plan.edit.end
    prefix = source[: plan.edit.start]
    assert prefix == "" or prefix.endswith(("\n", "\r")) or plan.opened_line
    updated = source[: plan.edit.start] + plan.edit.text + source[plan.edit.end :]
    tree = ast.parse(updated)
    window = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "XWindow")
    assert window.body[-1].name == "go_clicked"  # type: ignore[attr-defined]
    assert _class_dump(updated, skip="go_clicked") == _class_dump(source)
    again = read_window("/proj", "forms/x_window.py", text=updated)
    back = plan_unstub(again, "go_clicked", plan.stub_hash, plan.blank_lines, plan.opened_line)
    assert back is not None
    assert updated[: back.start] + back.text + updated[back.end :] == source


def test_a_decorator_added_above_a_stub_keeps_the_stub() -> None:
    source = _HEAD + "class XWindow(QWidget):\n" + _INIT
    read = read_window("/proj", "forms/x_window.py", text=source)
    plan = plan_stub(read, method_name="go_clicked", params=(), sender="go", event_words="clicked")
    updated = source + plan.edit.text
    decorated = updated.replace("    def go_clicked", "    @Slot()\n    def go_clicked")
    again = read_window("/proj", "forms/x_window.py", text=decorated)
    assert plan_unstub(again, "go_clicked", plan.stub_hash, plan.blank_lines, plan.opened_line) is None


def test_a_class_with_its_body_on_the_class_line_is_refused() -> None:
    source = _HEAD + "class XWindow(QWidget): ui = Ui_X(); ui.setupUi(self)\n"
    read = read_window("/proj", "forms/x_window.py", text=source)
    with pytest.raises(ValueError) as raised:
        plan_stub(read, method_name="go_clicked", params=(), sender="go", event_words="clicked")
    assert "won't change it" in str(raised.value)
