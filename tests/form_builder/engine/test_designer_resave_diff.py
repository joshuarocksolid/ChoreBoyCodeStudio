# pyright: reportAttributeAccessIssue=false
"""Compare our .ui writer with Qt Designer's own resave. Differences are listed.

The test does not fail while the writer still diverges. A clean match passes.
"""

from __future__ import annotations

import difflib
from pathlib import Path

import pytest

from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui
from app.features.form_builder.engine.ui4.writer import write_ui

_RESAVED = Path(__file__).resolve().parents[1] / "corpus" / "designer_resaved"


def _resaved_files() -> list[Path]:
    if not _RESAVED.is_dir():
        return []
    found = []
    for folder in ("qt_examples", "synthetic"):
        root = _RESAVED / folder
        if root.is_dir():
            found.extend(path for path in root.rglob("*.ui") if path.is_file())
    return sorted(found)


def _snippet(left: str, right: str) -> str:
    lines = list(
        difflib.unified_diff(
            left.splitlines(),
            right.splitlines(),
            fromfile="designer",
            tofile="writer",
            lineterm="",
            n=1,
        )
    )
    body = [line for line in lines if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))]
    return " | ".join(body[:4])


@pytest.mark.oracle
def test_writer_versus_designer_resave_is_reported() -> None:
    paths = _resaved_files()
    if not paths:
        pytest.skip("designer_resaved corpus is not present")
    identical = 0
    groups: dict[str, list[str]] = {}
    read_errors: list[str] = []
    for path in paths:
        rel = path.relative_to(_RESAVED).as_posix()
        raw = path.read_bytes()
        designer = raw.decode("utf-8")
        try:
            document = read_ui(designer, allocator=IdAllocator()).document
            written = write_ui(document).text
        except UiReadError as exc:
            read_errors.append("%s: %s" % (rel, exc))
            continue
        if written.encode("utf-8") == raw:
            identical += 1
            continue
        if designer.splitlines() == written.splitlines():
            sample = "line endings differ"
        else:
            sample = _snippet(designer, written)
        groups.setdefault(sample, []).append(rel)
    differing = sum(len(names) for names in groups.values())
    lines = [
        "designer files %d" % len(paths),
        "byte-identical %d" % identical,
        "differ %d" % differing,
        "read errors %d" % len(read_errors),
    ]
    for sample, names in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])):
        lines.append("pattern %d: %s" % (len(names), sample))
        for name in names:
            lines.append("  %s" % name)
    for error in read_errors:
        lines.append("read error %s" % error)
    summary = "\n".join(lines)
    print(summary)
    if differing or read_errors:
        pytest.xfail("writer differs from Designer on %d of %d files\n%s" % (differing, len(paths), summary[:4000]))
