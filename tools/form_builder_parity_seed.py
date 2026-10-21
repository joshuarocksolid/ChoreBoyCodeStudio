"""Extract docs/form_builder/parity.json from the research markdown once.

Refuses to overwrite an existing ledger (exit 2, file bytes unchanged). There is
no --force flag. Pass --out PATH to write a ledger somewhere else.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tools.form_builder_parity import (  # noqa: E402
    Paths,
    build,
    format_summary,
    parse_plan_wps,
    summarize,
)

P23_TEST = (
    "Opening a fixture of 400 rows paints a first screen and allows a selection. "
    "The runtime check loads the same file with QUiLoader in the preview process. "
    "The test records the time. It does not assert a number until a baseline exists."
)

WP_RULES: Tuple[Tuple[int, int, str], ...] = (
    (1, 1, "M5.6"), (2, 7, "M6.1"), (8, 12, "M5.6"),
    (13, 16, "M2.2"), (17, 22, "M3.1"), (23, 27, "M3.4"), (28, 29, "M3.1b"),
    (30, 31, "M3.1"), (32, 33, "M3.4"), (34, 34, "M3.1"), (35, 56, "M3.3"),
    (57, 123, "M4.1"), (124, 133, "M4.2"), (134, 144, "M5.1"),
    (145, 147, "M3.1b"), (148, 158, "M4.3a"), (159, 163, "M4.3b"),
    (164, 165, "M4.3c"), (166, 171, "M4.3a"),
    (172, 173, "M4.4"), (174, 175, "M5.2"), (176, 176, "M5.3"),
    (177, 181, "M5.5a"), (182, 184, "M5.5c"), (185, 193, "M5.5b"),
    (194, 198, "M5.4"), (199, 222, "M5.6"),
    (223, 223, "M1.1a"), (224, 226, "M1.1c"), (227, 228, "M1.1a"),
    (229, 256, "M1.1c"),
    (257, 266, "M1.1a"), (267, 269, "M1.1c"), (270, 274, "M1.1a"), (275, 282, "M1.1c"),
    (283, 321, "M1.1b"),
    (322, 330, "M1.3"),
)

PAIN_WP: Mapping[int, str] = {
    1: "M3.2", 2: "M3.6", 3: "M3.4", 4: "M3.2", 5: "M3.3", 6: "M6.2", 7: "M5.4",
    8: "M5.3", 9: "M5.2", 10: "M2.4", 11: "M2.5", 12: "M3.6", 13: "M5.6", 14: "M3.3",
    15: "M1.4", 16: "M6.1", 17: "M5.1", 18: "M4.3a", 19: "M3.3", 20: "M3.5", 21: "M3.2",
    22: "M6.2", 23: "M1.3", 24: "M1.2", 25: "M3.5",
}

LOGIC: Tuple[Tuple[str, str, str, str, str], ...] = (
    # (slug, title, kind, source, wp)
    ("L-discount-enables-field", "Discount check box enables a field", "scenario", "LOGIC_DESIGN.md §7.2", "M7.2"),
    ("L-line-total-live", "Line total = qty x price, live", "scenario", "LOGIC_DESIGN.md §7.3", "M7.2"),
    ("L-required-email-inline-error", "Required email with inline error label", "scenario", "LOGIC_DESIGN.md §7.4", "M7.3"),
    ("L-save-checks-then-calls", "Save checks fields, then calls the user's method", "scenario", "LOGIC_DESIGN.md §7.5", "M7.4"),
    ("L-customer-combo-lookup", "Customer combo filled from a table", "scenario", "LOGIC_DESIGN.md §7.6", "M8.3a"),
    ("L-invoice-sqlite-lines", "Invoice bound to SQLite with navigation and lines", "scenario", "LOGIC_DESIGN.md §7.7", "M8.3b"),
    ("L-logic-storage", "Dynamic-property codec, schema v1, canonical JSON", "feature", "LOGIC_DESIGN.md §6.1-6.3", "M6.0b"),
    ("L-logic-references", "Rename, copy, paste, delete keep references", "feature", "LOGIC_DESIGN.md §6.4, §2.13", "M6.0b"),
    ("L-events-list", "Events list and step lists", "feature", "LOGIC_DESIGN.md §2.2-2.4", "M6.1"),
    ("L-signal-slot-picker", "Friendly signal and slot picker", "feature", "LOGIC_DESIGN.md §3.1", "M6.1"),
    ("L-canvas-overlay", "Canvas logic overlay and arrows", "feature", "LOGIC_DESIGN.md §2.7", "M6.1"),
    ("L-handler-naming", "Handler naming", "feature", "LOGIC_DESIGN.md §3.2", "M6.2"),
    ("L-stub-and-jump", "Stub insertion and jump to code", "feature", "LOGIC_DESIGN.md §3.3", "M6.2"),
    ("L-signature-checks", "Signature and @Slot checks", "feature", "LOGIC_DESIGN.md §3.4", "M6.2"),
    ("L-runtime-connect", "How level 2 connects at run time", "feature", "LOGIC_DESIGN.md §3.5", "M6.2"),
    ("L-connect-slots-by-name", "connectSlotsByName checks", "feature", "LOGIC_DESIGN.md §3.6", "M6.2"),
    ("L-design-time-errors", "Design-time errors (FB codes in Problems)", "feature", "LOGIC_DESIGN.md §2.9", "M6.2"),
    ("L-expression-language", "Grammar, types, coercion, names, blanks", "feature", "LOGIC_DESIGN.md §4.1-4.6", "M7.1"),
    ("L-window-method-calls", "window.method() from a formula", "feature", "LOGIC_DESIGN.md §4.7", "M7.1"),
    ("L-function-library", "Function library", "feature", "LOGIC_DESIGN.md §4.8", "M7.1"),
    ("L-excel-habit-fixes", "Editor help for Excel habits", "feature", "LOGIC_DESIGN.md §4.10", "M7.1"),
    ("L-state-rules", "Enabled, visible, read-only, value, default rules", "feature", "LOGIC_DESIGN.md §2.1", "M7.2"),
    ("L-designer-roundtrip-merge", "Form edited in Qt Designer comes back", "feature", "LOGIC_DESIGN.md §6.5", "M7.2"),
    ("L-generated-logic-module", "Generated module shape, hooks, no fights with user code", "feature", "LOGIC_DESIGN.md §7.1, §7.8-7.9", "M7.2"),
    ("L-checks", "Checks (validation)", "feature", "LOGIC_DESIGN.md §4.9", "M7.3"),
    ("L-formats", "Formats", "feature", "LOGIC_DESIGN.md §4.11", "M7.3"),
    ("L-shipped-app-errors", "Run-time errors in the shipped app", "feature", "LOGIC_DESIGN.md §2.11", "M7.3"),
    ("L-action-vocabulary", "Event steps (action vocabulary)", "feature", "LOGIC_DESIGN.md §4.12", "M7.4"),
    ("L-condition-builder", "Point-and-click condition and value editors", "feature", "LOGIC_DESIGN.md §2.5", "M7.5"),
    ("L-try-mode", "Try mode without data", "feature", "LOGIC_DESIGN.md §2.10", "M7.6"),
    ("L-logic-outline-search", "Logic outline and search", "feature", "LOGIC_DESIGN.md §2.8", "M7.8"),
    ("L-logic-keyboard", "Keyboard-first logic editing", "feature", "LOGIC_DESIGN.md §2.12", "M9.3"),
    ("L-connections-manager", "Connections and credentials", "feature", "LOGIC_DESIGN.md §5.1", "M8.1"),
    ("L-form-data-source", "Form data source", "feature", "LOGIC_DESIGN.md §5.2", "M8.2"),
    ("L-field-bindings", "Field bindings", "feature", "LOGIC_DESIGN.md §5.3", "M8.2"),
    ("L-record-navigation", "Record navigation, toolbar, New, Save, Delete, Find", "feature", "LOGIC_DESIGN.md §5.5", "M8.2"),
    ("L-safe-sql", "SQL safe on PostgreSQL 9.3 and SQLite", "feature", "LOGIC_DESIGN.md §5.8", "M8.2"),
    ("L-data-panel", "Data panel", "feature", "LOGIC_DESIGN.md §2.6", "M8.2"),
    ("L-lookups", "Lookups (combos from a table)", "feature", "LOGIC_DESIGN.md §5.4", "M8.3a"),
    ("L-master-detail", "Master-detail line items", "feature", "LOGIC_DESIGN.md §5.6", "M8.3b"),
    ("L-list-search-screens", "List and search screens", "feature", "LOGIC_DESIGN.md §5.7", "M8.3c"),
    ("L-form-from-table", "Form from table", "feature", "PLAN.md M8.3d", "M8.3d"),
    ("L-try-mode-data", "Try mode for data (scratch copy, PG rollback)", "feature", "LOGIC_DESIGN.md §2.10", "M8.4"),
    ("L-eject-to-code", "Eject to code", "feature", "LOGIC_DESIGN.md §5.9", "M8.5"),
    ("L-schema-cache", "Schema helper process and cache", "feature", "PLAN.md M8.6", "M8.6"),
)

_CX_TOKEN = re.compile(r"Complexity\s+([SML])\b")
_ITEM_HEADING = re.compile(r"^###\s+(\d+)\.\s+(.+?)\s*$")
_THROUGH = re.compile(r"R3 items (\d+) through (\d+)")
_LIST = re.compile(r"R3 items (\d+(?:(?:\s*,\s*(?:and\s+)?|\s+and\s+)\d+)*)")
_ONE = re.compile(r"R3 item (\d+)")
_DETAIL = re.compile(r"^\*\*(\d+)\.\s+(.+?)\.\*\*\s*(.*)$")
_STOP = "## Where Designer's UX is weak"
_OVERLAPS = (
    "PLAN overlap: R3-145..R3-147 are M3.1b (changed-marker, reset, multi-select plumbing), not M4.3c's 145-171 blanket",
    "PLAN overlap: R3-227 (class) is M1.1a with R3-228 (widget), inside the M1.1c blanket",
    "PLAN overlap: R3-322..R3-330 are M1.3; PLAN.md M1.1c says R3 items 223-330",
)


class SeedFailure(Exception):
    """The markdown could not be turned into a ledger."""


def _split_cells(line: str) -> List[str]:
    cells: List[str] = []
    buf: List[str] = []
    index = 0
    while index < len(line):
        char = line[index]
        if char == "\\" and index + 1 < len(line) and line[index + 1] == "|":
            buf.append("|")
            index += 2
            continue
        if char == "|":
            cells.append("".join(buf).strip())
            buf = []
            index += 1
            continue
        buf.append(char)
        index += 1
    if buf:
        cells.append("".join(buf).strip())
    if cells and cells[0] == "":
        cells = cells[1:]
    if cells and cells[-1] == "":
        cells = cells[:-1]
    return cells


def _is_separator(cells: Sequence[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _header_kind(cells: Sequence[str]) -> str:
    if list(cells[:3]) == ["ID", "Entry", "Class stored"]:
        return "entry"
    if list(cells[:4]) == ["ID", "Class", "How the user gets it", "Storage"]:
        return "class_storage"
    if list(cells[:3]) == ["ID", "Shortcut", "Action"]:
        return "shortcut"
    if list(cells[:5]) == ["ID", "Name", "Parent", "What writes it", "Complexity"]:
        return "name_writes"
    if list(cells[:4]) == ["ID", "Name", "Parent", "Role"]:
        return "name_parent_role"
    if list(cells[:3]) == ["ID", "Element", "Shape"]:
        return "element"
    if list(cells[:3]) == ["ID", "Name", "Role"]:
        return "name_role"
    if list(cells[:3]) == ["ID", "Option", "Effect"]:
        return "option"
    return ""


def _cell(cells: Sequence[str], index: int, number: int) -> str:
    if index >= len(cells):
        raise SeedFailure(f"R3-{number} table row is missing a column")
    return cells[index]


def _name_and_storage(kind: str, cells: Sequence[str], number: int) -> Tuple[str, Optional[str]]:
    if kind == "shortcut":
        return _cell(cells, 1, number) + " " + _cell(cells, 2, number), None
    if kind == "option":
        return _cell(cells, 1, number), None
    if kind == "class_storage":
        return _cell(cells, 1, number), _cell(cells, 3, number)
    return _cell(cells, 1, number), _cell(cells, 2, number)


def _table_complexity(cells: Sequence[str], header: Sequence[str], widget_box: bool) -> Optional[str]:
    for cell in cells:
        match = _CX_TOKEN.search(cell)
        if match is not None:
            return match.group(1)
    if "Complexity" in header:
        index = list(header).index("Complexity")
        if index < len(cells) and cells[index] in {"S", "M", "L"}:
            return cells[index]
    if widget_box:
        return "S"
    return None


def _storage_sentence(body: str) -> Optional[str]:
    marker = "Storage is "
    index = body.find(marker)
    if index < 0:
        return None
    rest = body[index + len(marker):]
    dot = rest.find(".")
    sentence = rest if dot < 0 else rest[: dot + 1]
    sentence = " ".join(sentence.split())
    return sentence or None


def _body_complexity(body: str) -> Optional[str]:
    match = _CX_TOKEN.search(body)
    if match is None:
        return None
    return match.group(1)


def _r3_source(text: str) -> str:
    lines: List[str] = []
    for line in text.splitlines():
        if line.startswith("## ") and not line.startswith("###") and line[3:].strip() == "Where Designer's UX is weak":
            break
        if line.strip() == _STOP:
            break
        lines.append(line)
    return "\n".join(lines)


def parse_r3(text: str) -> Tuple[List[dict], List[dict]]:
    """Items 1..330 and the ordered area ranges that tile them."""
    source = _r3_source(text)
    items: List[dict] = []
    area_order: List[str] = []
    area_numbers: Dict[str, List[int]] = {}
    current_area: Optional[str] = None
    widget_box = False
    header_cells: Optional[List[str]] = None
    header_kind = ""
    lines = source.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("## ") and not line.startswith("###"):
            current_area = line[3:].strip()
            widget_box = current_area == "Widget box"
            header_cells = None
            header_kind = ""
            index += 1
            continue
        heading = _ITEM_HEADING.match(line)
        if heading is not None:
            number = int(heading.group(1))
            name = heading.group(2).strip()
            body_lines: List[str] = []
            index += 1
            while index < len(lines) and not lines[index].startswith("##"):
                body_lines.append(lines[index])
                index += 1
            body = "\n".join(body_lines)
            _note_item(
                items,
                area_order,
                area_numbers,
                current_area,
                number,
                name,
                _storage_sentence(body),
                _body_complexity(body),
                index,
            )
            continue
        if line.startswith("|"):
            cells = _split_cells(line)
            if _is_separator(cells):
                index += 1
                continue
            if cells and cells[0] == "ID":
                header_kind = _header_kind(cells)
                if not header_kind:
                    raise SeedFailure("unrecognized table header: " + " | ".join(cells))
                header_cells = cells
                index += 1
                continue
            if cells and cells[0].isdigit():
                if not header_kind or header_cells is None:
                    raise SeedFailure(f"R3-{cells[0]} table row has no header")
                number = int(cells[0])
                name, storage = _name_and_storage(header_kind, cells, number)
                complexity = _table_complexity(cells, header_cells, widget_box)
                _note_item(
                    items,
                    area_order,
                    area_numbers,
                    current_area,
                    number,
                    name,
                    storage,
                    complexity,
                    index + 1,
                )
            index += 1
            continue
        index += 1

    numbers = [item["number"] for item in items]
    missing = [number for number in range(1, 331) if number not in set(numbers)]
    duplicate = sorted({number for number in numbers if numbers.count(number) > 1})
    extra = [number for number in numbers if number < 1 or number > 330]
    if missing or duplicate or extra:
        raise SeedFailure(
            "R3 coverage missing={missing} duplicate={duplicate} extra={extra}".format(
                missing=missing,
                duplicate=duplicate,
                extra=extra,
            )
        )
    areas = []
    for name in area_order:
        nums = area_numbers[name]
        areas.append({"name": name, "first": min(nums), "last": max(nums)})
    if len(areas) != 13:
        names = ", ".join(area["name"] for area in areas)
        raise SeedFailure(f"expected 13 areas, found {len(areas)}: {names}")
    _check_area_tile(areas)
    items.sort(key=lambda item: item["number"])
    return items, areas


def _note_item(
    items: List[dict],
    area_order: List[str],
    area_numbers: Dict[str, List[int]],
    area: Optional[str],
    number: int,
    name: str,
    storage: Optional[str],
    complexity: Optional[str],
    source_line: int,
) -> None:
    if not area:
        raise SeedFailure(f"R3-{number} is outside a section")
    if not name:
        raise SeedFailure(f"R3-{number} has an empty name")
    if area not in area_numbers:
        area_order.append(area)
        area_numbers[area] = []
    area_numbers[area].append(number)
    items.append(
        {
            "number": number,
            "name": name,
            "area": area,
            "storage": storage,
            "complexity": complexity,
            "source_line": source_line,
        }
    )


def _check_area_tile(areas: Sequence[dict]) -> None:
    if not areas or areas[0]["first"] != 1 or areas[-1]["last"] != 330:
        raise SeedFailure("areas do not cover 1..330")
    for index, area in enumerate(areas):
        if area["first"] > area["last"]:
            raise SeedFailure(f"area {area['name']} has a bad range")
        if index and area["first"] != areas[index - 1]["last"] + 1:
            raise SeedFailure(
                f"areas {areas[index - 1]['name']!r} and {area['name']!r} gap or overlap"
            )


def _citations(paragraph: str) -> Tuple[str, ...]:
    spans: List[Tuple[int, int, List[int]]] = []
    occupied: List[Tuple[int, int]] = []

    def overlaps(start: int, end: int) -> bool:
        return any(not (end <= left or start >= right) for left, right in occupied)

    for match in _THROUGH.finditer(paragraph):
        start, end = int(match.group(1)), int(match.group(2))
        spans.append((match.start(), match.end(), list(range(start, end + 1))))
        occupied.append((match.start(), match.end()))
    for match in _LIST.finditer(paragraph):
        if overlaps(match.start(), match.end()):
            continue
        spans.append((match.start(), match.end(), [int(part) for part in re.findall(r"\d+", match.group(1))]))
        occupied.append((match.start(), match.end()))
    for match in _ONE.finditer(paragraph):
        if overlaps(match.start(), match.end()):
            continue
        spans.append((match.start(), match.end(), [int(match.group(1))]))
    spans.sort(key=lambda item: item[0])
    keys: List[str] = []
    seen = set()
    for _start, _end, numbers in spans:
        for number in numbers:
            key = f"R3-{number}"
            if key not in seen:
                seen.add(key)
                keys.append(key)
    return tuple(keys)


def _ranked_sentences(text: str) -> Dict[int, str]:
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip() == "## Ranked pains and the fix":
            start = index
            break
    if start is None:
        raise SeedFailure("missing ranked pains section")
    sentences: Dict[int, str] = {}
    for line in lines[start + 1:]:
        if line.startswith("**") or (line.startswith("## ") and not line.startswith("###")):
            break
        if not line.startswith("|"):
            continue
        cells = _split_cells(line)
        if not cells or not cells[0].isdigit():
            continue
        if len(cells) < 3:
            raise SeedFailure(f"pain {cells[0]} table row is missing a sentence")
        sentences[int(cells[0])] = cells[2].strip()
    return sentences


def _detail_paragraphs(text: str) -> Dict[int, Tuple[str, str]]:
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip() == "## Ranked pains and the fix":
            start = index
            break
    if start is None:
        raise SeedFailure("missing ranked pains section")
    details: Dict[int, Tuple[str, str]] = {}
    index = start + 1
    while index < len(lines):
        line = lines[index]
        if line.startswith("## ") and not line.startswith("###"):
            break
        match = _DETAIL.match(line)
        if match is None:
            index += 1
            continue
        rank = int(match.group(1))
        title = match.group(2).strip()
        parts = [match.group(3).strip()] if match.group(3).strip() else []
        index += 1
        while index < len(lines) and lines[index].strip():
            parts.append(lines[index].strip())
            index += 1
        details[rank] = (title, " ".join(parts))
    return details


def parse_pains(text: str) -> List[dict]:
    """Ranked sentence, title, Test. text, and cited R3 ids for P-1..P-25."""
    sentences = _ranked_sentences(text)
    details = _detail_paragraphs(text)
    pains: List[dict] = []
    for rank in range(1, 26):
        if rank not in sentences:
            raise SeedFailure(f"pain {rank} is missing from the ranked table")
        if rank not in details:
            raise SeedFailure(f"pain {rank} has no Test. sentence")
        title, paragraph = details[rank]
        if rank == 23:
            test = P23_TEST
        else:
            marker = "Test. "
            found = paragraph.find(marker)
            if found < 0:
                raise SeedFailure(f"pain {rank} has no Test. sentence")
            test = paragraph[found + len(marker):].strip()
            if not test:
                raise SeedFailure(f"pain {rank} has no Test. sentence")
        if rank not in PAIN_WP:
            raise SeedFailure(f"pain {rank} has no work package")
        pains.append(
            {
                "id": f"P-{rank}",
                "title": title,
                "pain": sentences[rank],
                "wp": PAIN_WP[rank],
                "r3": list(_citations(paragraph)),
                "test": test,
            }
        )
    return pains


def _assign_wp(number: int) -> str:
    found: List[str] = []
    for first, last, wp in WP_RULES:
        if first <= number <= last:
            found.append(wp)
    if len(found) != 1:
        raise SeedFailure(f"unassigned R3 id: R3-{number}")
    return found[0]


def _dump_line(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(", ", ": "))


def _emit_array(lines: List[str], key: str, rows: Sequence[dict], trailing_comma: bool) -> None:
    lines.append(f'  "{key}": [')
    for index, row in enumerate(rows):
        comma = "," if index + 1 < len(rows) else ""
        lines.append(f"    {_dump_line(row)}{comma}")
    lines.append("  ]," if trailing_comma else "  ]")


def dump_ledger(areas: Sequence[dict], r3_rows: Sequence[dict], pains: Sequence[dict], logic_rows: Sequence[dict], exempt: Sequence[str]) -> str:
    lines = ["{", '  "schema": 1,']
    _emit_array(lines, "areas", areas, True)
    _emit_array(lines, "r3", r3_rows, True)
    _emit_array(lines, "pains", pains, True)
    _emit_array(lines, "logic", logic_rows, True)
    lines.append('  "wps_without_items": [')
    for index, wp in enumerate(exempt):
        comma = "," if index + 1 < len(exempt) else ""
        lines.append(f'    "{wp}"{comma}')
    lines.append("  ]")
    lines.append("}")
    return "\n".join(lines) + "\n"


def _logic_rows() -> List[dict]:
    if len(LOGIC) != 45:
        raise SeedFailure(f"LOGIC has {len(LOGIC)} rows, expected 45")
    rows = []
    seen = set()
    for slug, title, kind, source, wp in LOGIC:
        if slug in seen:
            raise SeedFailure(f"duplicate logic slug {slug}")
        seen.add(slug)
        rows.append(
            {"id": slug, "title": title, "kind": kind, "source": source, "wp": wp}
        )
    return rows


def _validate(repo: Path, text: str):
    with tempfile.TemporaryDirectory(prefix="cbcs-parity-") as tmp:
        root = Path(tmp)
        docs = root / "docs" / "form_builder"
        docs.mkdir(parents=True)
        (docs / "parity.json").write_text(text, encoding="utf-8")
        paths = Paths(
            ledger=docs / "parity.json",
            plan=repo / "docs" / "form_builder" / "PLAN.md",
            rendered=docs / "PARITY.md",
            tests_root=repo / "tests" / "form_builder",
            repo=repo,
        )
        return build(paths)


def _publish(dest: Path, text: str) -> None:
    tmp = dest.with_name(dest.name + ".writing")
    if tmp.exists():
        tmp.unlink()
    tmp.write_text(text, encoding="utf-8")
    try:
        os.link(tmp, dest)
    except OSError:
        tmp.unlink()
        raise
    tmp.unlink()


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="form_builder_parity_seed")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(None if argv is None else list(argv))
    repo = _REPO
    dest = args.out if args.out is not None else repo / "docs" / "form_builder" / "parity.json"
    if dest.exists():
        print(f"error: refusing to overwrite {dest}", file=sys.stderr)
        return 2
    if not dest.parent.is_dir():
        print(f"error: output directory does not exist: {dest.parent}", file=sys.stderr)
        return 2
    try:
        r3_text = _read(repo / "docs" / "form_builder" / "research" / "R3_designer_parity_checklist.md")
        pain_text = _read(repo / "docs" / "form_builder" / "research" / "P_user_pain_points.md")
        plan_text = _read(repo / "docs" / "form_builder" / "PLAN.md")
    except OSError:
        return 2
    if set(PAIN_WP) != set(range(1, 26)):
        print("error: PAIN_WP must own ranks 1..25", file=sys.stderr)
        return 1
    try:
        items, areas = parse_r3(r3_text)
        pains = parse_pains(pain_text)
        logic_rows = _logic_rows()
        r3_rows = []
        owners = set()
        for item in items:
            wp = _assign_wp(item["number"])
            owners.add(wp)
            r3_rows.append(
                {
                    "id": f"R3-{item['number']}",
                    "name": item["name"],
                    "storage": item["storage"],
                    "complexity": item["complexity"],
                    "wp": wp,
                }
            )
        for pain in pains:
            owners.add(pain["wp"])
        for row in logic_rows:
            owners.add(row["wp"])
        plan_wps = parse_plan_wps(plan_text)
        plan_set = set(plan_wps)
        unknown = sorted(owners - plan_set)
        if unknown:
            raise SeedFailure("work packages not in PLAN.md: " + ", ".join(unknown))
        exempt = [wp for wp in plan_wps if wp not in owners]
        text = dump_ledger(areas, r3_rows, pains, logic_rows, exempt)
        report = _validate(repo, text)
    except SeedFailure as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if report.errors:
        for finding in report.errors:
            key = f"{finding.key}: " if finding.key else ""
            print(
                f"error: {key}{finding.code.value}: {finding.message} ({finding.where})",
                file=sys.stderr,
            )
        return 1
    null_storage = sum(1 for row in r3_rows if row["storage"] is None)
    null_complexity = sum(1 for row in r3_rows if row["complexity"] is None)
    for line in _OVERLAPS:
        print(line)
    print(f"storage null: {null_storage}  complexity null: {null_complexity}")
    try:
        _publish(dest, text)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if report.view is not None:
        sys.stdout.write(format_summary(summarize(report.view)))
    print(f"errors: {len(report.errors)}  warnings: {len(report.findings) - len(report.errors)}")
    print(f"wrote {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
