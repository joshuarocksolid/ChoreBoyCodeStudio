# pyright: reportAttributeAccessIssue=false
"""Writer bytes against Qt Designer's own resave.

Every changed line must be named by ALLOWLIST.json. An entry that matches
nothing fails the test as well.
"""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from typing import Dict, List, NamedTuple, Sequence

import pytest

from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui
from app.features.form_builder.engine.ui4.writer import write_ui

_RESAVED = Path(__file__).resolve().parents[1] / "corpus" / "designer_resaved"
_ALLOWLIST = _RESAVED / "ALLOWLIST.json"


class AllowEntry(NamedTuple):
    file: str
    pattern: re.Pattern[str]
    appendix: str
    reason: str


def _resaved_files() -> list[Path]:
    if not _RESAVED.is_dir():
        return []
    found = []
    for folder in ("qt_examples", "synthetic"):
        root = _RESAVED / folder
        if root.is_dir():
            found.extend(path for path in root.rglob("*.ui") if path.is_file())
    return sorted(found)


def _load_allowlist() -> List[AllowEntry]:
    payload = json.loads(_ALLOWLIST.read_text(encoding="utf-8"))
    raw_entries = payload["entries"]
    if not isinstance(raw_entries, list):
        raise AssertionError("ALLOWLIST.json entries must be a list")
    loaded: List[AllowEntry] = []
    for index, item in enumerate(raw_entries):
        if not isinstance(item, dict):
            raise AssertionError("allowlist entry %d is not an object" % index)
        file_name = item.get("file")
        pattern = item.get("pattern")
        appendix = item.get("appendix")
        reason = item.get("reason")
        if not all(isinstance(value, str) and value for value in (file_name, pattern, appendix, reason)):
            raise AssertionError("allowlist entry %d needs file, pattern, appendix, and reason" % index)
        assert isinstance(file_name, str) and isinstance(pattern, str)
        assert isinstance(appendix, str) and isinstance(reason, str)
        compiled = re.compile(pattern)
        if compiled.search(""):
            raise AssertionError("allowlist entry %d pattern matches every line" % index)
        path = (_RESAVED / file_name).resolve()
        if _RESAVED.resolve() not in path.parents or not path.is_file():
            raise AssertionError("allowlist file is not in the resaved corpus: %s" % file_name)
        loaded.append(AllowEntry(file_name, compiled, appendix, reason))
    return loaded


def _changed_lines(designer: str, written: str) -> List[str]:
    if designer.splitlines() == written.splitlines():
        return ["line endings differ"]
    return [
        line
        for line in difflib.unified_diff(
            designer.splitlines(),
            written.splitlines(),
            fromfile="designer",
            tofile="writer",
            lineterm="",
        )
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]


def _summary(
    paths: Sequence[Path],
    identical: int,
    allowlisted_files: int,
    uncovered: Sequence[str],
    read_errors: Sequence[str],
    entries: Sequence[AllowEntry],
    used: Dict[int, int],
) -> str:
    unused = [entries[index].file for index in range(len(entries)) if used.get(index, 0) == 0]
    lines = [
        "designer files %d" % len(paths),
        "byte-identical %d" % identical,
        "allowlisted files %d" % allowlisted_files,
        "non-allowlisted files %d" % len(uncovered),
        "read errors %d" % len(read_errors),
        "allowlist entries %d" % len(entries),
        "allowlist used %d" % sum(1 for index in used if used[index]),
        "allowlist unused %d" % len(unused),
    ]
    for name in unused:
        lines.append("unused %s" % name)
    for item in uncovered:
        lines.append(item)
    for error in read_errors:
        lines.append("read error %s" % error)
    return "\n".join(lines)


@pytest.mark.oracle
def test_writer_matches_designer_resave() -> None:
    paths = _resaved_files()
    if not paths:
        pytest.skip("designer_resaved corpus is not present")
    entries = _load_allowlist()
    by_file: Dict[str, List[int]] = {}
    for index, entry in enumerate(entries):
        by_file.setdefault(entry.file, []).append(index)
    identical = 0
    allowlisted_files = 0
    used = {index: 0 for index in range(len(entries))}
    uncovered: List[str] = []
    read_errors: List[str] = []
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
        pending = []
        for line in _changed_lines(designer, written):
            hit = False
            for index in by_file.get(rel, ()):
                if entries[index].pattern.search(line):
                    used[index] += 1
                    hit = True
            if not hit:
                pending.append(line)
        if pending:
            uncovered.append("%s: %s" % (rel, " | ".join(pending[:6])))
        else:
            allowlisted_files += 1
    summary = _summary(paths, identical, allowlisted_files, uncovered, read_errors, entries, used)
    print(summary)
    unused = [index for index, count in used.items() if count == 0]
    assert not read_errors, summary
    assert not uncovered, summary
    assert not unused, summary


# Constructs Designer drops but Appendix E keeps. Comments are left out: only
# those inside opaque subtrees survive (section 2.3).
_KEPT = {
    "float": r"<float>",
    "script": r"<script\b",
    "widgetdata": r"<widgetdata\b",
    "propertyspecifications": r"<propertyspecifications\b",
    "images": r"<images\b",
    "addpagemethod": r"<addpagemethod\b",
    "iconset resource": r"<iconset[^>]*\bresource=",
}


def _original_files() -> List[Path]:
    corpus = _RESAVED.parent
    return sorted(
        path
        for folder in ("qt_examples", "synthetic")
        for path in (corpus / folder).rglob("*.ui")
        if "malformed" not in path.parts
    )


def test_original_corpus_keeps_what_designer_drops() -> None:
    files = _original_files()
    assert files, "original corpus is missing"
    totals = {name: 0 for name in _KEPT}
    lost = []
    for path in files:
        text = path.read_bytes().decode("utf-8-sig")
        try:
            document = read_ui(text, allocator=IdAllocator()).document
        except UiReadError:
            continue
        written = write_ui(document).text
        for name, pattern in _KEPT.items():
            before = len(re.findall(pattern, text))
            totals[name] += before
            if len(re.findall(pattern, written)) != before:
                lost.append("%s: %s" % (path.relative_to(_RESAVED.parent).as_posix(), name))
    assert lost == []
    assert [name for name, count in totals.items() if count == 0] == []


def test_iconset_alias_survives_a_save() -> None:
    text = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0"><class>F</class>'
        '<widget class="QPushButton" name="F"><property name="icon">'
        '<iconset resource="app.qrc" alias="go"><normaloff>:/go.png</normaloff>:/go.png</iconset>'
        "</property></widget></ui>\n"
    )
    written = write_ui(read_ui(text, allocator=IdAllocator()).document).text
    assert re.search(r'<iconset resource="app.qrc" alias="go">', written)
