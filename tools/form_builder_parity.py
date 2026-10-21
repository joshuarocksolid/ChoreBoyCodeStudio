"""Form-builder parity ledger: validate parity.json, derive status from test markers, render PARITY.md.

Status is never stored. It is derived on every run:
  wont_do  if the entry has an approved won't-do record
  done     if at least one proving marker names the entry
  todo     otherwise
A marker is proving when no enclosing scope carries an unconditional pytest.mark.skip or
pytest.mark.xfail. skipif does not count: form-builder tests are skipif(not Qt6) on the
PySide2 lane. Day-to-day check does not read JUnit. check --junit is the milestone gate:
every proving node id must appear (else JUNIT_GAP) and every case of that id, including
each parametrized case, must have passed (else NOT_PASSED). One passing sibling does not
hide a failing or skipped sibling. A marked row stays done when JUnit is not supplied.
"""
from __future__ import annotations

import argparse
import ast
import enum
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple, Union

R3_COUNT = 330
PAIN_COUNT = 25
MARKER_PREFIX = {"parity": "R3-", "pain": "P-", "logic": "L-"}
KEY_RE = {
    "parity": re.compile(r"R3-([1-9][0-9]*)"),
    "pain": re.compile(r"P-([1-9][0-9]*)"),
    "logic": re.compile(r"L-[a-z0-9]+(?:-[a-z0-9]+)*"),
}
WP_ROW_RE = re.compile(r"^\|\s*(M[0-9]+\.[0-9]+[a-z]?)\s*\|", re.MULTILINE)
MILESTONE_RE = re.compile(r"^(M[0-9]+)\.")
_SKIP_MARKS = frozenset({"skip", "xfail"})
_TEST_PREFIX = "tests/form_builder/"


class Code(enum.Enum):
    SCHEMA = "schema"
    R3_COVERAGE = "r3-coverage"
    AREA_TILING = "area-tiling"
    PAIN_COVERAGE = "pain-coverage"
    DUPLICATE_KEY = "duplicate-key"
    UNKNOWN_WP = "unknown-wp"
    IDLE_WP = "idle-wp"
    STALE_EXEMPTION = "stale-exemption"
    WONT_DO_UNAPPROVED = "wont-do-unapproved"
    MARKER_UNKNOWN_KEY = "marker-unknown-key"
    MARKER_BAD_ARG = "marker-bad-arg"
    MARKER_OUTSIDE_TEST = "marker-outside-test"
    MARKER_ON_WONT_DO = "marker-on-wont-do"
    TEST_PARSE = "test-parse"
    UNPROVING_MARKER = "unproving-marker"
    NOT_PASSED = "not-passed"
    JUNIT_GAP = "junit-gap"
    RENDER_STALE = "render-stale"


WARNINGS = frozenset({Code.UNPROVING_MARKER})
_CODE_ORDER = {code: index for index, code in enumerate(Code)}


@dataclass(frozen=True)
class Paths:
    ledger: Path
    plan: Path
    rendered: Path
    tests_root: Path
    repo: Path

    @classmethod
    def for_repo(cls, repo: Path) -> "Paths":
        root = Path(repo)
        docs = root / "docs" / "form_builder"
        return cls(
            ledger=docs / "parity.json",
            plan=docs / "PLAN.md",
            rendered=docs / "PARITY.md",
            tests_root=root / "tests" / "form_builder",
            repo=root,
        )


@dataclass(frozen=True)
class WontDo:
    reason: str
    approved_in: str


@dataclass(frozen=True)
class Entry:
    key: str
    title: str
    wp: str
    wont_do: Optional[WontDo]

    @property
    def milestone(self) -> str:
        match = MILESTONE_RE.match(self.wp)
        if match is None:
            return self.wp
        return match.group(1)


@dataclass(frozen=True)
class Area:
    name: str
    first: int
    last: int


@dataclass(frozen=True)
class R3Item:
    entry: Entry
    number: int
    storage: Optional[str]
    complexity: Optional[str]


@dataclass(frozen=True)
class Pain:
    entry: Entry
    rank: int
    pain: str
    test: str
    r3: Tuple[str, ...]


@dataclass(frozen=True)
class LogicFeature:
    entry: Entry
    kind: str
    source: str


@dataclass(frozen=True)
class Ledger:
    areas: Tuple[Area, ...]
    r3: Tuple[R3Item, ...]
    pains: Tuple[Pain, ...]
    logic: Tuple[LogicFeature, ...]
    wps_without_items: frozenset

    def entries(self) -> Iterator[Entry]:
        for item in self.r3:
            yield item.entry
        for pain in self.pains:
            yield pain.entry
        for feature in self.logic:
            yield feature.entry

    def area_of(self, number: int) -> Area:
        for area in self.areas:
            if area.first <= number <= area.last:
                return area
        raise KeyError(number)


@dataclass(frozen=True)
class MarkerUse:
    key: str
    node_id: str
    line: int
    proving: bool


@dataclass(frozen=True)
class Finding:
    code: Code
    key: Optional[str]
    where: str
    message: str

    @property
    def is_error(self) -> bool:
        return self.code not in WARNINGS


@dataclass(frozen=True)
class MarkerScan:
    uses: Tuple[MarkerUse, ...]
    findings: Tuple[Finding, ...]


@dataclass(frozen=True)
class Derived:
    status: str
    tests: Tuple[str, ...]


@dataclass(frozen=True)
class View:
    ledger: Ledger
    plan_wps: Tuple[str, ...]
    derived: Mapping[str, Derived]
    cited_by: Mapping[str, Tuple[str, ...]]


@dataclass(frozen=True)
class Report:
    view: Optional[View]
    findings: Tuple[Finding, ...]

    @property
    def errors(self) -> Tuple[Finding, ...]:
        return tuple(finding for finding in self.findings if finding.is_error)


@dataclass(frozen=True)
class JunitCase:
    node_id: str
    raw_name: str
    passed: bool


@dataclass(frozen=True)
class JunitOutcome:
    passed: frozenset
    seen: frozenset
    cases: Tuple[JunitCase, ...]


@dataclass(frozen=True)
class Tally:
    done: int = 0
    todo: int = 0
    wont_do: int = 0

    @property
    def total(self) -> int:
        return self.done + self.todo + self.wont_do


@dataclass(frozen=True)
class Summary:
    r3_by_area: Tuple[Tuple[Area, Tally], ...]
    by_milestone: Tuple[Tuple[str, Tally, Tally, Tally], ...]
    by_wp: Tuple[Tuple[str, Tally], ...]
    exempt_wps: Tuple[str, ...]

    def to_json(self) -> dict:
        def tally_json(tally: Tally) -> dict:
            return {
                "done": tally.done,
                "todo": tally.todo,
                "wont_do": tally.wont_do,
                "total": tally.total,
            }

        return {
            "r3_by_area": [
                {
                    "name": area.name,
                    "first": area.first,
                    "last": area.last,
                    "done": tally.done,
                    "todo": tally.todo,
                    "wont_do": tally.wont_do,
                    "total": tally.total,
                }
                for area, tally in self.r3_by_area
            ],
            "by_milestone": [
                {
                    "milestone": milestone,
                    "r3": tally_json(r3),
                    "pains": tally_json(pains),
                    "logic": tally_json(logic),
                }
                for milestone, r3, pains, logic in self.by_milestone
            ],
            "by_wp": [
                {"wp": wp, **tally_json(tally)}
                for wp, tally in self.by_wp
            ],
            "exempt_wps": list(self.exempt_wps),
        }


def _sort_findings(findings: Iterable[Finding]) -> Tuple[Finding, ...]:
    return tuple(
        sorted(
            findings,
            key=lambda finding: (
                _CODE_ORDER[finding.code],
                finding.key or "",
                finding.where,
                finding.message,
            ),
        )
    )


def _schema(findings: List[Finding], key: Optional[str], message: str) -> None:
    findings.append(Finding(Code.SCHEMA, key, "parity.json", message))


def _as_int(value: object) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _nonblank(value: object) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    return value


def _check_keys(
    obj: object,
    required: Sequence[str],
    optional: Sequence[str],
    label: str,
    findings: List[Finding],
) -> Optional[dict]:
    if not isinstance(obj, dict):
        _schema(findings, label, f"{label} must be an object")
        return None
    allowed = set(required) | set(optional)
    ok = True
    for key in obj:
        if key not in allowed:
            _schema(findings, label, f"unknown key {key!r} on {label}")
            ok = False
    for key in required:
        if key not in obj:
            _schema(findings, label, f"missing key {key!r} on {label}")
            ok = False
    if not ok:
        return None
    return obj


def _parse_wont(obj: dict, label: str, findings: List[Finding]) -> Optional[WontDo]:
    raw = obj.get("wont_do", None)
    if raw is None:
        return None
    body = _check_keys(raw, ("reason", "approved_in"), (), f"{label}.wont_do", findings)
    if body is None:
        return None
    reason = body.get("reason")
    approved = body.get("approved_in")
    if not isinstance(reason, str) or not isinstance(approved, str):
        _schema(findings, label, f"{label} won't-do reason and approved_in must be strings")
        return None
    return WontDo(reason, approved)


def _parse_entry(obj: dict, key: str, title: str, findings: List[Finding]) -> Optional[Entry]:
    wp = obj.get("wp")
    if not isinstance(wp, str):
        _schema(findings, key, f"{key} wp must be a string")
        return None
    return Entry(key=key, title=title, wp=wp, wont_do=_parse_wont(obj, key, findings))


def parse_ledger(text: str) -> Tuple[Optional[Ledger], Tuple[Finding, ...]]:
    """Strict JSON → Ledger. Unknown keys, wrong types, and duplicate keys are SCHEMA."""
    duplicates: List[str] = []

    def hook(pairs: List[Tuple[str, object]]) -> dict:
        obj: dict = {}
        for key, value in pairs:
            if key in obj:
                duplicates.append(key)
            obj[key] = value
        return obj

    try:
        data = json.loads(text, object_pairs_hook=hook)
    except json.JSONDecodeError as exc:
        return None, (
            Finding(Code.SCHEMA, None, "parity.json", f"invalid JSON: {exc}"),
        )

    if duplicates:
        key = duplicates[0]
        return None, (
            Finding(Code.SCHEMA, key, "parity.json", f"duplicate key {key!r}"),
        )

    findings: List[Finding] = []
    root = _check_keys(
        data,
        ("schema", "areas", "r3", "pains", "logic", "wps_without_items"),
        (),
        "ledger",
        findings,
    )
    if root is None:
        return None, _sort_findings(findings)
    if root.get("schema") != 1:
        _schema(findings, None, "schema must be 1")

    areas = _parse_areas(root.get("areas"), findings)
    r3_items = _parse_r3_rows(root.get("r3"), findings)
    pains = _parse_pains(root.get("pains"), findings)
    logic = _parse_logic(root.get("logic"), findings)
    exempt = _parse_exempt(root.get("wps_without_items"), findings)
    if findings:
        return None, _sort_findings(findings)
    assert areas is not None and r3_items is not None
    assert pains is not None and logic is not None and exempt is not None
    r3_sorted = tuple(sorted(r3_items, key=lambda item: item.number))
    pains_sorted = tuple(sorted(pains, key=lambda pain: pain.rank))
    return (
        Ledger(
            areas=tuple(areas),
            r3=r3_sorted,
            pains=pains_sorted,
            logic=tuple(logic),
            wps_without_items=frozenset(exempt),
        ),
        (),
    )


def _parse_areas(raw: object, findings: List[Finding]) -> Optional[List[Area]]:
    if not isinstance(raw, list):
        _schema(findings, None, "areas must be a list")
        return None
    areas: List[Area] = []
    for index, item in enumerate(raw):
        label = f"areas[{index}]"
        body = _check_keys(item, ("name", "first", "last"), (), label, findings)
        if body is None:
            continue
        name = _nonblank(body.get("name"))
        first = _as_int(body.get("first"))
        last = _as_int(body.get("last"))
        if name is None or first is None or last is None:
            _schema(findings, label, f"{label} needs a name and integer first/last")
            continue
        areas.append(Area(name, first, last))
    return areas


def _parse_r3_rows(raw: object, findings: List[Finding]) -> Optional[List[R3Item]]:
    if not isinstance(raw, list):
        _schema(findings, None, "r3 must be a list")
        return None
    items: List[R3Item] = []
    for index, item in enumerate(raw):
        label = f"r3[{index}]"
        body = _check_keys(
            item,
            ("id", "name", "storage", "complexity", "wp"),
            ("wont_do",),
            label,
            findings,
        )
        if body is None:
            continue
        key = body.get("id")
        match = KEY_RE["parity"].fullmatch(key) if isinstance(key, str) else None
        name = _nonblank(body.get("name"))
        if match is None or name is None:
            _schema(findings, str(key) if isinstance(key, str) else label, f"{label} has a bad id or name")
            continue
        storage = body.get("storage")
        if storage is not None and not isinstance(storage, str):
            _schema(findings, match.group(0), f"{match.group(0)} storage must be a string or null")
            continue
        complexity = body.get("complexity")
        if complexity is not None and complexity not in {"S", "M", "L"}:
            _schema(findings, match.group(0), f"{match.group(0)} complexity must be S, M, L, or null")
            continue
        entry = _parse_entry(body, match.group(0), name, findings)
        if entry is None:
            continue
        items.append(
            R3Item(
                entry=entry,
                number=int(match.group(1)),
                storage=storage,
                complexity=complexity,
            )
        )
    return items


def _parse_pains(raw: object, findings: List[Finding]) -> Optional[List[Pain]]:
    if not isinstance(raw, list):
        _schema(findings, None, "pains must be a list")
        return None
    pains: List[Pain] = []
    for index, item in enumerate(raw):
        label = f"pains[{index}]"
        body = _check_keys(
            item,
            ("id", "title", "pain", "wp", "r3", "test"),
            ("wont_do",),
            label,
            findings,
        )
        if body is None:
            continue
        key = body.get("id")
        match = KEY_RE["pain"].fullmatch(key) if isinstance(key, str) else None
        title = _nonblank(body.get("title"))
        pain = _nonblank(body.get("pain"))
        test = _nonblank(body.get("test"))
        cited = body.get("r3")
        if match is None or title is None or pain is None or test is None or not isinstance(cited, list):
            _schema(findings, str(key) if isinstance(key, str) else label, f"{label} has a bad id, text, or r3 list")
            continue
        keys: List[str] = []
        cited_ok = True
        for ref in cited:
            if not isinstance(ref, str) or KEY_RE["parity"].fullmatch(ref) is None:
                _schema(findings, match.group(0), f"{match.group(0)} cites a malformed R3 id")
                cited_ok = False
                break
            keys.append(ref)
        if not cited_ok:
            continue
        entry = _parse_entry(body, match.group(0), title, findings)
        if entry is None:
            continue
        pains.append(
            Pain(
                entry=entry,
                rank=int(match.group(1)),
                pain=pain,
                test=test,
                r3=tuple(keys),
            )
        )
    return pains


def _parse_logic(raw: object, findings: List[Finding]) -> Optional[List[LogicFeature]]:
    if not isinstance(raw, list):
        _schema(findings, None, "logic must be a list")
        return None
    features: List[LogicFeature] = []
    for index, item in enumerate(raw):
        label = f"logic[{index}]"
        body = _check_keys(
            item,
            ("id", "title", "kind", "source", "wp"),
            ("wont_do",),
            label,
            findings,
        )
        if body is None:
            continue
        key = body.get("id")
        match = KEY_RE["logic"].fullmatch(key) if isinstance(key, str) else None
        title = _nonblank(body.get("title"))
        source = _nonblank(body.get("source"))
        kind = body.get("kind")
        if match is None or title is None or source is None or kind not in {"scenario", "feature"}:
            _schema(findings, str(key) if isinstance(key, str) else label, f"{label} has a bad id, kind, or text")
            continue
        entry = _parse_entry(body, match.group(0), title, findings)
        if entry is None:
            continue
        features.append(LogicFeature(entry=entry, kind=kind, source=source))
    return features


def _parse_exempt(raw: object, findings: List[Finding]) -> Optional[List[str]]:
    if not isinstance(raw, list):
        _schema(findings, None, "wps_without_items must be a list")
        return None
    exempt: List[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            _schema(findings, None, "wps_without_items entries must be strings")
            continue
        exempt.append(item)
    return exempt


def parse_plan_wps(text: str) -> Tuple[str, ...]:
    """WP ids from PLAN.md table rows (first column), in document order."""
    found: List[str] = []
    seen = set()
    for match in WP_ROW_RE.finditer(text):
        wp = match.group(1)
        if wp not in seen:
            seen.add(wp)
            found.append(wp)
    return tuple(found)


def _mark_node(node: ast.AST) -> Optional[str]:
    target = node.func if isinstance(node, ast.Call) else node
    if not isinstance(target, ast.Attribute):
        return None
    mark = target.value
    if not isinstance(mark, ast.Attribute) or mark.attr != "mark":
        return None
    root = mark.value
    if not isinstance(root, ast.Name) or root.id != "pytest":
        return None
    return target.attr


def _alias_marker(node: ast.AST) -> bool:
    target = node.func if isinstance(node, ast.Call) else node
    if not isinstance(target, ast.Attribute) or target.attr not in MARKER_PREFIX:
        return False
    return _mark_node(node) is None


def _literal_str(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _expr_has_skip(expr: ast.AST) -> bool:
    if isinstance(expr, (ast.List, ast.Tuple)):
        return any(_expr_has_skip(elt) for elt in expr.elts)
    return _mark_node(expr) in _SKIP_MARKS


def _is_pytest_param(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    return (
        node.func.attr == "param"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "pytest"
    )


def _at(rel_path: str, node: ast.AST) -> str:
    return f"{rel_path}:{getattr(node, 'lineno', 0) or 0}"


def _record_marker(
    expr: ast.AST,
    *,
    node_id: str,
    proving: bool,
    is_test_scope: bool,
    rel_path: str,
    uses: List[MarkerUse],
    findings: List[Finding],
) -> None:
    if isinstance(expr, (ast.List, ast.Tuple)):
        for elt in expr.elts:
            _record_marker(
                elt,
                node_id=node_id,
                proving=proving,
                is_test_scope=is_test_scope,
                rel_path=rel_path,
                uses=uses,
                findings=findings,
            )
        return
    name = _mark_node(expr)
    if name not in MARKER_PREFIX:
        if _alias_marker(expr):
            findings.append(
                Finding(
                    Code.MARKER_BAD_ARG,
                    None,
                    _at(rel_path, expr),
                    "aliased pytest mark is not accepted; use pytest.mark",
                )
            )
        return
    if not isinstance(expr, ast.Call):
        findings.append(
            Finding(
                Code.MARKER_BAD_ARG,
                None,
                _at(rel_path, expr),
                "marker arguments must be string literals",
            )
        )
        return
    if not is_test_scope:
        findings.append(
            Finding(
                Code.MARKER_OUTSIDE_TEST,
                None,
                _at(rel_path, expr),
                "marker is outside a test function or Test class",
            )
        )
        return
    if expr.keywords or not expr.args:
        findings.append(
            Finding(
                Code.MARKER_BAD_ARG,
                None,
                _at(rel_path, expr),
                "marker arguments must be string literals",
            )
        )
        return
    for arg in expr.args:
        text = _literal_str(arg)
        if text is None or KEY_RE[name].fullmatch(text) is None:
            findings.append(
                Finding(
                    Code.MARKER_BAD_ARG,
                    text,
                    _at(rel_path, expr),
                    "marker arguments must be string literals matching the marker prefix",
                )
            )
            continue
        uses.append(MarkerUse(text, node_id, expr.lineno, proving))


def _decorator_mark_exprs(decorators: Sequence[ast.expr]) -> List[ast.expr]:
    exprs: List[ast.expr] = []
    for decorator in decorators:
        exprs.append(decorator)
        for node in ast.walk(decorator):
            if not _is_pytest_param(node):
                continue
            assert isinstance(node, ast.Call)
            for keyword in node.keywords:
                if keyword.arg == "marks" and keyword.value is not None:
                    exprs.append(keyword.value)
    return exprs


def _assigned_pytestmark(stmt: ast.stmt) -> Optional[ast.AST]:
    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
        target = stmt.targets[0]
        if isinstance(target, ast.Name) and target.id == "pytestmark":
            return stmt.value
    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
        if stmt.target.id == "pytestmark":
            return stmt.value
    return None


def _walk_body(
    body: Sequence[ast.stmt],
    rel_path: str,
    scope: Sequence[str],
    inherited_skip: bool,
    uses: List[MarkerUse],
    findings: List[Finding],
) -> None:
    # pytest collects test functions nested in if/try/with, so those bodies stay in the walk.
    for stmt in body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _handle_function(stmt, rel_path, scope, inherited_skip, uses, findings)
        elif isinstance(stmt, ast.ClassDef):
            _handle_class(stmt, rel_path, scope, inherited_skip, uses, findings)
        elif isinstance(stmt, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith)):
            _walk_body(stmt.body, rel_path, scope, inherited_skip, uses, findings)
            _walk_body(stmt.orelse, rel_path, scope, inherited_skip, uses, findings)
        elif isinstance(stmt, ast.Try):
            _walk_body(stmt.body, rel_path, scope, inherited_skip, uses, findings)
            _walk_body(stmt.orelse, rel_path, scope, inherited_skip, uses, findings)
            _walk_body(stmt.finalbody, rel_path, scope, inherited_skip, uses, findings)
            for handler in stmt.handlers:
                _walk_body(handler.body, rel_path, scope, inherited_skip, uses, findings)


def _handle_function(
    fn: Union[ast.FunctionDef, ast.AsyncFunctionDef],
    rel_path: str,
    scope: Sequence[str],
    inherited_skip: bool,
    uses: List[MarkerUse],
    findings: List[Finding],
) -> None:
    own_skip = inherited_skip or any(_expr_has_skip(dec) for dec in fn.decorator_list)
    node_id = "::".join((rel_path, *scope, fn.name))
    for expr in _decorator_mark_exprs(fn.decorator_list):
        _record_marker(
            expr,
            node_id=node_id,
            proving=not own_skip,
            is_test_scope=fn.name.startswith("test_"),
            rel_path=rel_path,
            uses=uses,
            findings=findings,
        )
    _walk_body(fn.body, rel_path, (*scope, fn.name), own_skip, uses, findings)


def _handle_class(
    cls: ast.ClassDef,
    rel_path: str,
    scope: Sequence[str],
    inherited_skip: bool,
    uses: List[MarkerUse],
    findings: List[Finding],
) -> None:
    own_skip = inherited_skip or any(_expr_has_skip(dec) for dec in cls.decorator_list)
    node_id = "::".join((rel_path, *scope, cls.name))
    for expr in _decorator_mark_exprs(cls.decorator_list):
        _record_marker(
            expr,
            node_id=node_id,
            proving=not own_skip,
            is_test_scope=cls.name.startswith("Test"),
            rel_path=rel_path,
            uses=uses,
            findings=findings,
        )
    _walk_body(cls.body, rel_path, (*scope, cls.name), own_skip, uses, findings)


def scan_source(source: str, rel_path: str) -> MarkerScan:
    """AST scan of one test file. Raises SyntaxError when the file does not parse."""
    tree = ast.parse(source, filename=rel_path, feature_version=(3, 9))
    uses: List[MarkerUse] = []
    findings: List[Finding] = []
    pytestmark_value: Optional[ast.AST] = None
    for stmt in tree.body:
        value = _assigned_pytestmark(stmt)
        if value is not None:
            pytestmark_value = value
    module_skip = pytestmark_value is not None and _expr_has_skip(pytestmark_value)
    if pytestmark_value is not None:
        _record_marker(
            pytestmark_value,
            node_id=rel_path,
            proving=not module_skip,
            is_test_scope=True,
            rel_path=rel_path,
            uses=uses,
            findings=findings,
        )
    _walk_body(tree.body, rel_path, (), module_skip, uses, findings)
    return MarkerScan(tuple(uses), tuple(findings))


def scan_markers(paths: Paths) -> MarkerScan:
    """scan_source over tests_root/**/*.py. A missing root is an empty scan."""
    root = paths.tests_root
    if not root.is_dir():
        return MarkerScan((), ())
    uses: List[MarkerUse] = []
    findings: List[Finding] = []
    files = sorted(path for path in root.rglob("*.py") if path.is_file())
    for path in files:
        rel = path.relative_to(paths.repo).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            findings.append(Finding(Code.TEST_PARSE, None, rel, str(exc)))
            continue
        try:
            scanned = scan_source(source, rel)
        except SyntaxError as exc:
            findings.append(
                Finding(
                    Code.TEST_PARSE,
                    None,
                    f"{rel}:{exc.lineno or 0}",
                    f"could not parse: {exc.msg}",
                )
            )
            continue
        uses.extend(scanned.uses)
        findings.extend(scanned.findings)
    return MarkerScan(tuple(uses), tuple(findings))


def _xml_name(tag: str) -> str:
    if tag.startswith("{"):
        return tag.rsplit("}", 1)[-1]
    return tag


def _node_id_from_junit(classname: str, raw_name: str) -> str:
    """Reverse pytest's junit classname/name back to a node id with params stripped."""
    base_name = raw_name.split("[", 1)[0]
    file_parts: List[str] = []
    class_parts: List[str] = []
    in_class = False
    for part in classname.split(".") if classname else []:
        if not in_class and part[:1].isupper():
            in_class = True
        if in_class:
            class_parts.append(part)
        else:
            file_parts.append(part)
    pieces: List[str] = []
    if file_parts:
        pieces.append("/".join(file_parts) + ".py")
    pieces.extend(class_parts)
    if base_name:
        pieces.append(base_name)
    return "::".join(pieces)


def parse_junit(text: str) -> JunitOutcome:
    """pytest --junitxml outcomes. A case passed when it has no skipped, failure, or error child."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"invalid junit XML: {exc}") from exc
    cases: List[JunitCase] = []
    for elem in root.iter():
        if _xml_name(elem.tag) != "testcase":
            continue
        classname = elem.attrib.get("classname", "")
        raw_name = elem.attrib.get("name", "")
        kinds = {_xml_name(child.tag) for child in list(elem)}
        passed = not bool({"failure", "error", "skipped"} & kinds)
        cases.append(JunitCase(_node_id_from_junit(classname, raw_name), raw_name, passed))
    case_tuple = tuple(cases)
    return JunitOutcome(
        passed=frozenset(case.node_id for case in case_tuple if case.passed),
        seen=frozenset(case.node_id for case in case_tuple),
        cases=case_tuple,
    )


def _pain_sort(key: str) -> Tuple[int, str]:
    match = KEY_RE["pain"].fullmatch(key)
    if match is None:
        return (10**9, key)
    return (int(match.group(1)), key)


def derive(ledger: Ledger, scan: MarkerScan, plan_wps: Tuple[str, ...]) -> View:
    """Status for every entry. Precedence: wont_do > done > todo."""
    uses_by_key: dict = {}
    for use in scan.uses:
        uses_by_key.setdefault(use.key, []).append(use)
    derived = {}
    for entry in ledger.entries():
        if entry.wont_do is not None:
            derived[entry.key] = Derived("wont_do", ())
            continue
        proving = sorted(
            {use.node_id for use in uses_by_key.get(entry.key, ()) if use.proving}
        )
        if proving:
            derived[entry.key] = Derived("done", tuple(proving))
        else:
            derived[entry.key] = Derived("todo", ())
    cited: dict = {}
    for pain in ledger.pains:
        for key in pain.r3:
            bucket = cited.setdefault(key, [])
            if pain.entry.key not in bucket:
                bucket.append(pain.entry.key)
    cited_by = {
        key: tuple(sorted(values, key=_pain_sort))
        for key, values in cited.items()
    }
    return View(ledger, plan_wps, derived, cited_by)


def _area_findings(areas: Sequence[Area]) -> List[Finding]:
    findings: List[Finding] = []
    if not areas or areas[0].first != 1 or areas[-1].last != R3_COUNT:
        findings.append(
            Finding(
                Code.AREA_TILING,
                None,
                "parity.json",
                f"areas must tile 1..{R3_COUNT}",
            )
        )
    for index, area in enumerate(areas):
        if area.first > area.last or area.first < 1 or area.last > R3_COUNT:
            findings.append(
                Finding(
                    Code.AREA_TILING,
                    area.name,
                    "parity.json",
                    f"area {area.name} has a bad range {area.first}-{area.last}",
                )
            )
        if index == 0:
            continue
        previous = areas[index - 1]
        if area.first != previous.last + 1:
            findings.append(
                Finding(
                    Code.AREA_TILING,
                    area.name,
                    "parity.json",
                    f"areas {previous.name!r} and {area.name!r} leave a gap or overlap",
                )
            )
    return findings


def validate(view: View, scan: MarkerScan) -> Tuple[Finding, ...]:
    """Ledger invariants plus marker-vs-ledger invariants. Scan parse findings stay on the scan."""
    ledger = view.ledger
    findings: List[Finding] = []
    counts: dict = {}
    for item in ledger.r3:
        counts[item.number] = counts.get(item.number, 0) + 1
        if item.number < 1 or item.number > R3_COUNT:
            findings.append(
                Finding(
                    Code.R3_COVERAGE,
                    item.entry.key,
                    "parity.json",
                    f"{item.entry.key} is outside 1..{R3_COUNT}",
                )
            )
    for number in range(1, R3_COUNT + 1):
        seen = counts.get(number, 0)
        if seen == 0:
            findings.append(
                Finding(Code.R3_COVERAGE, f"R3-{number}", "parity.json", f"missing R3-{number}")
            )
        elif seen > 1:
            findings.append(
                Finding(Code.R3_COVERAGE, f"R3-{number}", "parity.json", f"duplicate R3-{number}")
            )
    findings.extend(_area_findings(ledger.areas))

    pain_counts: dict = {}
    r3_keys = {item.entry.key for item in ledger.r3}
    for pain in ledger.pains:
        pain_counts[pain.rank] = pain_counts.get(pain.rank, 0) + 1
        if pain.rank < 1 or pain.rank > PAIN_COUNT:
            findings.append(
                Finding(
                    Code.PAIN_COVERAGE,
                    pain.entry.key,
                    "parity.json",
                    f"{pain.entry.key} is outside 1..{PAIN_COUNT}",
                )
            )
        for key in pain.r3:
            if key not in r3_keys:
                findings.append(
                    Finding(
                        Code.PAIN_COVERAGE,
                        pain.entry.key,
                        "parity.json",
                        f"{pain.entry.key} cites unknown {key}",
                    )
                )
    for rank in range(1, PAIN_COUNT + 1):
        seen = pain_counts.get(rank, 0)
        if seen != 1:
            findings.append(
                Finding(
                    Code.PAIN_COVERAGE,
                    f"P-{rank}",
                    "parity.json",
                    f"P-{rank} appears {seen} times",
                )
            )

    logic_seen = set()
    for feature in ledger.logic:
        if feature.entry.key in logic_seen:
            findings.append(
                Finding(
                    Code.DUPLICATE_KEY,
                    feature.entry.key,
                    "parity.json",
                    f"duplicate logic id {feature.entry.key}",
                )
            )
        logic_seen.add(feature.entry.key)

    plan_set = set(view.plan_wps)
    owners: dict = {}
    for entry in ledger.entries():
        owners.setdefault(entry.wp, []).append(entry.key)
        if entry.wp not in plan_set:
            findings.append(
                Finding(
                    Code.UNKNOWN_WP,
                    entry.key,
                    "parity.json",
                    f"{entry.key} wp {entry.wp!r} is not in PLAN.md",
                )
            )
        if entry.wont_do is not None and (
            not entry.wont_do.reason.strip() or not entry.wont_do.approved_in.strip()
        ):
            findings.append(
                Finding(
                    Code.WONT_DO_UNAPPROVED,
                    entry.key,
                    "parity.json",
                    f"{entry.key} won't-do needs a reason and an approval",
                )
            )

    for wp in sorted(ledger.wps_without_items):
        if wp not in plan_set or wp in owners:
            findings.append(
                Finding(
                    Code.STALE_EXEMPTION,
                    wp,
                    "parity.json",
                    f"{wp} is exempt but is missing from PLAN.md or already owns rows",
                )
            )
    for wp in view.plan_wps:
        if wp not in owners and wp not in ledger.wps_without_items:
            findings.append(
                Finding(
                    Code.IDLE_WP,
                    wp,
                    "PLAN.md",
                    f"{wp} owns no ledger rows and is not exempt",
                )
            )

    known = {entry.key: entry for entry in ledger.entries()}
    for use in scan.uses:
        entry = known.get(use.key)
        where = f"{use.node_id}:{use.line}"
        if entry is None:
            findings.append(
                Finding(
                    Code.MARKER_UNKNOWN_KEY,
                    use.key,
                    where,
                    f"unknown ledger key {use.key}",
                )
            )
            continue
        if entry.wont_do is not None:
            findings.append(
                Finding(
                    Code.MARKER_ON_WONT_DO,
                    use.key,
                    where,
                    f"{use.key} is won't-do and also marked",
                )
            )
            continue
        if not use.proving:
            findings.append(
                Finding(
                    Code.UNPROVING_MARKER,
                    use.key,
                    where,
                    f"{use.key} is marked on a skipped or xfailed test",
                )
            )
    return _sort_findings(findings)


def _cases_for(outcome: JunitOutcome, node_id: str) -> Tuple[JunitCase, ...]:
    prefix = node_id + "::"
    return tuple(
        case
        for case in outcome.cases
        if case.node_id == node_id or case.node_id.startswith(prefix)
    )


def junit_findings(view: View, outcome: JunitOutcome) -> Tuple[Finding, ...]:
    """Milestone gate. Rows that are not done are never checked."""
    findings: List[Finding] = []
    for entry in view.ledger.entries():
        derived = view.derived[entry.key]
        if derived.status != "done":
            continue
        for node_id in derived.tests:
            matched = _cases_for(outcome, node_id)
            if not matched:
                findings.append(
                    Finding(
                        Code.JUNIT_GAP,
                        entry.key,
                        node_id,
                        f"no junit case for {node_id}",
                    )
                )
                continue
            failed = [case for case in matched if not case.passed]
            if failed:
                names = ", ".join(case.raw_name for case in failed)
                findings.append(
                    Finding(
                        Code.NOT_PASSED,
                        entry.key,
                        node_id,
                        f"{node_id} has a case that did not pass ({names})",
                    )
                )
    return _sort_findings(findings)


def _tally_from(counts: Mapping[str, int]) -> Tally:
    return Tally(
        done=counts.get("done", 0),
        todo=counts.get("todo", 0),
        wont_do=counts.get("wont_do", 0),
    )


def _bump(counts: dict, status: str) -> None:
    counts[status] = counts.get(status, 0) + 1


def _milestone_number(milestone: str) -> int:
    match = re.match(r"^M([0-9]+)", milestone)
    if match is None:
        return 0
    return int(match.group(1))


def summarize(view: View) -> Summary:
    area_counts = {area.name: {} for area in view.ledger.areas}
    for item in view.ledger.r3:
        for area in view.ledger.areas:
            if area.first <= item.number <= area.last:
                _bump(area_counts[area.name], view.derived[item.entry.key].status)
                break
    r3_by_area = tuple(
        (area, _tally_from(area_counts[area.name]))
        for area in view.ledger.areas
    )

    buckets: dict = {}

    def bucket_for(milestone: str) -> List[dict]:
        if milestone not in buckets:
            buckets[milestone] = [{}, {}, {}]
        return buckets[milestone]

    for item in view.ledger.r3:
        _bump(bucket_for(item.entry.milestone)[0], view.derived[item.entry.key].status)
    for pain in view.ledger.pains:
        _bump(bucket_for(pain.entry.milestone)[1], view.derived[pain.entry.key].status)
    for feature in view.ledger.logic:
        _bump(bucket_for(feature.entry.milestone)[2], view.derived[feature.entry.key].status)
    milestones = tuple(
        (
            milestone,
            _tally_from(buckets[milestone][0]),
            _tally_from(buckets[milestone][1]),
            _tally_from(buckets[milestone][2]),
        )
        for milestone in sorted(buckets, key=_milestone_number)
    )

    wp_counts = {wp: {} for wp in view.plan_wps}
    for entry in view.ledger.entries():
        if entry.wp in wp_counts:
            _bump(wp_counts[entry.wp], view.derived[entry.key].status)
    by_wp = tuple((wp, _tally_from(wp_counts[wp])) for wp in view.plan_wps)
    exempt = tuple(wp for wp in view.plan_wps if wp in view.ledger.wps_without_items)
    return Summary(r3_by_area, milestones, by_wp, exempt)


def _ratio(tally: Tally) -> str:
    return f"{tally.done}/{tally.total}"


def _wrap_ids(ids: Sequence[str], width: int = 78) -> str:
    lines: List[str] = []
    current = ""
    for wp in ids:
        piece = wp if not current else current + " " + wp
        if current and len(piece) > width:
            lines.append(current)
            current = "  " + wp
        elif not current:
            current = "  " + wp
        else:
            current = piece
    if current:
        lines.append(current)
    return "\n".join(lines)


def format_summary(summary: Summary) -> str:
    labels = [
        f"  {area.name} ({area.first}-{area.last})"
        for area, _tally in summary.r3_by_area
    ]
    width = max(
        [len("R3 by area"), len("  R3 total")]
        + [len(label) for label in labels]
    )
    lines = [f"{'R3 by area':<{width}}{'done':>6}{'todo':>6}{'wont':>6}{'total':>7}"]
    totals = {"done": 0, "todo": 0, "wont_do": 0}
    for label, (_area, tally) in zip(labels, summary.r3_by_area):
        lines.append(
            f"{label:<{width}}{tally.done:>6}{tally.todo:>6}{tally.wont_do:>6}{tally.total:>7}"
        )
        totals["done"] += tally.done
        totals["todo"] += tally.todo
        totals["wont_do"] += tally.wont_do
    total = _tally_from(totals)
    lines.append(
        f"{'  R3 total':<{width}}{total.done:>6}{total.todo:>6}{total.wont_do:>6}{total.total:>7}"
    )
    lines.append("")
    lines.append(f"{'By milestone':<22}{'R3':>12}{'pains':>12}{'logic':>10}")
    for milestone, r3, pains, logic in summary.by_milestone:
        lines.append(
            f"  {milestone:<20}{_ratio(r3):>12}{_ratio(pains):>12}{_ratio(logic):>10}"
        )
    lines.append("")
    lines.append(
        f"WPs in PLAN.md with no ledger items (exempt): {len(summary.exempt_wps)}"
    )
    wrapped = _wrap_ids(summary.exempt_wps)
    if wrapped:
        lines.append(wrapped)
    return "\n".join(lines) + "\n"


def _md_cell(value: Optional[str]) -> str:
    if not value:
        return ""
    text = value.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ")
    return text.replace("|", "\\|")


def _md_row(cells: Sequence[str]) -> str:
    return "| " + " | ".join(_md_cell(cell) for cell in cells) + " |"


def _md_sep(count: int) -> str:
    return "| " + " | ".join("---" for _ in range(count)) + " |"


def _proving_cell(tests: Sequence[str]) -> str:
    if not tests:
        return ""
    shown = tests[0]
    if shown.startswith(_TEST_PREFIX):
        shown = shown[len(_TEST_PREFIX):]
    extra = len(tests) - 1
    if extra:
        return f"{shown} (+{extra})"
    return shown


def _notes(item: R3Item, view: View) -> str:
    parts: List[str] = []
    if item.entry.wont_do is not None and item.entry.wont_do.reason.strip():
        parts.append(item.entry.wont_do.reason.strip())
    cited = view.cited_by.get(item.entry.key, ())
    if cited:
        parts.append("Pain " + ", ".join(cited))
    return "; ".join(parts)


def render_markdown(view: View) -> str:
    """PARITY.md text. Byte-stable for a given view."""
    summary = summarize(view)
    lines = [
        "# Form-builder parity ledger",
        "",
        "Generated by `tools/form_builder_parity.py`. Do not edit by hand.",
        "",
        "## Summary",
        "",
        "### R3 by area",
        "",
        _md_row(["Area", "Done", "Todo", "Wont", "Total"]),
        _md_sep(5),
    ]
    for area, tally in summary.r3_by_area:
        lines.append(
            _md_row(
                [
                    f"{area.name} ({area.first}-{area.last})",
                    str(tally.done),
                    str(tally.todo),
                    str(tally.wont_do),
                    str(tally.total),
                ]
            )
        )
    lines.extend(
        [
            "",
            "### By milestone",
            "",
            _md_row(["Milestone", "R3", "Pains", "Logic"]),
            _md_sep(4),
        ]
    )
    for milestone, r3, pains, logic in summary.by_milestone:
        lines.append(_md_row([milestone, _ratio(r3), _ratio(pains), _ratio(logic)]))
    lines.extend(
        [
            "",
            f"Work packages with no ledger items: {len(summary.exempt_wps)}",
            "",
            ", ".join(summary.exempt_wps),
            "",
            "## R3",
            "",
        ]
    )
    tally_by_name = {area.name: tally for area, tally in summary.r3_by_area}
    r3_header = [
        "ID",
        "Item",
        "Area",
        ".ui storage",
        "Complexity",
        "WP",
        "Status",
        "Proving test",
        "Notes",
    ]
    for area in view.ledger.areas:
        tally = tally_by_name[area.name]
        lines.append(f"### {area.name} ({area.first}-{area.last}) — {tally.done}/{tally.total}")
        lines.append("")
        lines.append(_md_row(r3_header))
        lines.append(_md_sep(len(r3_header)))
        for item in view.ledger.r3:
            if not area.first <= item.number <= area.last:
                continue
            derived = view.derived[item.entry.key]
            lines.append(
                _md_row(
                    [
                        item.entry.key,
                        item.entry.title,
                        area.name,
                        item.storage or "",
                        item.complexity or "",
                        item.entry.wp,
                        derived.status,
                        _proving_cell(derived.tests),
                        _notes(item, view),
                    ]
                )
            )
        lines.append("")
    pain_header = ["ID", "Pain", "WP", "Status", "Proving test", "Test description"]
    lines.extend(["## Pains", "", _md_row(pain_header), _md_sep(len(pain_header))])
    for pain in view.ledger.pains:
        derived = view.derived[pain.entry.key]
        lines.append(
            _md_row(
                [
                    pain.entry.key,
                    pain.pain,
                    pain.entry.wp,
                    derived.status,
                    _proving_cell(derived.tests),
                    pain.test,
                ]
            )
        )
    lines.append("")
    logic_header = ["ID", "Feature", "Kind", "Source", "WP", "Status", "Proving test"]
    lines.extend(["## Logic", "", _md_row(logic_header), _md_sep(len(logic_header))])
    for feature in view.ledger.logic:
        derived = view.derived[feature.entry.key]
        lines.append(
            _md_row(
                [
                    feature.entry.key,
                    feature.entry.title,
                    feature.kind,
                    feature.source,
                    feature.entry.wp,
                    derived.status,
                    _proving_cell(derived.tests),
                ]
            )
        )
    lines.append("")
    return "\n".join(lines)


def build(paths: Paths, junit: Optional[Path] = None) -> Report:
    """Read the ledger, PLAN.md, and tests; derive; validate; optional junit cross-check."""
    ledger_text = paths.ledger.read_text(encoding="utf-8")
    plan_text = paths.plan.read_text(encoding="utf-8")
    ledger, parse_findings = parse_ledger(ledger_text)
    if ledger is None:
        return Report(None, _sort_findings(parse_findings))
    plan_wps = parse_plan_wps(plan_text)
    scan = scan_markers(paths)
    view = derive(ledger, scan, plan_wps)
    findings: List[Finding] = list(parse_findings)
    findings.extend(scan.findings)
    findings.extend(validate(view, scan))
    if junit is not None:
        junit_text = junit.read_text(encoding="utf-8")
        try:
            outcome = parse_junit(junit_text)
        except ValueError as exc:
            findings.append(Finding(Code.SCHEMA, None, str(junit), str(exc)))
        else:
            findings.extend(junit_findings(view, outcome))
    return Report(view, _sort_findings(findings))


def _print_findings(findings: Sequence[Finding], stream: Optional[object] = None) -> None:
    out = stream or sys.stdout
    for finding in findings:
        kind = "warning" if not finding.is_error else "error"
        key = f"{finding.key}: " if finding.key else ""
        print(
            f"{kind}: {key}{finding.code.value}: {finding.message} ({finding.where})",
            file=out,
        )


def _print_report(report: Report) -> None:
    _print_findings(report.findings)
    errors = len(report.errors)
    warnings = len(report.findings) - errors
    print(f"errors: {errors}  warnings: {warnings}")


def _cmd_status(report: Report, as_json: bool) -> int:
    if as_json:
        payload = summarize(report.view).to_json() if report.view is not None else {"view": None}
        json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        if report.findings:
            _print_findings(report.findings, sys.stderr)
        return 1 if report.errors else 0
    if report.view is not None:
        sys.stdout.write(format_summary(summarize(report.view)))
    _print_report(report)
    return 1 if report.errors else 0


def _cmd_render(paths: Paths, report: Report, check: bool) -> int:
    _print_report(report)
    if report.errors or report.view is None:
        return 1
    text = render_markdown(report.view)
    if check:
        try:
            current = paths.rendered.read_text(encoding="utf-8") if paths.rendered.is_file() else ""
        except OSError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if current != text:
            stale = Finding(
                Code.RENDER_STALE,
                None,
                paths.rendered.as_posix(),
                "PARITY.md differs from the ledger",
            )
            _print_findings((stale,))
            return 1
        return 0
    try:
        paths.rendered.write_text(text, encoding="utf-8")
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="form_builder_parity")
    parser.add_argument("--repo", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="validate the ledger and the marker scan")
    check.add_argument("--junit", type=Path, default=None)
    status = sub.add_parser("status", help="print per-area and per-milestone counts")
    status.add_argument("--json", action="store_true")
    render = sub.add_parser("render", help="write PARITY.md")
    render.add_argument("--check", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """check [--junit PATH], status [--json], render [--check]. Exit 0, 1, or 2."""
    args = _parser().parse_args(None if argv is None else list(argv))
    repo = Path(args.repo) if args.repo is not None else Path(__file__).resolve().parent.parent
    paths = Paths.for_repo(repo)
    junit = args.junit if args.command == "check" else None
    try:
        report = build(paths, junit=junit)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.command == "render":
        return _cmd_render(paths, report, check=bool(args.check))
    if args.command == "status":
        return _cmd_status(report, as_json=bool(args.json))
    _print_report(report)
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
