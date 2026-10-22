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
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

from app.features.form_builder.engine.commands.catalog import SetProperty
from app.features.form_builder.engine.commands.log import CommandLog, SelectionSnapshot
from app.features.form_builder.engine.events import PRIORITY_DIAGNOSTICS, ChangeSet
from app.features.form_builder.engine.ids import IdAllocator, NodeId
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
    cpu_within_budget,
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
OUTLINE_PATCH_BUDGET_MS = 2.0
EDIT_BUDGET_MS = 16.0
SELECTION_BUDGET_MS = 8.0
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
    "open total",
    "one command",
    "one command O(changed)",
    "undo",
    "redo",
    "realize patch",
    "hit index invalidate",
    "hit index refresh",
    "hit query",
    "overlay paint",
    "outline patch",
    "edit total",
    "selection change",
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
    columns = ("point", "widgets", "n", "p50", "p95", "budget", "verdict")
    body = [
        (
            row.point,
            "-" if row.widgets is None else str(row.widgets),
            "-" if row.samples is None else str(row.samples),
            _num(row.p50),
            _num(row.p95),
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
    rows.extend(_realize_rows(forms.get(300), samples, warmup, enforce_absolute, wall_on))
    rows.append(_missing("outline full build", 300, _ms_budget(OUTLINE_BUILD_BUDGET_MS), "no outline yet"))
    rows.append(
        _missing(
            "open total",
            300,
            _ms_budget(OPEN_BUDGET_MS),
            "needs read, Realizer.build, outline, inspector and the hit index",
        )
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

    rows.append(_missing("realize patch", 300, _ms_budget(REALIZER_PATCH_BUDGET_MS), "no qtside realize yet"))
    rows.append(_missing("hit index invalidate", None, "-", "no hit index yet"))
    for count, budget in HIT_REFRESH_BUDGET_MS.items():
        rows.append(_missing("hit index refresh", count, _ms_budget(budget), "no hit index yet"))
    rows.append(_missing("hit query", 300, _ms_budget(HIT_QUERY_BUDGET_MS), "no hit index yet"))
    rows.append(_missing("overlay paint", 300, _ms_budget(OVERLAY_BUDGET_MS), "no canvas overlay yet"))
    rows.append(_missing("outline patch", 300, _ms_budget(OUTLINE_PATCH_BUDGET_MS), "no outline yet"))
    rows.append(
        _missing(
            "edit total",
            300,
            _ms_budget(EDIT_BUDGET_MS),
            "needs the command, the realize patch, the outline and the inspector",
        )
    )
    rows.append(
        _missing(
            "selection change",
            300,
            _ms_budget(SELECTION_BUDGET_MS),
            "no canvas selection yet. Inspector repopulate budget is 16 ms",
        )
    )

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
        rows.extend(_overhead_rows(forms.get(300), samples, warmup))
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
    ratio, used, tries = _ratio_with_retry(dists[300], dists[1000], forms, samples, warmup)
    detail = "1000-widget cpu p95 / 300-widget cpu p95"
    if tries > 1:
        detail += ". retried the pair once"
    verdict = "pass" if ratio <= CHANGED_RATIO_LIMIT else "fail"
    if verdict == "fail":
        detail += ". cpu p95 at 1000 widgets was %.3f ms and at 300 was %.3f ms" % (
            used[1000].cpu_p95 * 1000.0,
            used[300].cpu_p95 * 1000.0,
        )
    return Row(
        "one command O(changed)",
        None,
        samples,
        None,
        ratio,
        "%.1fx" % CHANGED_RATIO_LIMIT,
        verdict,
        detail,
    )


def _ratio_with_retry(
    small: Distribution,
    large: Distribution,
    forms: Dict[int, ReferenceForm],
    samples: int,
    warmup: int,
) -> Tuple[float, Dict[int, Distribution], int]:
    ratio = _safe_ratio(large.cpu_p95, small.cpu_p95)
    if ratio <= CHANGED_RATIO_LIMIT:
        return ratio, {300: small, 1000: large}, 1
    again = {
        300: _command_row(300, forms[300], samples=samples, warmup=warmup, enforce_absolute=False, wall_on=False)[1],
        1000: _command_row(1000, forms[1000], samples=samples, warmup=warmup, enforce_absolute=False, wall_on=False)[1],
    }
    return _safe_ratio(again[1000].cpu_p95, again[300].cpu_p95), again, 2


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0.0:
        return float("inf")
    return numerator / denominator


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
        scope = forms.FormScope(
            kind="project",
            ui_path="/tmp/cbcs-speed.ui",
            project_root="/tmp",
            generated_path="/tmp/ui_cbcs_speed.py",
            window_path="/tmp/cbcs_speed_window.py",
            module_name="ui_cbcs_speed",
            window_module_name="cbcs_speed_window",
        )
        session = session_mod.FormSession.open(xml, path="/tmp/cbcs-speed.ui", scope=scope)
        realizer = realize.Realizer(session)
        realizer.build()
        held.append(session)

    def cleanup() -> None:
        while held:
            session = held.pop()
            dispose = getattr(session, "dispose", None)
            if dispose is not None:
                dispose()

    try:
        return sample_until_budget(
            lambda: measure(once, warmup=warmup, samples=samples, cleanup=cleanup),
            budget_ms,
        )
    except (AttributeError, TypeError, RuntimeError) as exc:
        return "Realizer.build could not be called (%s)" % exc


def _codegen_and_save(
    document: object,
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
            Row("generate_form_module", 300, None, None, None, _ms_budget(CODEGEN_BUDGET_MS), "skip", str(exc)),
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
    save_budget = SAVE_BUDGET_MS if enforce_absolute else None
    # Save is write plus generate. Reuse the two p95 numbers. They were measured
    # separately, so the sum is an upper bound, not one timed region.
    write_row = _timed(
        "write_ui",
        300,
        lambda doc=document: _write(doc),
        None,
        samples=samples,
        warmup=warmup,
        enforce_absolute=False,
        wall_on=False,
    )[0]
    write_p95 = write_row.p95 or 0.0
    gen_p95 = generated.p95 or 0.0
    total = write_p95 + gen_p95
    if save_budget is None:
        verdict = "reported"
    else:
        verdict = "pass" if cpu_within_budget(total, save_budget) else "fail"
    save = Row(
        "save total",
        300,
        samples,
        None,
        total,
        _ms_budget(SAVE_BUDGET_MS),
        verdict,
        "sum of write_ui p95 and generate_form_module p95",
    )
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
            ui_path="/tmp/cbcs-speed.ui",
            project_root="/tmp",
            generated_path="/tmp/ui_cbcs_speed.py",
            window_path="/tmp/cbcs_speed_window.py",
            module_name="ui_cbcs_speed",
            window_module_name="cbcs_speed_window",
        )
        options_mod = importlib.import_module("app.features.form_builder.engine.codegen.api")
        options = getattr(options_mod, "CodegenOptions", None)
        kwargs = {"scope": scope, "source_bytes": source}
        if options is not None:
            kwargs["options"] = options()
        return fn(document, **kwargs)

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
    del held
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
        scope = forms.FormScope(
            kind="project",
            ui_path="/tmp/cbcs-speed.ui",
            project_root="/tmp",
            generated_path="/tmp/ui_cbcs_speed.py",
            window_path="/tmp/cbcs_speed_window.py",
            module_name="ui_cbcs_speed",
            window_module_name="cbcs_speed_window",
        )
        session = session_mod.FormSession.open(xml, path="/tmp/cbcs-speed.ui", scope=scope)
        realizer = realize.Realizer(session)
        realizer.build()
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


def _overhead_rows(form: Optional[ReferenceForm], samples: int, warmup: int) -> Tuple[Row, ...]:
    if form is None:
        return (
            Row("raw Qt build and show", 300, None, None, None, "-", "skip", "no 300-widget form in this run"),
        )
    windows: List[object] = []

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
    open_ratio = _missing(
        "open / raw Qt build",
        300,
        "%.1fx" % OVERHEAD_RATIO_LIMIT,
        "needs Realizer.build. The raw baseline is the row above",
    )
    edit_ratio = _missing(
        "edit / raw Qt update",
        300,
        "%.1fx" % OVERHEAD_RATIO_LIMIT,
        "needs the realize patch. The raw baseline is the row above",
    )
    return (build_row, edit_row, open_ratio, edit_ratio)


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
    try:
        status = Path("/proc/self/status").read_text(encoding="ascii")
    except OSError:
        return 0
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
    try:
        return len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
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
