"""Adapter capability text and results aggregation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[3] / ".cursor/skills/verify-cbcs/scripts"
sys.path.insert(0, str(SCRIPTS))

from scenarios.caps import op_supported  # noqa: E402
from scenarios.adapter import Adapter  # noqa: E402
from scenarios.model import Check, ScenarioResult, status_for, summarize, summary_markdown  # noqa: E402
from scenarios.model import canonical_listing, listing_sha256  # noqa: E402


def test_unknown_ctl_op_is_unsupported():
    text = "unknown ctl op: grab"
    assert op_supported(text, "grab") is False
    assert op_supported(text, "state") is True


def test_widget_error_still_means_the_op_exists():
    text = "RuntimeError: grab missed __verify_cbcs_absent__"
    assert op_supported(text, "grab") is True


def test_invalid_choice_disables_checkpoint():
    text = "cb-slot: error: argument command: invalid choice: 'checkpoint'"
    assert op_supported(text, "checkpoint") is False


def test_status_pass_fail_skip_error():
    ok = [Check("a", True, "1", "1")]
    bad = [Check("a", False, "1", "0")]
    assert status_for(ok, skipped=None, error=None) == "pass"
    assert status_for(bad, skipped=None, error=None) == "fail"
    assert status_for([], skipped="not run", error=None) == "skipped"
    assert status_for(ok, skipped=None, error="boom") == "error"
    assert status_for([], skipped=None, error=None) == "error"


def test_summary_counts_and_markdown():
    results = [
        ScenarioResult("gates", "pass", "t", 1.2, checks=[Check("c", True, "y", "y")]),
        ScenarioResult("cb5", "fail", "t", 2.0, checks=[Check("c", False, "y", "n")]),
        ScenarioResult("cb8", "skipped", "t", 0.0, notes="not run"),
    ]
    payload = summarize(results, run_id="r", started="t", duration_s=3.2)
    assert payload["counts"] == {"pass": 1, "fail": 1, "error": 0, "skipped": 1}
    text = summary_markdown(payload)
    assert "| gates | pass |" in text
    assert "| cb5 | fail |" in text
    assert "skipped 1" in text
    json.dumps(payload)


def test_probe_bridge_falls_back_when_the_host_rejects_the_op():
    def run(args, timeout):
        class Proc:
            returncode = 1
            stdout = ""
            stderr = "unknown ctl op: " + args[3]

        return Proc()

    adapter = Adapter(run=run)
    adapter.sid = "SID"
    adapter.probe_bridge()
    assert adapter.caps.grab is False
    assert adapter.caps.state is False
    assert adapter.caps.drag is False


def test_listing_hash_changes_when_a_size_changes():
    before = [{"path": "/home/default/a", "kind": "file", "size": 3}]
    after = [{"path": "/home/default/a", "kind": "file", "size": 4}]
    same = [{"size": 3, "kind": "file", "path": "/home/default/a"}]
    assert listing_sha256(before) == listing_sha256(same)
    assert listing_sha256(before) != listing_sha256(after)
    assert canonical_listing(before).startswith("/home/default/a\tfile\t3\n")
