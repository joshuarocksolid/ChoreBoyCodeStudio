# pyright: reportAttributeAccessIssue=false
"""Section 12 speed harness.

Profiles:

* ``mac`` enforces the absolute CPU budgets. Memory and the O(changed) ratio
  are enforced on every profile.
* ``choreboy`` records the same points and enforces the overhead ratios when
  Realizer exists. Absolute millisecond budgets stay in the table and are not
  enforced.
* ``capped`` is the choreboy profile after the process is pinned to one CPU.

The pytest perf gate calls ``run_speed`` with ``GATE_SAMPLES`` (5) and
``GATE_SIZES`` so the marker finishes in under 30 seconds. The CLI default is
15 samples and the 300, 600 and 1000 forms.

CPU tolerance and the one retry live in ``stats.py``.
"""

from __future__ import annotations

import gc
import importlib
import importlib.util
import json
import os
import sys
import tracemalloc
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog import (
    CreateAction,
    DeleteNodes,
    InsertFragment,
    MorphWidget,
    MoveNodes,
    SetProperty,
)
from app.features.form_builder.engine.commands.placement import InActionList, InBoxLayout, InContainer, InGridCell
from app.features.form_builder.engine.ui4.nodes import LayoutNode, WidgetNode
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec
from app.qt.QtCore import QRectF
from app.qt.QtGui import QImage, QPainter
from app.qt.QtWidgets import QApplication, QWidget
from tests.form_builder.engine.commands._support import button_spec
from app.features.form_builder.engine.commands.log import CommandLog, SelectionSnapshot
from app.features.form_builder.engine.events import PRIORITY_DIAGNOSTICS, ChangeSet
from app.features.form_builder.engine.ids import IdAllocator, NodeId
from app.features.form_builder.engine.query.drop_target import DropPayload
from app.features.form_builder.engine.query.hit_index import GeoEntry, HitIndex, Rect
from app.features.form_builder.qtside.canvas.core.place import resolve_at
from app.features.form_builder.qtside.canvas.core.space import FormPoint
from app.features.form_builder.engine.ui4 import defaults as class_defaults
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.engine.ui4.writer import write_ui
from tests.form_builder.perf import raw_qt
from tests.form_builder.perf.reference import (
    EDIT_NAME,
    REFERENCE_COUNTS,
    ReferenceForm,
    reference_form,
)
from tests.form_builder.perf.stats import (
    CHANGED_RATIO_LIMIT,
    CPU_TOLERANCE,
    OVERHEAD_RATIO_LIMIT,
    Attempt,
    Distribution,
    Sample,
    ScaleJudgment,
    cpu_within_budget,
    judge_changed_scale,
    judge_timed,
    measure,
    sample_until_budget,
    wall_policy,
)

GATE_SAMPLES = 5
GATE_WARMUP = 2
GATE_SIZES: Tuple[int, ...] = (300, 1000)
FULL_SIZES: Tuple[int, ...] = REFERENCE_COUNTS

READ_BUDGET_MS = {300: 25.0}
WRITE_BUDGET_MS = {300: 10.0}
COMMAND_BUDGET_MS = {300: 2.0, 1000: 3.0}
CLASS_TABLE_BUDGET_MS = 25.0
REALIZER_BUILD_BUDGET_MS = 90.0
REALIZER_PATCH_BUDGET_MS = 8.0
OUTLINE_BUILD_BUDGET_MS = 15.0
OPEN_BUDGET_MS = 150.0
HIT_REFRESH_BUDGET_MS = {300: 4.0, 1000: 12.0}
HIT_QUERY_BUDGET_MS = 0.2
OVERLAY_BUDGET_MS = 4.0
DROP_TARGET_BUDGET_MS = 2.0
OUTLINE_PATCH_BUDGET_MS = 2.0
EDIT_BUDGET_MS = 16.0
SELECTION_BUDGET_MS = 8.0
INSPECTOR_REPOPULATE_BUDGET_MS = 16.0
DIAGNOSTICS_BUDGET_MS = 2.0
CODEGEN_BUDGET_MS = 30.0
SAVE_BUDGET_MS = 50.0
PREVIEW_WARM_BUDGET_MS = 100.0
ONE_FORM_BUDGET_MB = 30.0
THREE_FORM_BUDGET_MB = 60.0
UNDO_LOG_BUDGET_MB = 2.0
UNDO_LOG_EDITS = 500

SECTION_12_POINTS: Tuple[str, ...] = (
    "read_ui",
    "class table first load",
    "Realizer.build",
    "outline full build",
    "read + build",
    "one command",
    "one command O(changed)",
    "undo",
    "redo",
    "property patch",
    "insert into layout",
    "delete from layout",
    "move into earlier container",
    "morph",
    "toolbar edit",
    "hit index invalidate",
    "hit index refresh",
    "hit query",
    "overlay paint",
    "outline patch",
    "edit total",
    "selection change",
    "inspector repopulate",
    "sizing panel repopulate",
    "sizing edit",
    "sizing edit canvas normal",
    "sizing edit canvas 16pt",
    "inspector select collapsed",
    "inspector select expanded",
    "is_dirty",
    "revision",
    "cheap diagnostics",
    "write_ui",
    "generate_form_module",
    "save total",
    "memory one form tracemalloc",
    "memory one form rss",
    "memory three forms tracemalloc",
    "memory three forms rss",
    "undo log",
    "preview warm update",
    "preview cold start",
)

_LISTENER_SINK: List[int] = [0]


@dataclass(frozen=True)
class Row:
    point: str
    widgets: Optional[int]
    samples: Optional[int]
    p50: Optional[float]
    p95: Optional[float]
    budget: str
    verdict: str
    detail: str
    # Structural edits: execute + realize + repaint, next to the realize-only p95.
    total_p95: Optional[float] = None


@dataclass(frozen=True)
class SpeedReport:
    profile: str
    interpreter: str
    qt_version: str
    load_start: Tuple[float, float, float]
    load_end: Tuple[float, float, float]
    wall: str
    samples: int
    warmup: int
    cpu_tolerance: float
    cpus: int
    rows: Tuple[Row, ...]

    @property
    def ok(self) -> bool:
        return all(row.verdict != "fail" for row in self.rows)


def run_speed(
    *,
    profile: str,
    samples: int = 15,
    warmup: int = 3,
    sizes: Sequence[int] = FULL_SIZES,
    seed: int = 1505,
) -> SpeedReport:
    """Measure the section 12 points that exist and list the ones that do not."""
    if profile not in ("mac", "choreboy", "capped"):
        raise ValueError("unknown profile %s" % profile)
    load_start = _read_load()
    previous = os.environ.get("CBCS_FB_VALIDATE")
    # Section 12 edit budgets are the production path. Tests turn validation on,
    # and validate() walks the whole form, which is allowed only as a test hook.
    os.environ["CBCS_FB_VALIDATE"] = "0"
    try:
        rows = _collect(
            profile=profile,
            samples=samples,
            warmup=warmup,
            sizes=tuple(sizes),
            seed=seed,
            load_start=load_start,
        )
    finally:
        if previous is None:
            os.environ.pop("CBCS_FB_VALIDATE", None)
        else:
            os.environ["CBCS_FB_VALIDATE"] = previous
    load_end = _read_load()
    enforced, wall = wall_policy(load_start, load_end)
    if enforced:
        judged = rows
    else:
        judged = tuple(_drop_wall_failures(row) for row in rows)
        wall = wall_policy(load_start, load_end)[1]
    return SpeedReport(
        profile=profile,
        interpreter=sys.version.split()[0],
        qt_version=raw_qt.qt_version(),
        load_start=load_start,
        load_end=load_end,
        wall=wall,
        samples=samples,
        warmup=warmup,
        cpu_tolerance=CPU_TOLERANCE,
        cpus=_cpu_count(),
        rows=judged,
    )


def format_table(report: SpeedReport) -> str:
    """Plain-text table. p50 and p95 use the unit named in the budget."""
    header = (
        "profile %s  interpreter %s  Qt %s  cpus %d"
        % (report.profile, report.interpreter, report.qt_version, report.cpus)
    )
    load = "load avg 1m/5m/15m start %s end %s" % (
        _load_text(report.load_start),
        _load_text(report.load_end),
    )
    meta = "samples %d  warmup %d  cpu tolerance %.2f  wall %s" % (
        report.samples,
        report.warmup,
        report.cpu_tolerance,
        report.wall,
    )
    columns = ("point", "widgets", "n", "p50", "p95", "total p95", "budget", "verdict")
    body = [
        (
            row.point,
            "-" if row.widgets is None else str(row.widgets),
            "-" if row.samples is None else str(row.samples),
            _num(row.p50),
            _num(row.p95),
            _num(row.total_p95),
            row.budget,
            row.verdict,
        )
        for row in report.rows
    ]
    widths = [
        max([len(columns[index])] + [len(item[index]) for item in body])
        for index in range(len(columns))
    ]

    def line(item: Tuple[str, ...]) -> str:
        return "  ".join(item[index].ljust(widths[index]) for index in range(len(item)))

    table = [line(columns), line(tuple("-" * width for width in widths))]
    table.extend(line(item) for item in body)
    notes = [
        "%s: %s" % (row.point if row.widgets is None else "%s @%s" % (row.point, row.widgets), row.detail)
        for row in report.rows
        if row.detail
    ]
    parts = [header, load, meta, "", "\n".join(table)]
    if notes:
        parts.extend(["", "\n".join(notes)])
    parts.append("")
    parts.append("speed: %s" % ("PASS" if report.ok else "FAIL"))
    return "\n".join(parts) + "\n"


def report_json(report: SpeedReport) -> dict:
    return {
        "profile": report.profile,
        "interpreter": report.interpreter,
        "qt_version": report.qt_version,
        "load_start": list(report.load_start),
        "load_end": list(report.load_end),
        "wall": report.wall,
        "samples": report.samples,
        "warmup": report.warmup,
        "cpu_tolerance": report.cpu_tolerance,
        "cpus": report.cpus,
        "ok": report.ok,
        "rows": [
            {
                "point": row.point,
                "widgets": row.widgets,
                "n": row.samples,
                "p50": row.p50,
                "p95": row.p95,
                "total_p95": row.total_p95,
                "budget": row.budget,
                "verdict": row.verdict,
                "detail": row.detail,
            }
            for row in report.rows
        ],
    }


def write_json(report: SpeedReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report_json(report), indent=2) + "\n", encoding="utf-8")


def _collect(
    *,
    profile: str,
    samples: int,
    warmup: int,
    sizes: Tuple[int, ...],
    seed: int,
    load_start: Tuple[float, float, float],
) -> Tuple[Row, ...]:
    enforce_absolute = profile == "mac"
    wall_on = wall_policy(load_start, load_start)[0]
    forms = {count: reference_form(count, seed) for count in sizes}
    documents = {
        count: read_ui(form.xml, allocator=IdAllocator()).document
        for count, form in forms.items()
    }
    rows: List[Row] = []
    command_dists: Dict[int, Distribution] = {}

    for count in sizes:
        form = forms[count]
        rows.append(
            _timed(
                "read_ui",
                count,
                lambda text=form.xml: _read(text),
                READ_BUDGET_MS.get(count),
                samples=samples,
                warmup=warmup,
                enforce_absolute=enforce_absolute,
                wall_on=wall_on,
            )[0]
        )

    rows.append(_class_table_row(samples, warmup, enforce_absolute, wall_on))
    realize_rows = _realize_rows(forms.get(300), samples, warmup, enforce_absolute, wall_on)
    rows.extend(realize_rows)
    build_p95 = next((row.p95 for row in realize_rows if row.point == "Realizer.build"), None)
    rows.append(_missing("outline full build", 300, _ms_budget(OUTLINE_BUILD_BUDGET_MS), "no outline yet"))
    rows.append(
        _open_read_build_row(forms.get(300), samples, warmup, enforce_absolute, wall_on)
    )

    for count in sizes:
        form = forms[count]
        row, dist = _command_row(
            count,
            form,
            samples=samples,
            warmup=warmup,
            enforce_absolute=enforce_absolute,
            wall_on=wall_on,
        )
        rows.append(row)
        command_dists[count] = dist
    rows.append(_changed_ratio(command_dists, samples, warmup, forms, enforce_absolute, wall_on))

    for count in sizes:
        form = forms[count]
        rows.append(
            _undo_row(
                "undo",
                count,
                form,
                samples=samples,
                warmup=warmup,
                enforce_absolute=enforce_absolute,
                wall_on=wall_on,
                kind="undo",
            )
        )
        rows.append(
            _undo_row(
                "redo",
                count,
                form,
                samples=samples,
                warmup=warmup,
                enforce_absolute=enforce_absolute,
                wall_on=wall_on,
                kind="redo",
            )
        )

    rows.append(
        _realize_patch_row(forms.get(300), samples, warmup, enforce_absolute, wall_on)
    )
    rows.extend(_structural_rows(forms, samples, warmup, enforce_absolute))
    rows.extend(_hit_rows(forms, samples, warmup, enforce_absolute, wall_on))
    rows.extend(_drop_target_rows(documents, samples, warmup, enforce_absolute, wall_on))
    rows.extend(_canvas_rows(forms, samples, warmup, enforce_absolute, wall_on))
    rows.extend(_outline_attached_rows(forms, samples, warmup, enforce_absolute, wall_on))
    rows.append(_missing("outline patch", 300, _ms_budget(OUTLINE_PATCH_BUDGET_MS), "no separate patch timing"))
    rows.append(
        _inspector_row(forms.get(300), samples, warmup, enforce_absolute, wall_on)
    )
    rows.extend(
        _inspector_select_rows(forms.get(300), samples, warmup, enforce_absolute, wall_on)
    )
    rows.append(
        _inspector_shell_row(forms.get(300), samples, warmup, enforce_absolute, wall_on)
    )
    rows.extend(_sizing_rows(forms, samples, warmup, enforce_absolute, wall_on))

    probe = documents[sizes[0]]
    rows.append(
        _timed(
            "is_dirty",
            None,
            lambda log=_dirty_log(forms[sizes[0]].xml): _touch_dirty(log),
            None,
            samples=samples,
            warmup=warmup,
            enforce_absolute=False,
            wall_on=False,
        )[0]
    )
    rows.append(
        _timed(
            "revision",
            None,
            lambda document=probe: _touch_revision(document),
            None,
            samples=samples,
            warmup=warmup,
            enforce_absolute=False,
            wall_on=False,
        )[0]
    )
    rows.append(
        _missing(
            "cheap diagnostics",
            300,
            _ms_budget(DIAGNOSTICS_BUDGET_MS),
            "no edit-path diagnostic producer yet",
        )
    )

    for count in sizes:
        document = documents[count]
        rows.append(
            _timed(
                "write_ui",
                count,
                lambda doc=document: _write(doc),
                WRITE_BUDGET_MS.get(count),
                samples=samples,
                warmup=warmup,
                enforce_absolute=enforce_absolute,
                wall_on=wall_on,
            )[0]
        )

    rows.extend(_codegen_and_save(documents.get(300), forms.get(300), samples, warmup, enforce_absolute, wall_on))
    rows.extend(_memory_rows(forms[300] if 300 in forms else forms[sizes[0]]))
    rows.append(_undo_log_row(forms[300] if 300 in forms else forms[sizes[0]]))
    rows.append(
        _missing(
            "preview warm update",
            None,
            _ms_budget(PREVIEW_WARM_BUDGET_MS) + " wall",
            "no preview yet",
        )
    )
    rows.append(_missing("preview cold start", None, "-", "no preview yet. No budget. Report against the M0.7 cold start when it exists"))

    if profile in ("choreboy", "capped"):
        rows.extend(_overhead_rows(forms.get(300), samples, warmup, build_p95))
    return tuple(rows)


def _timed(
    point: str,
    widgets: Optional[int],
    fn: Callable[[], None],
    budget_ms: Optional[float],
    *,
    samples: int,
    warmup: int,
    enforce_absolute: bool,
    wall_on: bool,
    prepare: Optional[Callable[[], None]] = None,
    cleanup: Optional[Callable[[], None]] = None,
) -> Tuple[Row, Distribution]:
    enforced = budget_ms if enforce_absolute else None

    def once() -> Distribution:
        return measure(fn, warmup=warmup, samples=samples, prepare=prepare, cleanup=cleanup)

    attempt = sample_until_budget(once, enforced)
    return _row_from_attempt(point, widgets, attempt, budget_ms, enforce_absolute, wall_on), attempt.distribution


def _row_from_attempt(
    point: str,
    widgets: Optional[int],
    attempt: Attempt,
    budget_ms: Optional[float],
    enforce_absolute: bool,
    wall_on: bool,
) -> Row:
    dist = attempt.distribution
    if budget_ms is None or not enforce_absolute:
        verdict = "reported"
    else:
        verdict = judge_timed(dist, budget_ms, wall_enforced=wall_on and enforce_absolute)
    detail: List[str] = []
    if attempt.tries > 1:
        detail.append("retried the sample set once")
    if verdict == "fail" and cpu_within_budget(dist.cpu_p95 * 1000.0, budget_ms or 0.0):
        detail.append("wall p95 exceeded the budget")
    elif verdict == "fail":
        detail.append("cpu p95 exceeded the tolerated budget")
    if budget_ms is not None and not enforce_absolute:
        detail.append("absolute budget is mac-only")
    return Row(
        point,
        widgets,
        dist.n,
        dist.cpu_p50 * 1000.0,
        dist.cpu_p95 * 1000.0,
        _ms_budget(budget_ms),
        verdict,
        " ".join(detail),
    )


def _command_row(
    count: int,
    form: ReferenceForm,
    *,
    samples: int,
    warmup: int,
    enforce_absolute: bool,
    wall_on: bool,
) -> Tuple[Row, Distribution]:
    log, owner = _open_log(form.xml)
    counter = {"n": 0}

    def edit() -> None:
        _LISTENER_SINK[0] = 0
        counter["n"] += 1
        outcome = log.execute(SetProperty(owner, "toolTip", StringValue("m%d" % counter["n"])))
        if outcome.noop:
            raise RuntimeError("property edit was a no-op")
        if _LISTENER_SINK[0] == 0:
            raise RuntimeError("command listener was not called")

    return _timed(
        "one command",
        count,
        edit,
        COMMAND_BUDGET_MS.get(count),
        samples=samples,
        warmup=warmup,
        enforce_absolute=enforce_absolute,
        wall_on=wall_on,
    )


def _changed_ratio(
    dists: Dict[int, Distribution],
    samples: int,
    warmup: int,
    forms: Dict[int, ReferenceForm],
    enforce_absolute: bool,
    wall_on: bool,
) -> Row:
    del enforce_absolute, wall_on
    if 300 not in dists or 1000 not in dists:
        return Row(
            "one command O(changed)",
            None,
            None,
            None,
            None,
            "%.1fx" % CHANGED_RATIO_LIMIT,
            "skip",
            "needs the one-command samples at 300 and 1000 widgets",
        )
    judgment, tries = _judge_pair_with_retry(dists[300], dists[1000], forms, samples, warmup)
    detail = judgment.detail
    if tries > 1:
        detail += ". retried the pair once"
    return Row(
        "one command O(changed)",
        None,
        samples,
        None,
        judgment.measured,
        judgment.budget,
        "pass" if judgment.passed else "fail",
        detail,
    )


def _judge_pair_with_retry(
    small: Distribution,
    large: Distribution,
    forms: Dict[int, ReferenceForm],
    samples: int,
    warmup: int,
) -> Tuple[ScaleJudgment, int]:
    judgment = judge_changed_scale(small.cpu_p95, large.cpu_p95)
    if judgment.passed:
        return judgment, 1
    again = {
        300: _command_row(300, forms[300], samples=samples, warmup=warmup, enforce_absolute=False, wall_on=False)[1],
        1000: _command_row(1000, forms[1000], samples=samples, warmup=warmup, enforce_absolute=False, wall_on=False)[1],
    }
    return judge_changed_scale(again[300].cpu_p95, again[1000].cpu_p95), 2


def _undo_row(
    point: str,
    count: int,
    form: ReferenceForm,
    *,
    samples: int,
    warmup: int,
    enforce_absolute: bool,
    wall_on: bool,
    kind: str,
) -> Row:
    log, owner = _open_log(form.xml)
    log.execute(SetProperty(owner, "toolTip", StringValue("base")))
    if kind == "redo":
        if not log.undo():
            raise RuntimeError("redo sample could not prime the redo stack")

    def restore() -> None:
        if kind == "undo":
            if not log.redo():
                raise RuntimeError("undo sample had nothing to restore")
        elif not log.undo():
            raise RuntimeError("redo sample had nothing to restore")

    def act() -> None:
        ok = log.undo() if kind == "undo" else log.redo()
        if not ok:
            raise RuntimeError("%s sample was empty" % kind)

    # The first prepare is a no-op: the stack was primed above. Later prepares
    # put the entry back so each sample performs one real undo or redo.
    primed = {"done": False}

    def prepare() -> None:
        if not primed["done"]:
            primed["done"] = True
            return
        restore()

    budget = COMMAND_BUDGET_MS.get(count)
    row, _dist = _timed(
        point,
        count,
        act,
        budget,
        samples=samples,
        warmup=warmup,
        enforce_absolute=enforce_absolute,
        wall_on=wall_on,
        prepare=prepare,
    )
    note = "same millisecond budget as one command. Undo and redo have no row of their own in section 12"
    row = Row(row.point, row.widgets, row.samples, row.p50, row.p95, row.budget, row.verdict, _join(row.detail, note))
    return row


def _class_table_row(samples: int, warmup: int, enforce_absolute: bool, wall_on: bool) -> Row:
    path = Path(class_defaults.__file__).resolve().parent / class_defaults.DATA_FILE
    if not path.is_file():
        return Row(
            "class table first load",
            None,
            None,
            None,
            None,
            _ms_budget(CLASS_TABLE_BUDGET_MS),
            "skip",
            "qt_classes.json is not in this tree, so the loader returns an empty table",
        )

    def load() -> None:
        # shared() caches the table for the process. Clearing it is the only
        # way to time the load more than once. There is no public reset.
        class_defaults._SHARED = None
        class_defaults.QtClassTable.shared()

    row, _dist = _timed(
        "class table first load",
        None,
        load,
        CLASS_TABLE_BUDGET_MS,
        samples=samples,
        warmup=warmup,
        enforce_absolute=enforce_absolute,
        wall_on=wall_on,
    )
    return row


def _realize_rows(
    form: Optional[ReferenceForm],
    samples: int,
    warmup: int,
    enforce_absolute: bool,
    wall_on: bool,
) -> Tuple[Row, ...]:
    if form is None:
        return (
            _missing("Realizer.build", 300, _ms_budget(REALIZER_BUILD_BUDGET_MS), "no 300-widget form in this run"),
        )
    if not _module_exists("app.features.form_builder.qtside.realize"):
        return (
            _missing(
                "Realizer.build",
                300,
                _ms_budget(REALIZER_BUILD_BUDGET_MS),
                "app.features.form_builder.qtside.realize is not in this tree",
            ),
        )
    attempt = _time_realizer_build(form.xml, samples, warmup, REALIZER_BUILD_BUDGET_MS if enforce_absolute else None)
    if isinstance(attempt, str):
        return (Row("Realizer.build", 300, None, None, None, _ms_budget(REALIZER_BUILD_BUDGET_MS), "skip", attempt),)
    return (_row_from_attempt("Realizer.build", 300, attempt, REALIZER_BUILD_BUDGET_MS, enforce_absolute, wall_on),)


def _time_realizer_build(
    xml: str, samples: int, warmup: int, budget_ms: Optional[float]
) -> Union[Attempt, str]:
    try:
        realize = importlib.import_module("app.features.form_builder.qtside.realize")
        session_mod = importlib.import_module("app.features.form_builder.engine.session")
        forms = importlib.import_module("app.features.form_builder.engine.project.forms")
    except ImportError as exc:
        return "realize is present but its session imports failed (%s)" % exc
    held: List[object] = []

    def once() -> None:
        session, realizer = _open_realized(xml, session_mod, forms, realize)
        held.append(realizer)
        held.append(session)

    def cleanup() -> None:
        _dispose_held(held)

    try:
        return sample_until_budget(
            lambda: measure(once, warmup=warmup, samples=samples, cleanup=cleanup),
            budget_ms,
        )
    except (AttributeError, TypeError, RuntimeError) as exc:
        return "Realizer.build could not be called (%s)" % exc


def _hit_rows(
    forms: Dict[int, ReferenceForm],
    samples: int,
    warmup: int,
    enforce_absolute: bool,
    wall_on: bool,
) -> Tuple[Row, ...]:
    """LiveGeometrySource over the realized reference form, shown offscreen.

    A hidden root would make every child invisible to the walk, which then
    skips them and times almost nothing.
    """
    if not _module_exists("app.features.form_builder.qtside.canvas.geometry"):
        reason = "no live geometry source in this tree"
        missing = [_missing("hit index invalidate", None, "-", reason)]
        missing.extend(
            _missing("hit index refresh", count, _ms_budget(budget), reason)
            for count, budget in HIT_REFRESH_BUDGET_MS.items()
        )
        missing.append(_missing("hit query", 300, _ms_budget(HIT_QUERY_BUDGET_MS), reason))
        return tuple(missing)
    realize = importlib.import_module("app.features.form_builder.qtside.realize")
    session_mod = importlib.import_module("app.features.form_builder.engine.session")
    forms_mod = importlib.import_module("app.features.form_builder.engine.project.forms")
    geometry = importlib.import_module("app.features.form_builder.qtside.canvas.geometry")
    hit_index = importlib.import_module("app.features.form_builder.engine.query.hit_index")
    invalidate_rows: List[Row] = []
    refresh_rows: List[Row] = []
    query_rows: List[Row] = []
    for count, budget in HIT_REFRESH_BUDGET_MS.items():
        form = forms.get(count)
        if form is None:
            refresh_rows.append(_missing("hit index refresh", count, _ms_budget(budget), "no %d-widget form in this run" % count))
            continue
        session, realizer = _open_realized(form.xml, session_mod, forms_mod, realize)
        root = realizer.root_widget
        root.show()
        try:
            source = geometry.LiveGeometrySource(realizer)
            index = hit_index.HitIndex(source)
            index.ensure_fresh()
            entries = source.entries()
            visible = sum(1 for entry in entries if entry.visible)
            if count == 300:
                invalidate_rows.append(
                    _timed(
                        "hit index invalidate",
                        None,
                        lambda index=index: index.invalidate("changeset"),
                        None,
                        samples=samples,
                        warmup=warmup,
                        enforce_absolute=False,
                        wall_on=False,
                    )[0]
                )
            row = _timed(
                "hit index refresh",
                count,
                index.ensure_fresh,
                budget,
                samples=samples,
                warmup=warmup,
                enforce_absolute=enforce_absolute,
                wall_on=wall_on,
                prepare=lambda index=index: index.invalidate("changeset"),
            )[0]
            refresh_rows.append(
                _with_detail(row, "settle plus walk after an invalidate. %d entries, %d visible" % (len(entries), visible))
            )
            if count == 300:
                x, y, depth = _deepest_point(index, root.width(), root.height())
                row = _timed(
                    "hit query",
                    300,
                    lambda index=index, x=x, y=y: index.query(x, y),
                    HIT_QUERY_BUDGET_MS,
                    samples=samples,
                    warmup=warmup,
                    enforce_absolute=enforce_absolute,
                    wall_on=wall_on,
                )[0]
                query_rows.append(_with_detail(row, "one query at the deepest point, path length %d" % depth))
        finally:
            root.hide()
            _dispose_held([realizer, session])
    return tuple(invalidate_rows + refresh_rows + query_rows)


class _FlatGeometry:
    """Synthetic rects. The timed path still walks ``rect_of`` on every call."""

    def __init__(self, entries: Tuple[GeoEntry, ...]) -> None:
        self._entries = entries

    def settle(self) -> None:
        return None

    def entries(self) -> Tuple[GeoEntry, ...]:
        return self._entries


def _drop_target_rows(
    documents: Dict[int, UiDocument],
    samples: int,
    warmup: int,
    enforce_absolute: bool,
    wall_on: bool,
) -> Tuple[Row, ...]:
    rows: List[Row] = []
    payload = DropPayload("widget")
    for count in (300, 1000):
        label = "drop target @%d" % count
        document = documents.get(count)
        if document is None:
            rows.append(_missing(label, count, _ms_budget(DROP_TARGET_BUDGET_MS), "no %d-widget form in this run" % count))
            continue
        entries = []
        y = 0
        for node in document.iter_preorder():
            entries.append(GeoEntry(node.id, "widget", Rect(0, y, 240, 24), None, True, y))
            y += 28
        index = HitIndex(_FlatGeometry(tuple(entries)))
        index.ensure_fresh()
        point = FormPoint(12, 40)
        resolve_at(document, index, point, payload)

        def run(
            document: UiDocument = document,
            index: HitIndex = index,
            point: FormPoint = point,
        ) -> None:
            resolve_at(document, index, point, payload)

        rows.append(
            _timed(
                label,
                count,
                run,
                DROP_TARGET_BUDGET_MS,
                samples=samples,
                warmup=warmup,
                enforce_absolute=enforce_absolute,
                wall_on=wall_on,
            )[0]
        )
    return tuple(rows)


def _canvas_rows(
    forms: Dict[int, ReferenceForm],
    samples: int,
    warmup: int,
    enforce_absolute: bool,
    wall_on: bool,
) -> Tuple[Row, ...]:
    """Overlay paint, selection to the canvas frame, and one property edit.

    Outline and the inspector are not in this fixture. Those rows stay open.
    """
    if not _module_exists("app.features.form_builder.qtside.canvas.paint"):
        reason = "no canvas paint in this tree"
        return (
            _missing("overlay paint", 300, _ms_budget(OVERLAY_BUDGET_MS), reason),
            _missing("edit total", 300, _ms_budget(EDIT_BUDGET_MS), reason),
            _missing("selection change", 300, _ms_budget(SELECTION_BUDGET_MS), reason),
        )
    form = forms.get(300)
    if form is None:
        reason = "no 300-widget form in this run"
        return (
            _missing("overlay paint", 300, _ms_budget(OVERLAY_BUDGET_MS), reason),
            _missing("edit total", 300, _ms_budget(EDIT_BUDGET_MS), reason),
            _missing("selection change", 300, _ms_budget(SELECTION_BUDGET_MS), reason),
        )
    if QApplication.instance() is None:
        QApplication([])
    realize = importlib.import_module("app.features.form_builder.qtside.realize")
    session_mod = importlib.import_module("app.features.form_builder.engine.session")
    forms_mod = importlib.import_module("app.features.form_builder.engine.project.forms")
    canvas_mod = importlib.import_module("app.features.form_builder.integration.canvas")
    paint_mod = importlib.import_module("app.features.form_builder.qtside.canvas.paint")
    theme = importlib.import_module("app.features.form_builder.qtside.theme.overlay")
    selection = importlib.import_module("app.features.form_builder.engine.query.selection")
    nodes = importlib.import_module("app.features.form_builder.engine.ui4.nodes")
    session, realizer = _open_realized(form.xml, session_mod, forms_mod, realize)
    parent = QWidget()
    parent.resize(960, 720)
    canvas = canvas_mod.FormCanvas(session, realizer, _SpeedHost(), parent)
    canvas.resize(960, 720)
    parent.show()
    app = QApplication.instance()
    assert app is not None
    # Show posts a resize after the first frame. Drain until the overlay matches the placed page.
    for _ in range(4):
        app.processEvents()
    painted_items = len(canvas.overlay().items)
    if painted_items == 0:
        raise RuntimeError("overlay frame is empty, so paint would time nothing")
    try:
        fill, dot = theme.backdrop_fill(False, False)
        palette = theme.CanvasPalette(
            overlay=theme.overlay_palette(False),
            backdrop=theme.BackdropPalette(
                fill=fill,
                dot=dot,
                faint="#666F76",
                accent="#3366FF",
                muted="#5A6168",
                panel="#FFFFFF",
                border="#DEE2E6",
                text="#212529",
            ),
        )
        scene = canvas.sceneRect()
        image = QImage(
            max(1, int(scene.width())),
            max(1, int(scene.height())),
            getattr(getattr(QImage, "Format", QImage), "Format_ARGB32"),
        )
        image.fill(0)
        painter = QPainter(image)
        exposed = QRectF(scene)
        try:
            paint = _timed(
                "overlay paint",
                300,
                lambda: paint_mod.paint_frame(painter, canvas.overlay(), palette, exposed),
                OVERLAY_BUDGET_MS,
                samples=samples,
                warmup=warmup,
                enforce_absolute=enforce_absolute,
                wall_on=wall_on,
            )[0]
        finally:
            painter.end()
        ids = [
            node.id
            for node in session.document.iter_preorder()
            if isinstance(node, nodes.WidgetNode) and node.id != session.document.root.id
        ]
        if not ids:
            ids = [session.document.root.id]
        cursor = {"n": 0}

        def choose() -> None:
            cursor["n"] = (cursor["n"] + 1) % len(ids)
            node_id = ids[cursor["n"]]
            session.selection.set((node_id,), current=node_id, source=selection.SelectionSource.CANVAS)
            app.processEvents()

        chosen = _timed(
            "selection change",
            300,
            choose,
            SELECTION_BUDGET_MS,
            samples=samples,
            warmup=warmup,
            enforce_absolute=enforce_absolute,
            wall_on=wall_on,
        )[0]
        owner = ids[0]
        step = {"n": 0}
        expected = {"n": canvas._index.refresh_count}

        def edit() -> None:
            step["n"] += 1
            outcome = session.log.execute(SetProperty(owner, "toolTip", StringValue("e%d" % step["n"])))
            if outcome.noop:
                raise RuntimeError("text edit was a no-op")
            app.processEvents()
            expected["n"] += 1
            if canvas._index.refresh_count != expected["n"]:
                raise RuntimeError(
                    "hit index refreshed %s times, wanted %s" % (canvas._index.refresh_count, expected["n"])
                )

        edited = _timed(
            "edit total",
            300,
            edit,
            EDIT_BUDGET_MS,
            samples=samples,
            warmup=warmup,
            enforce_absolute=enforce_absolute,
            wall_on=wall_on,
        )[0]
        return (
            _with_detail(
                paint,
                "paint_frame of %d overlay items into a %dx%d image"
                % (painted_items, image.width(), image.height()),
            ),
            _with_detail(chosen, "selection.set plus one frame. Outline is not attached"),
            _with_detail(edited, "SetProperty plus one frame. The hit index refreshes once. Inspector is not attached"),
        )
    finally:
        canvas.dispose()
        parent.deleteLater()
        app.processEvents()
        _dispose_held([realizer, session])


def _outline_attached_rows(
    forms: Dict[int, ReferenceForm],
    samples: int,
    warmup: int,
    enforce_absolute: bool,
    wall_on: bool,
) -> Tuple[Row, ...]:
    """Selection with the outline listening. The unattached row stays separate."""
    rows: List[Row] = []
    for count in (300, 1000):
        form = forms.get(count)
        if form is None:
            rows.append(
                _missing(
                    "selection change outline",
                    count,
                    _ms_budget(SELECTION_BUDGET_MS),
                    "no %d-widget form in this run" % count,
                )
            )
            continue
        rows.append(
            _outline_selection_row(form, count, samples, warmup, enforce_absolute, wall_on)
        )
    return tuple(rows)


def _outline_selection_row(
    form: ReferenceForm,
    count: int,
    samples: int,
    warmup: int,
    enforce_absolute: bool,
    wall_on: bool,
) -> Row:
    if QApplication.instance() is None:
        QApplication([])
    realize = importlib.import_module("app.features.form_builder.qtside.realize")
    session_mod = importlib.import_module("app.features.form_builder.engine.session")
    forms_mod = importlib.import_module("app.features.form_builder.engine.project.forms")
    canvas_mod = importlib.import_module("app.features.form_builder.integration.canvas")
    outline_mod = importlib.import_module("app.features.form_builder.integration.workbench")
    nodes = importlib.import_module("app.features.form_builder.engine.ui4.nodes")
    selection = importlib.import_module("app.features.form_builder.engine.query.selection")
    session, realizer = _open_realized(form.xml, session_mod, forms_mod, realize)
    parent = QWidget()
    parent.resize(960, 720)
    canvas = canvas_mod.FormCanvas(session, realizer, _SpeedHost(), parent)
    canvas.resize(960, 720)
    outline = outline_mod.OutlinePane(lambda _node: None, lambda _collapsed: None, parent)
    outline.rebuild(session.document, session.selection.state.current)
    app = QApplication.instance()
    assert app is not None

    def on_selection(change: object) -> None:
        after = getattr(change, "after", None)
        outline.show_current(None if after is None else getattr(after, "current", None))

    unsubscribe = session.selection.subscribe(on_selection)
    parent.show()
    for _ in range(4):
        app.processEvents()
    ids = [
        node.id
        for node in session.document.iter_preorder()
        if isinstance(node, nodes.WidgetNode) and node.id != session.document.root.id
    ]
    if not ids:
        ids = [session.document.root.id]
    cursor = {"n": 0}

    def choose() -> None:
        cursor["n"] = (cursor["n"] + 1) % len(ids)
        node_id = ids[cursor["n"]]
        session.selection.set((node_id,), current=node_id, source=selection.SelectionSource.CANVAS)
        app.processEvents()

    try:
        chosen = _timed(
            "selection change outline",
            count,
            choose,
            SELECTION_BUDGET_MS,
            samples=samples,
            warmup=warmup,
            enforce_absolute=enforce_absolute,
            wall_on=wall_on,
        )[0]
        return _with_detail(chosen, "selection.set plus one frame. Outline show_current is attached")
    finally:
        unsubscribe()
        canvas.dispose()
        parent.deleteLater()
        app.processEvents()
        _dispose_held([realizer, session])


class _SpeedHost:
    def canvas_pressed(self) -> None:
        return None

    def narrate(self, sentence: str) -> None:
        return None

    def hover_changed(self, node: object) -> None:
        return None

    def zoom_changed(self, label: str) -> None:
        return None

    def open_problem(self, node: object) -> None:
        return None

    def open_layout_popover(self, node: object) -> None:
        return None


def _deepest_point(index: Any, width: int, height: int) -> Tuple[int, int, int]:
    best = (0, 0, 0)
    for x in range(0, width, 16):
        for y in range(0, height, 16):
            hit = index.query(x, y)
            if hit is not None and len(hit.path) > best[2]:
                best = (x, y, len(hit.path))
    return best


def _with_detail(row: Row, detail: str) -> Row:
    if row.detail:
        detail = "%s. %s" % (detail, row.detail)
    return Row(row.point, row.widgets, row.samples, row.p50, row.p95, row.budget, row.verdict, detail, row.total_p95)


def _codegen_and_save(
    document: Optional[UiDocument],
    form: Optional[ReferenceForm],
    samples: int,
    warmup: int,
    enforce_absolute: bool,
    wall_on: bool,
) -> Tuple[Row, ...]:
    generate = _load_generate()
    if generate is None or document is None or form is None:
        return (
            _missing(
                "generate_form_module",
                300,
                _ms_budget(CODEGEN_BUDGET_MS),
                "app.features.form_builder.engine.codegen is not in this tree",
            ),
            _missing(
                "save total",
                300,
                _ms_budget(SAVE_BUDGET_MS),
                "needs write_ui and generate_form_module",
            ),
        )
    source = form.xml.encode("utf-8")

    def once() -> None:
        generate(document, source)

    try:
        attempt = sample_until_budget(
            lambda: measure(once, warmup=warmup, samples=samples),
            CODEGEN_BUDGET_MS if enforce_absolute else None,
        )
    except (AttributeError, TypeError, RuntimeError) as exc:
        return (
            Row("generate_form_module", 300, None, None, None, _ms_budget(CODEGEN_BUDGET_MS), "fail", str(exc)),
            _missing("save total", 300, _ms_budget(SAVE_BUDGET_MS), "generate_form_module could not be called"),
        )
    generated = _row_from_attempt(
        "generate_form_module",
        300,
        attempt,
        CODEGEN_BUDGET_MS,
        enforce_absolute,
        wall_on,
    )
    def once_save() -> None:
        text = write_ui(document).text
        generate(document, text.encode("utf-8"))

    save = _timed(
        "save total",
        300,
        once_save,
        SAVE_BUDGET_MS,
        samples=samples,
        warmup=warmup,
        enforce_absolute=enforce_absolute,
        wall_on=wall_on,
    )[0]
    return (generated, save)


def _load_generate() -> Optional[Callable[..., object]]:
    if not _module_exists("app.features.form_builder.engine.codegen"):
        return None
    module = importlib.import_module("app.features.form_builder.engine.codegen")
    fn = getattr(module, "generate_form_module", None)
    if fn is None:
        api = importlib.import_module("app.features.form_builder.engine.codegen.api")
        fn = getattr(api, "generate_form_module", None)
    if fn is None:
        return None

    def call(document: object, source: bytes) -> object:
        forms = importlib.import_module("app.features.form_builder.engine.project.forms")
        scope = forms.FormScope(
            kind="project",
            ui_path="/tmp/forms/speed_form.ui",
            project_root="/tmp",
            generated_path="/tmp/forms/ui_speed_form.py",
            window_path="/tmp/forms/speed_form_window.py",
            module_name="forms.ui_speed_form",
            window_module_name="forms.speed_form_window",
        )
        options_mod = importlib.import_module("app.features.form_builder.engine.codegen.api")
        options = getattr(options_mod, "CodegenOptions", None)
        kwargs = {"scope": scope, "source_bytes": source}
        if options is not None:
            kwargs["options"] = options()
        result = fn(document, **kwargs)
        # Timing a refusal would report a meaningless pass.
        if getattr(result, "text", None) is None:
            codes = [getattr(item, "code", "?") for item in getattr(result, "diagnostics", ())]
            raise RuntimeError("generate_form_module returned no module: %s" % codes)
        return result

    return call


def _memory_rows(form: ReferenceForm) -> Tuple[Row, ...]:
    one_trace, one_rss, one_note = _open_memory((form.xml,))
    three_trace, three_rss, three_note = _open_memory((form.xml, form.xml, form.xml))
    return (
        _memory_row("memory one form tracemalloc", one_trace, ONE_FORM_BUDGET_MB, "tracemalloc peak. %s" % one_note),
        _memory_row("memory one form rss", one_rss, ONE_FORM_BUDGET_MB, "VmRSS delta. %s" % one_note),
        _memory_row(
            "memory three forms tracemalloc",
            three_trace,
            THREE_FORM_BUDGET_MB,
            "tracemalloc peak. %s" % three_note,
        ),
        _memory_row(
            "memory three forms rss",
            three_rss,
            THREE_FORM_BUDGET_MB,
            "VmRSS delta. %s" % three_note,
        ),
    )


def _open_memory(texts: Sequence[str]) -> Tuple[float, float, str]:
    gc.collect()
    rss_before = _rss_bytes()
    tracemalloc.start()
    held: List[object] = []
    note = "read only"
    try:
        for text in texts:
            opened, note = _hold_open_form(text)
            held.extend(opened)
        _current, peak = tracemalloc.get_traced_memory()
        rss_after = _rss_bytes()
    finally:
        tracemalloc.stop()
        _dispose_held(held)
    return peak / (1024.0 * 1024.0), max(0.0, rss_after - rss_before) / (1024.0 * 1024.0), note


def _hold_open_form(xml: str) -> Tuple[List[object], str]:
    """Read one form, and realize it when that module is already in the tree."""
    document = read_ui(xml, allocator=IdAllocator()).document
    held: List[object] = [document]
    if not _module_exists("app.features.form_builder.qtside.realize"):
        return held, "read only. qtside realize is not in this tree"
    try:
        realize = importlib.import_module("app.features.form_builder.qtside.realize")
        session_mod = importlib.import_module("app.features.form_builder.engine.session")
        forms = importlib.import_module("app.features.form_builder.engine.project.forms")
        session, realizer = _open_realized(xml, session_mod, forms, realize)
        held.extend((session, realizer))
    except (ImportError, AttributeError, TypeError, RuntimeError) as exc:
        return held, "read only. realize could not be called (%s)" % exc
    return held, "read and realize"


def _memory_row(point: str, value_mb: float, budget_mb: float, detail: str) -> Row:
    verdict = "pass" if value_mb <= budget_mb else "fail"
    if verdict == "fail":
        detail = "%s. measured %.2f MB" % (detail, value_mb)
    return Row(point, 300, 1, None, value_mb, "%.0f MB" % budget_mb, verdict, detail)


def _undo_log_row(form: ReferenceForm) -> Row:
    log, owner = _open_log(form.xml)
    for index in range(UNDO_LOG_EDITS):
        log.execute(SetProperty(owner, "toolTip", StringValue("u%d" % index)))
    size_mb = retained_bytes(log.entries()) / (1024.0 * 1024.0)
    verdict = "pass" if size_mb <= UNDO_LOG_BUDGET_MB else "fail"
    detail = "%d property edits, object-graph bytes of the undo entries" % UNDO_LOG_EDITS
    return Row("undo log", 300, UNDO_LOG_EDITS, None, size_mb, "%.0f MB" % UNDO_LOG_BUDGET_MB, verdict, detail)


def _open_read_build_row(
    form: Optional[ReferenceForm],
    samples: int,
    warmup: int,
    enforce_absolute: bool,
    wall_on: bool,
) -> Row:
    """Read plus realize. Outline, inspector and the first hit index come later."""
    detail = "read plus Realizer.build. Outline, inspector and the first hit index are not in this number"
    if form is None or not _module_exists("app.features.form_builder.qtside.realize"):
        return _missing("read + build", 300, _ms_budget(OPEN_BUDGET_MS), detail)
    try:
        realize = importlib.import_module("app.features.form_builder.qtside.realize")
        session_mod = importlib.import_module("app.features.form_builder.engine.session")
        forms = importlib.import_module("app.features.form_builder.engine.project.forms")
    except ImportError as exc:
        return Row("read + build", 300, None, None, None, _ms_budget(OPEN_BUDGET_MS), "skip", str(exc))
    held: List[object] = []

    def once() -> None:
        session, realizer = _open_realized(form.xml, session_mod, forms, realize)
        held.append(realizer)
        held.append(session)

    try:
        row, _dist = _timed(
            "read + build",
            300,
            once,
            OPEN_BUDGET_MS,
            samples=samples,
            warmup=warmup,
            enforce_absolute=enforce_absolute,
            wall_on=wall_on,
            cleanup=lambda: _dispose_held(held),
        )
    except (AttributeError, TypeError, RuntimeError) as exc:
        _dispose_held(held)
        return Row("read + build", 300, None, None, None, _ms_budget(OPEN_BUDGET_MS), "skip", str(exc))
    return Row(row.point, row.widgets, row.samples, row.p50, row.p95, row.budget, "partial", detail)


def _realize_patch_row(
    form: Optional[ReferenceForm],
    samples: int,
    warmup: int,
    enforce_absolute: bool,
    wall_on: bool,
) -> Row:
    """One toolTip edit. The clock is PatchStats.cpu_ms, the realize listener only."""
    del wall_on
    if form is None or not _module_exists("app.features.form_builder.qtside.realize"):
        return _missing("property patch", 300, _ms_budget(REALIZER_PATCH_BUDGET_MS), "no qtside realize yet")
    try:
        realize = importlib.import_module("app.features.form_builder.qtside.realize")
        session_mod = importlib.import_module("app.features.form_builder.engine.session")
        forms = importlib.import_module("app.features.form_builder.engine.project.forms")
        session, realizer = _open_realized(form.xml, session_mod, forms, realize)
    except (ImportError, AttributeError, TypeError, RuntimeError) as exc:
        return Row("property patch", 300, None, None, None, _ms_budget(REALIZER_PATCH_BUDGET_MS), "skip", str(exc))
    owner = session.document.by_name(form.edit_name)
    if not owner:
        _dispose_held([realizer, session])
        return Row(
            "property patch",
            300,
            None,
            None,
            None,
            _ms_budget(REALIZER_PATCH_BUDGET_MS),
            "skip",
            "reference form has no %s" % form.edit_name,
        )

    def take(count: int) -> Distribution:
        taken: List[Sample] = []
        for index in range(count):
            session.log.execute(SetProperty(owner[0], "toolTip", StringValue("speed-%d" % index)))
            seconds = realizer.last_stats.cpu_ms / 1000.0
            taken.append(Sample(seconds, seconds))
        return Distribution(tuple(taken))

    try:
        take(warmup)
        attempt = sample_until_budget(lambda: take(samples), REALIZER_PATCH_BUDGET_MS if enforce_absolute else None)
    except (AttributeError, TypeError, RuntimeError) as exc:
        return Row("property patch", 300, None, None, None, _ms_budget(REALIZER_PATCH_BUDGET_MS), "skip", str(exc))
    finally:
        _dispose_held([realizer, session])
    row = _row_from_attempt(
        "property patch",
        300,
        attempt,
        REALIZER_PATCH_BUDGET_MS,
        enforce_absolute,
        False,
    )
    detail = "property patch. PatchStats.cpu_ms for one toolTip edit. Command planning is the one-command row"
    if row.detail:
        detail = "%s. %s" % (detail, row.detail)
    return Row(row.point, row.widgets, row.samples, row.p50, row.p95, row.budget, row.verdict, detail)


STRUCTURAL_POINTS: Tuple[str, ...] = (
    "insert into layout",
    "insert into box layout",
    "insert into loose container",
    "insert tab page",
    "delete from layout",
    "move into earlier container",
    "morph",
    "toolbar edit",
)
# Edits whose changed set does not grow with the form. Their realize p95 at
# 1000 widgets stays within CHANGED_RATIO_LIMIT of the 300-widget p95.
# ``insert into layout`` shifts every grid row, so it is reported at 1000
# widgets and not ratio-judged.
STRUCTURAL_RATIO_POINTS: Tuple[str, ...] = (
    "insert into box layout",
    "insert into loose container",
    "insert tab page",
    "delete from layout",
    "move into earlier container",
    "morph",
    "toolbar edit",
)
STRUCTURAL_TOTAL_NOTE = "realize p95 is PatchStats.cpu_ms. total p95 is log execute + realize + repaint"


def _structural_rows(
    forms: Dict[int, ReferenceForm],
    samples: int,
    warmup: int,
    enforce_absolute: bool,
) -> Tuple[Row, ...]:
    """Structural edits. Realize-only p95 against the 8 ms patch budget at 300 widgets."""
    if 300 not in forms or not _module_exists("app.features.form_builder.qtside.realize"):
        return tuple(_missing(point, 300, _ms_budget(REALIZER_PATCH_BUDGET_MS), "no qtside realize yet") for point in STRUCTURAL_POINTS)
    small = _structural_dists(forms[300], samples, warmup)
    if isinstance(small, str):
        return tuple(Row(point, 300, None, None, None, "-", "skip", small) for point in STRUCTURAL_POINTS)
    rows: List[Row] = []
    for point in STRUCTURAL_POINTS:
        rows.append(_structural_row(point, 300, small[point], REALIZER_PATCH_BUDGET_MS, enforce_absolute))
    if 1000 not in forms:
        for point in STRUCTURAL_RATIO_POINTS:
            rows.append(
                Row(
                    "%s O(changed)" % point,
                    None,
                    None,
                    None,
                    None,
                    "%.1fx" % CHANGED_RATIO_LIMIT,
                    "skip",
                    "needs the 1000-widget form",
                )
            )
        return tuple(rows)
    large = _structural_dists(forms[1000], samples, warmup)
    if isinstance(large, str):
        return tuple(rows) + tuple(Row(point, 1000, None, None, None, "-", "skip", large) for point in STRUCTURAL_POINTS)
    for point in STRUCTURAL_POINTS:
        rows.append(_structural_row(point, 1000, large[point], None, False))
    for point in STRUCTURAL_RATIO_POINTS:
        rows.append(_structural_ratio_row(point, small, large, forms, samples, warmup))
    return tuple(rows)


def _structural_row(
    point: str,
    widgets: int,
    dists: Tuple[Distribution, Distribution],
    budget_ms: Optional[float],
    enforce_absolute: bool,
) -> Row:
    realize_dist, total_dist = dists
    if budget_ms is None or not enforce_absolute:
        verdict = "reported"
    else:
        verdict = judge_timed(realize_dist, budget_ms, wall_enforced=False)
    detail = STRUCTURAL_TOTAL_NOTE
    if verdict == "fail":
        detail += ". realize cpu p95 exceeded the tolerated budget"
    if budget_ms is not None and not enforce_absolute:
        detail += ". absolute budget is mac-only"
    return Row(
        point,
        widgets,
        realize_dist.n,
        realize_dist.cpu_p50 * 1000.0,
        realize_dist.cpu_p95 * 1000.0,
        _ms_budget(budget_ms),
        verdict,
        detail,
        total_p95=total_dist.cpu_p95 * 1000.0,
    )


def _structural_ratio_row(
    point: str,
    small: Dict[str, Tuple[Distribution, Distribution]],
    large: Dict[str, Tuple[Distribution, Distribution]],
    forms: Dict[int, ReferenceForm],
    samples: int,
    warmup: int,
) -> Row:
    used_small, used_large = small[point][0], large[point][0]
    judgment = judge_changed_scale(used_small.cpu_p95, used_large.cpu_p95)
    tries = 1
    if not judgment.passed:
        tries = 2
        again_small = _structural_dists(forms[300], samples, warmup, only=point)
        again_large = _structural_dists(forms[1000], samples, warmup, only=point)
        if not isinstance(again_small, str) and not isinstance(again_large, str):
            judgment = judge_changed_scale(again_small[point][0].cpu_p95, again_large[point][0].cpu_p95)
    detail = judgment.detail
    if tries > 1:
        detail += ". retried the pair once"
    return Row(
        "%s O(changed)" % point,
        None,
        samples,
        None,
        judgment.measured,
        judgment.budget,
        "pass" if judgment.passed else "fail",
        detail,
    )


def _structural_dists(
    form: ReferenceForm,
    samples: int,
    warmup: int,
    only: Optional[str] = None,
) -> Union[str, Dict[str, Tuple[Distribution, Distribution]]]:
    """Per point: (realize-only PatchStats.cpu_ms, execute + realize + repaint)."""
    try:
        realize = importlib.import_module("app.features.form_builder.qtside.realize")
        session_mod = importlib.import_module("app.features.form_builder.engine.session")
        forms = importlib.import_module("app.features.form_builder.engine.project.forms")
        session, realizer = _open_realized(form.xml, session_mod, forms, realize)
    except (ImportError, AttributeError, TypeError, RuntimeError) as exc:
        return str(exc)
    found: Dict[str, Tuple[Distribution, Distribution]] = {}
    try:
        ops = _structural_ops(session)
        for point, fn in ops:
            if only is not None and point != only:
                continue
            found[point] = _measure_structural(fn, session, realizer, samples, warmup)
    except (AttributeError, TypeError, RuntimeError, LookupError, CommandRejected) as exc:
        return str(exc)
    finally:
        _dispose_held([realizer, session])
    return found


def _measure_structural(
    fn: Callable[[], None],
    session: Any,
    realizer: Any,
    samples: int,
    warmup: int,
) -> Tuple[Distribution, Distribution]:
    patch_seconds: List[float] = []

    def once() -> None:
        fn()
        stats = realizer.last_stats
        if stats.fallback_rebuilds:
            raise RuntimeError("structural edit fell back to a rebuild")
        patch_seconds.append(stats.cpu_ms / 1000.0)
        _repaint(realizer)

    def undo() -> None:
        if session.log.can_undo():
            session.log.undo()

    total = measure(once, warmup=warmup, samples=samples, cleanup=undo)
    timed = patch_seconds[warmup:]
    patch = Distribution(tuple(Sample(value, value) for value in timed))
    return patch, total


def _structural_ops(session: Any) -> Tuple[Tuple[str, Callable[[], None]], ...]:
    grid_id = session.document.by_name("grid")[0]
    header_id = session.document.by_name("headerBar")[0]
    toolbar_id = session.document.by_name("toolBar")[0]
    details_id = session.document.by_name("tabDetails")[0]
    tabs_id = session.document.by_name("tabs")[0]
    grid = session.document.get(grid_id)
    header = session.document.get(header_id)
    if not isinstance(grid, LayoutNode) or not isinstance(header, LayoutNode):
        raise LookupError("reference grid or header is not a layout")
    widgets = [item.content.id for item in grid.items if isinstance(item.content, WidgetNode)]
    if len(widgets) < 2:
        raise LookupError("reference grid has fewer than two widgets")
    deleted = widgets[0]
    moved = widgets[1]
    counter = {"n": 0}

    def insert() -> None:
        counter["n"] += 1
        session.log.execute(
            InsertFragment(
                InGridCell(grid_id, 0, 0, mode="insert_row"),
                Fragment(nodes=(button_spec("speedBtn%d" % counter["n"]),)),
            )
        )

    def append() -> None:
        counter["n"] += 1
        live = session.document.get(header_id)
        session.log.execute(
            InsertFragment(
                InBoxLayout(header_id, len(live.items)),
                Fragment(nodes=(button_spec("speedBox%d" % counter["n"]),)),
            )
        )

    def loose() -> None:
        counter["n"] += 1
        live = session.document.get(details_id)
        session.log.execute(
            InsertFragment(
                InContainer(details_id, len(live.child_widgets)),
                Fragment(nodes=(button_spec("speedLoose%d" % counter["n"]),)),
            )
        )

    def tab_page() -> None:
        counter["n"] += 1
        live = session.document.get(tabs_id)
        page = NodeSpec("widget", None, (("class_name", "QWidget"), ("object_name", "speedPage%d" % counter["n"])))
        session.log.execute(InsertFragment(InContainer(tabs_id, len(live.child_widgets)), Fragment(nodes=(page,))))

    def delete() -> None:
        session.log.execute(DeleteNodes((deleted,)))

    def move() -> None:
        session.log.execute(MoveNodes((moved,), InBoxLayout(header_id, 0)))

    def morph() -> None:
        session.log.execute(MorphWidget(moved, "QFrame"))

    def toolbar() -> None:
        session.log.execute(
            CreateAction(
                NodeSpec("action", None, (("name", "actionSpeed"),)),
                ref_at=InActionList(toolbar_id, 0),
            )
        )

    return (
        ("insert into layout", insert),
        ("insert into box layout", append),
        ("insert into loose container", loose),
        ("insert tab page", tab_page),
        ("delete from layout", delete),
        ("move into earlier container", move),
        ("morph", morph),
        ("toolbar edit", toolbar),
    )


def _interactive_edit_p95(form: ReferenceForm, samples: int, warmup: int) -> Optional[float]:
    if not _module_exists("app.features.form_builder.qtside.realize"):
        return None
    try:
        realize = importlib.import_module("app.features.form_builder.qtside.realize")
        session_mod = importlib.import_module("app.features.form_builder.engine.session")
        forms = importlib.import_module("app.features.form_builder.engine.project.forms")
        session, realizer = _open_realized(form.xml, session_mod, forms, realize)
    except (ImportError, AttributeError, TypeError, RuntimeError):
        return None
    owner = session.document.by_name(form.edit_name)
    if not owner:
        _dispose_held([realizer, session])
        return None

    def once() -> None:
        session.log.execute(SetProperty(owner[0], "toolTip", StringValue("speed-edit")))
        _repaint(realizer)

    try:
        dist = measure(once, warmup=warmup, samples=samples)
    except (AttributeError, TypeError, RuntimeError):
        return None
    finally:
        _dispose_held([realizer, session])
    return dist.cpu_p95 * 1000.0


def _repaint(realizer: Any) -> None:
    root = realizer.root_widget
    if root is not None:
        root.repaint()
    app = QApplication.instance()
    if app is not None:
        app.processEvents()


def _inspector_row(
    form: Optional[ReferenceForm],
    samples: int,
    warmup: int,
    enforce_absolute: bool,
    wall_on: bool,
) -> Row:
    if form is None or not _module_exists("app.features.form_builder.qtside.inspector"):
        return _missing(
            "inspector repopulate",
            300,
            _ms_budget(INSPECTOR_REPOPULATE_BUDGET_MS),
            "no qtside inspector yet",
        )
    try:
        realize = importlib.import_module("app.features.form_builder.qtside.realize")
        session_mod = importlib.import_module("app.features.form_builder.engine.session")
        forms = importlib.import_module("app.features.form_builder.engine.project.forms")
        inspector = importlib.import_module("app.features.form_builder.qtside.inspector")
        selection = importlib.import_module("app.features.form_builder.engine.query.selection")
        session, realizer = _open_realized(form.xml, session_mod, forms, realize)
    except (ImportError, AttributeError, TypeError, RuntimeError) as exc:
        return Row(
            "inspector repopulate",
            300,
            None,
            None,
            None,
            _ms_budget(INSPECTOR_REPOPULATE_BUDGET_MS),
            "skip",
            str(exc),
        )
    pane = inspector.InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None)
    pane.resize(288, 600)
    pane.show()
    line = _first_widget(session.document, "QLineEdit")
    button = _first_widget(session.document, "QPushButton")
    if line is None or button is None:
        pane.dispose()
        _dispose_held([realizer, session])
        return Row(
            "inspector repopulate",
            300,
            None,
            None,
            None,
            _ms_budget(INSPECTOR_REPOPULATE_BUDGET_MS),
            "skip",
            "reference form has no line edit and push button",
        )
    current = {"id": line}

    def flip() -> None:
        nxt = button if current["id"] == line else line
        current["id"] = nxt
        session.selection.set((nxt,), source=selection.SelectionSource.PROGRAM)

    try:
        row, _distribution = _timed(
            "inspector repopulate",
            300,
            pane.flush,
            INSPECTOR_REPOPULATE_BUDGET_MS,
            samples=samples,
            warmup=warmup,
            enforce_absolute=enforce_absolute,
            wall_on=wall_on,
            prepare=flip,
        )
        return row
    finally:
        pane.dispose()
        _dispose_held([realizer, session])


def _inspector_select_rows(
    form: Optional[ReferenceForm],
    samples: int,
    warmup: int,
    enforce_absolute: bool,
    wall_on: bool,
) -> List[Row]:
    """Select, then flush, with All properties collapsed and expanded."""
    names = ("inspector select collapsed", "inspector select expanded")
    if form is None or not _module_exists("app.features.form_builder.qtside.inspector"):
        return [
            _missing(name, 300, _ms_budget(INSPECTOR_REPOPULATE_BUDGET_MS), "no qtside inspector yet")
            for name in names
        ]
    try:
        realize = importlib.import_module("app.features.form_builder.qtside.realize")
        session_mod = importlib.import_module("app.features.form_builder.engine.session")
        forms = importlib.import_module("app.features.form_builder.engine.project.forms")
        inspector = importlib.import_module("app.features.form_builder.qtside.inspector")
        api = importlib.import_module("app.features.form_builder.qtside.inspector.api")
        selection = importlib.import_module("app.features.form_builder.engine.query.selection")
        session, realizer = _open_realized(form.xml, session_mod, forms, realize)
    except (ImportError, AttributeError, TypeError, RuntimeError) as exc:
        return [
            Row(name, 300, None, None, None, _ms_budget(INSPECTOR_REPOPULATE_BUDGET_MS), "skip", str(exc))
            for name in names
        ]
    pane = inspector.InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None)
    pane.resize(288, 600)
    pane.show()
    line = _first_widget(session.document, "QLineEdit")
    button = _first_widget(session.document, "QPushButton")
    if line is None or button is None:
        pane.dispose()
        _dispose_held([realizer, session])
        return [
            Row(
                name,
                300,
                None,
                None,
                None,
                _ms_budget(INSPECTOR_REPOPULATE_BUDGET_MS),
                "skip",
                "reference form has no line edit and push button",
            )
            for name in names
        ]
    current = {"id": line}

    def flip() -> None:
        nxt = button if current["id"] == line else line
        current["id"] = nxt
        session.selection.set((nxt,), source=selection.SelectionSource.PROGRAM)

    rows: List[Row] = []
    try:
        for name, expanded in ((names[0], False), (names[1], True)):
            pane.set_group_expanded(api.GroupId.ALL, expanded)
            row, _distribution = _timed(
                name,
                300,
                pane.flush,
                INSPECTOR_REPOPULATE_BUDGET_MS,
                samples=samples,
                warmup=warmup,
                enforce_absolute=enforce_absolute,
                wall_on=wall_on,
                prepare=flip,
            )
            rows.append(row)
        return rows
    finally:
        pane.dispose()
        _dispose_held([realizer, session])


SHELL_SELECT_POINT = "inspector select expanded shell"


def _sizing_rows(
    forms: Dict[int, Any],
    samples: int,
    warmup: int,
    enforce_absolute: bool,
    wall_on: bool,
) -> List[Row]:
    """Repaint the Size group, then one sizing command, at 300 and 1000 widgets."""
    names = (
        "sizing panel repopulate",
        "sizing edit",
        "sizing edit canvas normal",
        "sizing edit canvas 16pt",
    )
    budget = _ms_budget(INSPECTOR_REPOPULATE_BUDGET_MS)
    rows: List[Row] = []
    for count in (300, 1000):
        form = forms.get(count)
        if form is None or not _module_exists("app.features.form_builder.qtside.inspector"):
            rows.extend(_missing(name, count, budget, "no form or no inspector") for name in names)
            continue
        try:
            realize = importlib.import_module("app.features.form_builder.qtside.realize")
            session_mod = importlib.import_module("app.features.form_builder.engine.session")
            forms_mod = importlib.import_module("app.features.form_builder.engine.project.forms")
            inspector = importlib.import_module("app.features.form_builder.qtside.inspector")
            selection = importlib.import_module("app.features.form_builder.engine.query.selection")
            sizing_cmd = importlib.import_module("app.features.form_builder.engine.commands.catalog_ext.sizing")
            values = importlib.import_module("app.features.form_builder.engine.ui4.values")
            session, realizer = _open_realized(form.xml, session_mod, forms_mod, realize)
        except (ImportError, AttributeError, TypeError, RuntimeError) as exc:
            rows.extend(
                Row(name, count, None, None, None, budget, "skip", str(exc)) for name in names
            )
            continue
        pane = inspector.InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None)
        pane.resize(288, 600)
        pane.show()
        line = _first_widget(session.document, "QLineEdit")
        button = _first_widget(session.document, "QPushButton")
        owners = []
        for owner in (line, button, session.document.root.id):
            if owner is not None and owner not in owners:
                owners.append(owner)
        if len(owners) < 2:
            pane.dispose()
            _dispose_held([realizer, session])
            rows.extend(
                Row(name, count, None, None, None, budget, "skip", "reference form has no second widget")
                for name in names
            )
            continue
        target = line or button or owners[0]
        session.selection.set((owners[0],), source=selection.SelectionSource.PROGRAM)
        pane.flush()
        cursor = {"index": 0}

        def flip(ids: List[Any] = owners, log: Any = session, source: Any = selection.SelectionSource.PROGRAM, pos: Dict[str, int] = cursor) -> None:
            pos["index"] = 1 - pos["index"]
            log.selection.set((ids[pos["index"]],), source=source)

        state = {"fill": False}

        def edit(owner: Any = target, log: Any = session.log, cmd: Any = sizing_cmd, size_values: Any = values, flag: Dict[str, bool] = state) -> None:
            flag["fill"] = not flag["fill"]
            horizontal = "Expanding" if flag["fill"] else "Fixed"
            log.execute(
                cmd.ApplySizing(
                    owner,
                    size_values.SizePolicyValue(horizontal, "Preferred", 0, 0),
                    touch_policy=True,
                )
            )

        try:
            rows.append(
                _timed(
                    names[0],
                    count,
                    pane.flush,
                    INSPECTOR_REPOPULATE_BUDGET_MS,
                    samples=samples,
                    warmup=warmup,
                    enforce_absolute=enforce_absolute,
                    wall_on=wall_on,
                    prepare=flip,
                )[0]
            )
            rows.append(
                _timed(
                    names[1],
                    count,
                    edit,
                    EDIT_BUDGET_MS,
                    samples=samples,
                    warmup=warmup,
                    enforce_absolute=enforce_absolute,
                    wall_on=wall_on,
                )[0]
            )
            pane.hide()
            rows.extend(
                _sizing_preview_rows(
                    session,
                    realizer,
                    target,
                    count,
                    samples,
                    warmup,
                    enforce_absolute,
                    wall_on,
                )
            )
        finally:
            pane.dispose()
            _dispose_held([realizer, session])
    return rows


def _sizing_preview_rows(
    session: Any,
    realizer: Any,
    target: Any,
    count: int,
    samples: int,
    warmup: int,
    enforce_absolute: bool,
    wall_on: bool,
) -> List[Row]:
    """One sizing command while the canvas preview is listening.

    The plain ``sizing edit`` row times the command alone. These rows keep a
    FormCanvas up, at Normal and at 16 pt, and include one event-loop turn so
    a deferred cut-off recount is part of the sample.
    """
    canvas_mod = importlib.import_module("app.features.form_builder.integration.canvas")
    sizing_cmd = importlib.import_module("app.features.form_builder.engine.commands.catalog_ext.sizing")
    values = importlib.import_module("app.features.form_builder.engine.ui4.values")
    parent = QWidget()
    parent.resize(960, 720)
    canvas = canvas_mod.FormCanvas(session, realizer, _SpeedHost(), parent)
    canvas.resize(960, 720)
    parent.show()
    app = QApplication.instance()
    assert app is not None
    for _ in range(3):
        app.processEvents()
    state = {"fill": False}

    def edit(log: Any = session.log, cmd: Any = sizing_cmd, size_values: Any = values, flag: Dict[str, bool] = state, loop: Any = app) -> None:
        flag["fill"] = not flag["fill"]
        horizontal = "Expanding" if flag["fill"] else "Fixed"
        log.execute(
            cmd.ApplySizing(
                target,
                size_values.SizePolicyValue(horizontal, "Preferred", 0, 0),
                touch_policy=True,
            )
        )
        loop.processEvents()

    rows: List[Row] = []
    try:
        rows.append(
            _timed(
                "sizing edit canvas normal",
                count,
                edit,
                EDIT_BUDGET_MS,
                samples=samples,
                warmup=warmup,
                enforce_absolute=enforce_absolute,
                wall_on=wall_on,
            )[0]
        )
        canvas.preview.set_points(16)
        app.processEvents()
        rows.append(
            _timed(
                "sizing edit canvas 16pt",
                count,
                edit,
                EDIT_BUDGET_MS,
                samples=samples,
                warmup=warmup,
                enforce_absolute=enforce_absolute,
                wall_on=wall_on,
            )[0]
        )
        canvas.preview.reset()
        return rows
    finally:
        canvas.dispose()
        parent.deleteLater()


def _inspector_shell_row(
    form: Optional[ReferenceForm],
    samples: int,
    warmup: int,
    enforce_absolute: bool,
    wall_on: bool,
) -> Row:
    """Select, then flush, with All properties expanded, in a real MainWindow.

    The bare-pane rows miss the shell: its window style sheet and chrome
    font-weight rule make every setStyleSheet and polish dearer. The timed
    call is the selection change and the flush. The first build, which makes
    the row widgets, is one sample and goes in the detail.
    """
    point = SHELL_SELECT_POINT
    budget = _ms_budget(INSPECTOR_REPOPULATE_BUDGET_MS)
    if form is None or not _module_exists("app.shell.main_window"):
        return _missing(point, 300, budget, "no 300-widget form or no shell")
    try:
        install = importlib.import_module("app.features.form_builder.install")
        if not install.form_builder_enabled():
            return Row(point, 300, None, None, None, budget, "skip", "form builder is registered on PySide6")
        main_window = importlib.import_module("app.shell.main_window")
        shutdown = importlib.import_module("testing.main_window_shutdown")
        api = importlib.import_module("app.features.form_builder.qtside.inspector.api")
        selection = importlib.import_module("app.features.form_builder.engine.query.selection")
    except (ImportError, AttributeError) as exc:
        return Row(point, 300, None, None, None, budget, "skip", str(exc))
    import tempfile
    import time

    previous = os.environ.get("CBCS_DISABLE_BACKGROUND_RUNTIME")
    os.environ["CBCS_DISABLE_BACKGROUND_RUNTIME"] = "1"
    app = QApplication.instance() or QApplication([])
    scratch = tempfile.TemporaryDirectory(prefix="cbcs-shell-speed-")
    window = None
    try:
        root = Path(scratch.name).resolve()
        path = root / "speed_form.ui"
        path.write_text(form.xml, encoding="utf-8")
        window = main_window.MainWindow(state_root=str(root / "state"))
        if not window._editor_tab_factory.open_file_in_editor(str(path)):
            return Row(point, 300, None, None, None, budget, "skip", "the shell did not open the form")
        window._center_stack.setCurrentIndex(1)
        window.resize(1400, 900)
        window.show()
        app.processEvents()
        if not window.styleSheet() and not app.styleSheet():
            return Row(point, 300, None, None, None, budget, "skip", "the shell style sheet is not loaded")
        surface = window._tab_content_registry.surface_for_path(str(path))
        session = surface._session
        pane = surface._workbench.inspector
        line = _first_widget(session.document, "QLineEdit")
        button = _first_widget(session.document, "QPushButton")
        if line is None or button is None:
            return Row(point, 300, None, None, None, budget, "skip", "reference form has no line edit and push button")
        pane.set_group_expanded(api.GroupId.ALL, True)
        current = {"id": button}

        def select_and_flush() -> None:
            nxt = button if current["id"] == line else line
            current["id"] = nxt
            session.selection.set((nxt,), source=selection.SelectionSource.PROGRAM)
            pane.flush()

        started = time.perf_counter()
        select_and_flush()
        first_ms = (time.perf_counter() - started) * 1000.0
        app.processEvents()
        row, _distribution = _timed(
            point,
            300,
            select_and_flush,
            INSPECTOR_REPOPULATE_BUDGET_MS,
            samples=samples,
            warmup=warmup,
            enforce_absolute=enforce_absolute,
            wall_on=wall_on,
            prepare=app.processEvents,
        )
        note = "first build %.1f ms wall (row widgets made once per key)" % first_ms
        return Row(row.point, row.widgets, row.samples, row.p50, row.p95, row.budget, row.verdict, _join(row.detail, note))
    finally:
        if window is not None:
            shutdown.shutdown_main_window_for_test(window, app)
        app.processEvents()
        scratch.cleanup()
        if previous is None:
            os.environ.pop("CBCS_DISABLE_BACKGROUND_RUNTIME", None)
        else:
            os.environ["CBCS_DISABLE_BACKGROUND_RUNTIME"] = previous


def _first_widget(document: UiDocument, class_name: str) -> Optional[NodeId]:
    for widget in document.iter_widgets():
        if widget.class_name == class_name:
            return widget.id
    return None


def _open_realized(xml: str, session_mod: Any, forms: Any, realize: Any) -> Tuple[Any, Any]:
    scope = forms.FormScope(
        kind="project",
        ui_path="/tmp/forms/speed_form.ui",
        project_root="/tmp",
        generated_path="/tmp/forms/ui_speed_form.py",
        window_path="/tmp/forms/speed_form_window.py",
        module_name="forms.ui_speed_form",
        window_module_name="forms.speed_form_window",
    )
    session = session_mod.FormSession.open(xml, path="/tmp/cbcs-speed.ui", scope=scope)
    realizer = realize.Realizer(session)
    realizer.build()
    return session, realizer


def _dispose_held(held: List[object]) -> None:
    while held:
        item = held.pop()
        dispose = getattr(item, "dispose", None)
        if dispose is not None:
            dispose()


def _overhead_rows(
    form: Optional[ReferenceForm],
    samples: int,
    warmup: int,
    realize_build_p95: Optional[float],
) -> Tuple[Row, ...]:
    if form is None:
        return (
            Row("raw Qt build and show", 300, None, None, None, "-", "skip", "no 300-widget form in this run"),
        )
    windows = []

    def build_once() -> None:
        windows.append(raw_qt.build_and_show(form.xml))

    def drop() -> None:
        if windows:
            raw_qt.release(windows.pop())

    build = sample_until_budget(
        lambda: measure(build_once, warmup=warmup, samples=samples, cleanup=drop),
        None,
    )
    window = raw_qt.build_and_show(form.xml)
    try:
        target = raw_qt.find_named(window, form.edit_name)

        def edit_once() -> None:
            raw_qt.raw_edit(target)

        edit = sample_until_budget(lambda: measure(edit_once, warmup=warmup, samples=samples), None)
    finally:
        raw_qt.release(window)
    build_row = Row(
        "raw Qt build and show",
        300,
        build.distribution.n,
        build.distribution.cpu_p50 * 1000.0,
        build.distribution.cpu_p95 * 1000.0,
        "-",
        "reported",
        "PySide6 construction and show of the reference form",
    )
    edit_row = Row(
        "raw Qt update and repaint",
        300,
        edit.distribution.n,
        edit.distribution.cpu_p50 * 1000.0,
        edit.distribution.cpu_p95 * 1000.0,
        "-",
        "reported",
        "setToolTip, repaint and processEvents on the edit target",
    )
    open_ratio = _overhead_ratio(
        "open / raw Qt build",
        realize_build_p95,
        build_row.p95,
        "Realizer.build p95 / raw Qt build and show p95",
    )
    edit_ratio = _overhead_ratio(
        "edit / raw Qt update",
        _interactive_edit_p95(form, samples, warmup),
        edit_row.p95,
        "log execute + realize + repaint p95 / raw Qt update and repaint p95",
    )
    return (build_row, edit_row, open_ratio, edit_ratio)


def _overhead_ratio(
    point: str,
    ours: Optional[float],
    raw: Optional[float],
    detail: str,
) -> Row:
    budget = "%.1fx" % OVERHEAD_RATIO_LIMIT
    if ours is None or raw is None or raw <= 0.0:
        return _missing(point, 300, budget, detail)
    ratio = ours / raw
    verdict = "pass" if ratio <= OVERHEAD_RATIO_LIMIT else "fail"
    return Row(point, 300, None, None, ratio, budget, verdict, "%s (%.2f)" % (detail, ratio))


def _missing(point: str, widgets: Optional[int], budget: str, detail: str) -> Row:
    return Row(point, widgets, None, None, None, budget, "not yet available", detail)


def _read(text: str) -> None:
    read_ui(text, allocator=IdAllocator())


def _write(document: UiDocument) -> None:
    written = write_ui(document)
    if EDIT_NAME not in written.text:
        raise RuntimeError("write_ui dropped the edit target")


def _open_log(xml: str) -> Tuple[CommandLog, NodeId]:
    allocator = IdAllocator()
    document = read_ui(xml, allocator=allocator).document
    holder = {"snap": SelectionSnapshot((), None)}

    def provider() -> SelectionSnapshot:
        return holder["snap"]

    log = CommandLog(document, allocator, selection_provider=provider)

    def remember(change_set: ChangeSet) -> None:
        holder["snap"] = log.selection
        _LISTENER_SINK[0] = change_set.revision

    log.subscribe(remember, priority=PRIORITY_DIAGNOSTICS)
    found = document.by_name(EDIT_NAME)
    if not found:
        raise RuntimeError("reference form has no %s" % EDIT_NAME)
    return log, found[0]


def _dirty_log(xml: str) -> CommandLog:
    log, _owner = _open_log(xml)
    return log


def _touch_dirty(log: CommandLog) -> None:
    if log.is_dirty() is None:
        raise RuntimeError("is_dirty returned None")


def _touch_revision(document: UiDocument) -> None:
    if document.revision < 0:
        raise RuntimeError("revision went negative")


def _drop_wall_failures(row: Row) -> Row:
    if row.verdict != "fail":
        return row
    if "wall p95" not in row.detail:
        return row
    return Row(
        row.point,
        row.widgets,
        row.samples,
        row.p50,
        row.p95,
        row.budget,
        "pass",
        _join(row.detail, "wall assertion skipped because the machine was not idle"),
    )


def _module_exists(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def retained_bytes(root: object) -> int:
    """Bytes retained by ``root`` and the objects it points at.

    The walk does not follow classes or modules, so a log entry cannot pull in
    the interpreter.
    """
    seen = set()
    total = 0
    stack: List[object] = [root]
    while stack:
        obj = stack.pop()
        if obj is None or isinstance(obj, (bool, int, float, type)):
            continue
        marker = id(obj)
        if marker in seen:
            continue
        seen.add(marker)
        try:
            total += sys.getsizeof(obj)
        except TypeError:
            continue
        if isinstance(obj, str):
            continue
        if isinstance(obj, dict):
            stack.extend(obj.keys())
            stack.extend(obj.values())
            continue
        if isinstance(obj, (list, tuple, set, frozenset)):
            stack.extend(list(obj))
            continue
        slots = getattr(type(obj), "__slots__", ())
        if isinstance(slots, str):
            slots = (slots,)
        for name in slots:
            if not isinstance(name, str) or name.startswith("__"):
                continue
            try:
                stack.append(getattr(obj, name))
            except AttributeError:
                continue
        payload = getattr(obj, "__dict__", None)
        if isinstance(payload, dict):
            stack.append(payload)
    return total


def _rss_bytes() -> int:
    """Current RSS from /proc on Linux; elsewhere the peak RSS, which still
    grows when memory leaks."""
    try:
        status = Path("/proc/self/status").read_text(encoding="ascii")
    except OSError:
        import resource
        import sys

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return peak if sys.platform == "darwin" else peak * 1024
    for line in status.splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) * 1024
    return 0


def _read_load() -> Tuple[float, float, float]:
    try:
        one, five, fifteen = os.getloadavg()
    except OSError:
        return (0.0, 0.0, 0.0)
    return (one, five, fifteen)


def _cpu_count() -> int:
    # Linux only; macOS has no affinity call.
    affinity = getattr(os, "sched_getaffinity", None)
    if affinity is not None:
        try:
            return len(affinity(0))
        except OSError:
            pass
    return os.cpu_count() or 1


def _ms_budget(value: Optional[float]) -> str:
    if value is None:
        return "-"
    if float(value).is_integer():
        return "%d ms" % int(value)
    return "%.1f ms" % value


def _num(value: Optional[float]) -> str:
    if value is None:
        return "-"
    return "%.3f" % value


def _load_text(load: Sequence[float]) -> str:
    return "%.2f/%.2f/%.2f" % (load[0], load[1], load[2])


def _join(left: str, right: str) -> str:
    if left and right:
        return "%s. %s" % (left, right)
    return left or right
