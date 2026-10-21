"""Behavior tests for the form-builder parity ledger."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import pytest

from tools.form_builder_parity import (
    Code,
    MarkerScan,
    MarkerUse,
    Paths,
    build,
    derive,
    junit_findings,
    parse_junit,
    parse_ledger,
    parse_plan_wps,
    render_markdown,
    scan_source,
    validate,
)
import tools.form_builder_parity_seed as seed

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
REL = "tests/form_builder/engine/test_layout_ops.py"
NODE = "tests/form_builder/a.py::test_a"
FAKE_PLAN = "\n".join(
    [
        "| WP | Work |",
        "| --- | --- |",
        "| M1.1 | Owner of every fixture row |",
        "| M9.9 | Idle package |",
        "",
    ]
)
P23_TEST = (
    "Opening a fixture of 400 rows paints a first screen and allows a selection. "
    "The runtime check loads the same file with QUiLoader in the preview process. "
    "The test records the time. It does not assert a number until a baseline exists."
)


def valid_ledger_dict() -> dict:
    cuts = [1, 26, 51, 76, 101, 126, 151, 176, 201, 226, 251, 276, 301, 331]
    areas = [
        {"name": f"Area {index + 1}", "first": cuts[index], "last": cuts[index + 1] - 1}
        for index in range(13)
    ]
    r3 = [
        {
            "id": f"R3-{number}",
            "name": f"Item {number}",
            "storage": None,
            "complexity": None,
            "wp": "M1.1",
        }
        for number in range(1, 331)
    ]
    pains = [
        {
            "id": f"P-{rank}",
            "title": f"Pain {rank}",
            "pain": f"Sentence {rank}.",
            "wp": "M1.1",
            "r3": ["R3-1"],
            "test": f"Do the thing {rank}.",
        }
        for rank in range(1, 26)
    ]
    logic = [
        {
            "id": "L-line-total-live",
            "title": "Line total",
            "kind": "scenario",
            "source": "LOGIC_DESIGN.md §7.3",
            "wp": "M1.1",
        }
    ]
    return {
        "schema": 1,
        "areas": areas,
        "r3": r3,
        "pains": pains,
        "logic": logic,
        "wps_without_items": ["M9.9"],
    }


def _evaluate(data: dict, uses: Sequence[MarkerUse]) -> Tuple[object, Tuple[object, ...]]:
    ledger, findings = parse_ledger(json.dumps(data))
    assert ledger is not None, findings
    assert findings == ()
    scan = MarkerScan(tuple(uses), ())
    plan = parse_plan_wps(FAKE_PLAN)
    view = derive(ledger, scan, plan)
    return view, validate(view, scan)


def _codes(findings: Sequence[object]) -> List[Code]:
    return [finding.code for finding in findings]


def _junit(cases: Sequence[Tuple[str, str, Optional[str]]]) -> str:
    parts = ["<testsuite>"]
    for classname, name, kind in cases:
        if kind:
            parts.append(
                f'<testcase classname="{classname}" name="{name}"><{kind} message="no"/></testcase>'
            )
        else:
            parts.append(f'<testcase classname="{classname}" name="{name}"/>')
    parts.append("</testsuite>")
    return "".join(parts)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            """\
            import pytest

            @pytest.mark.parity("R3-35")
            def test_wrap(doc):
                pass
            """,
            [("R3-35", REL + "::test_wrap", True)],
        ),
        (
            """\
            import pytest

            @pytest.mark.parity("R3-35", "R3-36")
            def test_wrap(doc):
                pass
            """,
            [
                ("R3-35", REL + "::test_wrap", True),
                ("R3-36", REL + "::test_wrap", True),
            ],
        ),
        (
            """\
            import pytest

            @pytest.mark.parity("R3-52")
            class TestGridSpans:
                def test_span(self):
                    pass
            """,
            [("R3-52", REL + "::TestGridSpans", True)],
        ),
        (
            """\
            import pytest

            pytestmark = [
                pytest.mark.logic("L-logic-references"),
                pytest.mark.parity("R3-1"),
            ]

            def test_a():
                pass
            """,
            [
                ("L-logic-references", REL, True),
                ("R3-1", REL, True),
            ],
        ),
        (
            """\
            import pytest

            @pytest.mark.parametrize(
                "n",
                [pytest.param(1, marks=pytest.mark.parity("R3-10"))],
            )
            def test_nums(n):
                pass
            """,
            [("R3-10", REL + "::test_nums", True)],
        ),
        (
            """\
            import pytest

            @pytest.mark.skip
            @pytest.mark.parity("R3-1")
            def test_a():
                pass
            """,
            [("R3-1", REL + "::test_a", False)],
        ),
        (
            """\
            import pytest

            @pytest.mark.xfail(reason="later")
            class TestA:
                @pytest.mark.parity("R3-1")
                def test_a(self):
                    pass
            """,
            [("R3-1", REL + "::TestA::test_a", False)],
        ),
        (
            """\
            import pytest

            pytestmark = pytest.mark.skip(reason="later")

            @pytest.mark.parity("R3-1")
            def test_a():
                pass
            """,
            [("R3-1", REL + "::test_a", False)],
        ),
        (
            """\
            import pytest

            @pytest.mark.skipif(True, reason="qt")
            @pytest.mark.parity("R3-3")
            def test_qt():
                pass
            """,
            [("R3-3", REL + "::test_qt", True)],
        ),
        (
            """\
            import pytest

            @pytest.mark.pain("P-3")
            async def test_async():
                pass
            """,
            [("P-3", REL + "::test_async", True)],
        ),
    ],
)
def test_scan_source_attributes_markers(source: str, expected: list) -> None:
    scanned = scan_source(textwrap.dedent(source), REL)
    got = [(use.key, use.node_id, use.proving) for use in scanned.uses]
    assert got == expected
    assert scanned.findings == ()


@pytest.mark.parametrize(
    ("source", "code"),
    [
        (
            """\
            import pytest

            @pytest.mark.parity(f"R3-{1}")
            def test_a():
                pass
            """,
            Code.MARKER_BAD_ARG,
        ),
        (
            """\
            import pytest

            name = "R3-1"

            @pytest.mark.parity(name)
            def test_a():
                pass
            """,
            Code.MARKER_BAD_ARG,
        ),
        (
            """\
            import pytest

            @pytest.mark.parity("P-3")
            def test_a():
                pass
            """,
            Code.MARKER_BAD_ARG,
        ),
        (
            """\
            import pytest

            @pytest.mark.parity("R3-1")
            def build():
                pass
            """,
            Code.MARKER_OUTSIDE_TEST,
        ),
        (
            """\
            from pytest import mark

            @mark.parity("R3-1")
            def test_foo():
                pass
            """,
            Code.MARKER_BAD_ARG,
        ),
    ],
)
def test_scan_source_rejects_bad_markers(source: str, code: Code) -> None:
    scanned = scan_source(textwrap.dedent(source), REL)
    assert code in _codes(scanned.findings)
    assert scanned.uses == ()


@pytest.mark.parametrize(
    "label",
    [
        "todo",
        "done",
        "unproving",
        "wont_do",
        "wont_do_marked",
        "wont_do_blank",
        "unknown_key",
        "junit_not_passed",
    ],
)
def test_status_precedence(label: str) -> None:
    data = valid_ledger_dict()
    uses: List[MarkerUse] = []
    if label == "done":
        uses = [
            MarkerUse("R3-1", "tests/form_builder/b.py::test_b", 2, True),
            MarkerUse("R3-1", "tests/form_builder/a.py::test_a", 1, True),
        ]
    elif label == "unproving":
        uses = [MarkerUse("R3-1", NODE, 4, False)]
    elif label == "wont_do":
        data["r3"][0]["wont_do"] = {"reason": "C++ only.", "approved_in": "O-logic gate"}
    elif label == "wont_do_marked":
        data["r3"][0]["wont_do"] = {"reason": "C++ only.", "approved_in": "O-logic gate"}
        uses = [MarkerUse("R3-1", NODE, 4, True)]
    elif label == "wont_do_blank":
        data["r3"][0]["wont_do"] = {"reason": "because", "approved_in": ""}
        uses = [MarkerUse("R3-1", NODE, 4, True)]
    elif label == "unknown_key":
        uses = [MarkerUse("R3-999", NODE, 4, True)]
    elif label == "junit_not_passed":
        uses = [MarkerUse("R3-1", NODE, 4, True)]

    view, findings = _evaluate(data, uses)
    codes = _codes(findings)
    if label == "unknown_key":
        assert Code.MARKER_UNKNOWN_KEY in codes
        return
    derived = view.derived["R3-1"]
    if label == "todo":
        assert derived.status == "todo"
        assert derived.tests == ()
        assert codes == []
    elif label == "done":
        assert derived.status == "done"
        assert derived.tests == (
            "tests/form_builder/a.py::test_a",
            "tests/form_builder/b.py::test_b",
        )
        assert codes == []
    elif label == "unproving":
        assert derived.status == "todo"
        assert derived.tests == ()
        assert codes == [Code.UNPROVING_MARKER]
    elif label == "wont_do":
        assert derived.status == "wont_do"
        assert derived.tests == ()
        assert codes == []
    elif label == "wont_do_marked":
        assert derived.status == "wont_do"
        assert derived.tests == ()
        assert Code.MARKER_ON_WONT_DO in codes
    elif label == "wont_do_blank":
        assert derived.status == "wont_do"
        assert derived.tests == ()
        assert Code.WONT_DO_UNAPPROVED in codes
    elif label == "junit_not_passed":
        extra = junit_findings(
            view,
            parse_junit(_junit([("tests.form_builder.a", "test_a", "skipped")])),
        )
        assert derived.status == "done"
        assert derived.tests == (NODE,)
        assert _codes(extra) == [Code.NOT_PASSED]


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("drop_r3", Code.R3_COVERAGE),
        ("duplicate_r3", Code.R3_COVERAGE),
        ("r3_331", Code.R3_COVERAGE),
        ("area_gap", Code.AREA_TILING),
        ("area_overlap", Code.AREA_TILING),
        ("unknown_wp", Code.UNKNOWN_WP),
        ("idle_wp", Code.IDLE_WP),
        ("stale_exemption", Code.STALE_EXEMPTION),
        ("blank_approved", Code.WONT_DO_UNAPPROVED),
        ("status_key", Code.SCHEMA),
        ("pain_cites_unknown", Code.PAIN_COVERAGE),
        ("duplicate_logic", Code.DUPLICATE_KEY),
        ("duplicate_json_key", Code.SCHEMA),
    ],
)
def test_ledger_invariant_violations(mutation: str, code: Code) -> None:
    data = valid_ledger_dict()
    raw: Optional[str] = None
    if mutation == "drop_r3":
        data["r3"] = [row for row in data["r3"] if row["id"] != "R3-200"]
    elif mutation == "duplicate_r3":
        data["r3"].append(dict(data["r3"][4]))
    elif mutation == "r3_331":
        data["r3"].append(
            {
                "id": "R3-331",
                "name": "Extra",
                "storage": None,
                "complexity": None,
                "wp": "M1.1",
            }
        )
    elif mutation == "area_gap":
        data["areas"][0]["last"] = 24
    elif mutation == "area_overlap":
        data["areas"][1]["first"] = 25
    elif mutation == "unknown_wp":
        data["r3"][0]["wp"] = "M99.9"
    elif mutation == "idle_wp":
        data["wps_without_items"] = []
    elif mutation == "stale_exemption":
        data["wps_without_items"] = ["M1.1", "M9.9"]
    elif mutation == "blank_approved":
        data["r3"][0]["wont_do"] = {"reason": "because", "approved_in": "  "}
    elif mutation == "status_key":
        data["r3"][0]["status"] = "done"
    elif mutation == "pain_cites_unknown":
        data["pains"][0]["r3"] = ["R3-999"]
    elif mutation == "duplicate_logic":
        data["logic"].append(dict(data["logic"][0]))
    elif mutation == "duplicate_json_key":
        raw = '{"schema": 1, "schema": 1, "areas": [], "r3": [], "pains": [], "logic": [], "wps_without_items": []}'
    if raw is None:
        raw = json.dumps(data)
    ledger, findings = parse_ledger(raw)
    if ledger is None:
        assert code in _codes(findings)
        return
    plan = parse_plan_wps(FAKE_PLAN)
    view = derive(ledger, MarkerScan((), ()), plan)
    findings = tuple(findings) + validate(view, MarkerScan((), ()))
    assert code in _codes(findings)


@pytest.mark.parametrize(
    ("cases", "node_id", "codes"),
    [
        (
            [("tests.form_builder.a", "test_a", None)],
            NODE,
            frozenset(),
        ),
        (
            [("tests.form_builder.a", "test_a", "skipped")],
            NODE,
            frozenset({Code.NOT_PASSED}),
        ),
        (
            [("tests.form_builder.a", "test_a[left]", None)],
            NODE,
            frozenset(),
        ),
        (
            [("tests.form_builder.a.TestGrid", "test_span", None)],
            "tests/form_builder/a.py::TestGrid",
            frozenset(),
        ),
        (
            [
                ("tests.form_builder.a", "test_a[a]", None),
                ("tests.form_builder.a", "test_a[b]", "failure"),
            ],
            NODE,
            frozenset({Code.NOT_PASSED}),
        ),
        (
            [("tests.form_builder.a", "test_other", None)],
            NODE,
            frozenset({Code.JUNIT_GAP}),
        ),
        (
            [("tests.form_builder.a", "test_a", "error")],
            NODE,
            frozenset({Code.NOT_PASSED}),
        ),
        (
            [
                ("tests.form_builder.a", "test_a[a]", None),
                ("tests.form_builder.a", "test_a[b]", "skipped"),
            ],
            NODE,
            frozenset({Code.NOT_PASSED}),
        ),
        (
            [
                ("tests.form_builder.a.TestGrid", "test_one", None),
                ("tests.form_builder.a.TestGrid", "test_two", "failure"),
            ],
            "tests/form_builder/a.py::TestGrid",
            frozenset({Code.NOT_PASSED}),
        ),
    ],
)
def test_junit_crosscheck(cases: list, node_id: str, codes: frozenset) -> None:
    view, findings = _evaluate(valid_ledger_dict(), [MarkerUse("R3-1", node_id, 1, True)])
    assert findings == ()
    extra = junit_findings(view, parse_junit(_junit(cases)))
    assert view.derived["R3-1"].status == "done"
    assert frozenset(_codes(extra)) == codes


def test_junit_gap_does_not_demote_day_to_day_status(tmp_path: Path) -> None:
    docs = tmp_path / "docs" / "form_builder"
    docs.mkdir(parents=True)
    (docs / "parity.json").write_text(json.dumps(valid_ledger_dict()), encoding="utf-8")
    (docs / "PLAN.md").write_text(FAKE_PLAN, encoding="utf-8")
    tests = tmp_path / "tests" / "form_builder"
    tests.mkdir(parents=True)
    (tests / "test_item.py").write_text(
        textwrap.dedent(
            """\
            import pytest

            @pytest.mark.parity("R3-1")
            def test_a():
                pass
            """
        ),
        encoding="utf-8",
    )
    paths = Paths.for_repo(tmp_path)
    plain = build(paths)
    assert plain.view is not None
    assert plain.errors == ()
    assert plain.view.derived["R3-1"].status == "done"

    missing = tmp_path / "missing.xml"
    missing.write_text(_junit([("tests.form_builder.other", "test_z", None)]), encoding="utf-8")
    gapped = build(paths, junit=missing)
    assert gapped.view is not None
    assert gapped.view.derived["R3-1"].status == "done"
    assert Code.JUNIT_GAP in _codes(gapped.errors)

    mixed = tmp_path / "mixed.xml"
    mixed.write_text(
        _junit(
            [
                ("tests.form_builder.test_item", "test_a[a]", None),
                ("tests.form_builder.test_item", "test_a[b]", "failure"),
            ]
        ),
        encoding="utf-8",
    )
    failed = build(paths, junit=mixed)
    assert failed.view is not None
    assert failed.view.derived["R3-1"].status == "done"
    assert Code.NOT_PASSED in _codes(failed.errors)
    assert Code.JUNIT_GAP not in _codes(failed.errors)


def test_seed_refuses_second_write(tmp_path: Path) -> None:
    dest = tmp_path / "parity.json"
    assert seed.main(["--out", str(dest)]) == 0
    first = dest.read_bytes()
    assert seed.main(["--out", str(dest)]) == 2
    assert dest.read_bytes() == first


def test_seed_of_real_sources(tmp_path: Path) -> None:
    dest = tmp_path / "parity.json"
    assert seed.main(["--out", str(dest)]) == 0
    report = build(
        Paths(
            ledger=dest,
            plan=REPO_ROOT / "docs" / "form_builder" / "PLAN.md",
            rendered=tmp_path / "PARITY.md",
            tests_root=REPO_ROOT / "tests" / "form_builder",
            repo=REPO_ROOT,
        )
    )
    assert report.errors == ()
    assert report.view is not None
    ledger = report.view.ledger
    assert len(ledger.r3) == 330
    assert len(ledger.pains) == 25
    assert len(ledger.logic) == 45
    by_id = {item.entry.key: item for item in ledger.r3}
    assert by_id["R3-145"].entry.wp == "M3.1b"
    assert by_id["R3-146"].entry.wp == "M3.1b"
    assert by_id["R3-148"].entry.wp == "M4.3a"
    assert by_id["R3-159"].entry.wp == "M4.3b"
    assert by_id["R3-164"].entry.wp == "M4.3c"
    assert by_id["R3-227"].entry.wp == "M1.1a"
    assert by_id["R3-322"].entry.wp == "M1.3"
    assert by_id["R3-330"].entry.wp == "M1.3"
    pains = {pain.entry.key: pain for pain in ledger.pains}
    assert pains["P-23"].entry.wp == "M1.3"
    assert pains["P-23"].test == P23_TEST
    assert pains["P-23"].r3 == ("R3-177",)
    logic = {feature.entry.key: feature for feature in ledger.logic}
    assert logic["L-line-total-live"].entry.wp == "M7.2"
    assert "M1.5" in ledger.wps_without_items
    assert "M3.1b" not in ledger.wps_without_items
    assert "M1.1a" not in ledger.wps_without_items
    assert "wont_do" not in dest.read_text(encoding="utf-8")
    assert '"status"' not in dest.read_text(encoding="utf-8")


def test_committed_ledger_is_valid() -> None:
    report = build(Paths.for_repo(REPO_ROOT))
    assert report.errors == ()


def test_render_twice_is_byte_identical() -> None:
    report = build(Paths.for_repo(REPO_ROOT))
    assert report.view is not None
    assert report.errors == ()
    first = render_markdown(report.view)
    second = render_markdown(report.view)
    assert first == second
    assert "Generated by `tools/form_builder_parity.py`" in first
    assert "Do not edit by hand." in first
