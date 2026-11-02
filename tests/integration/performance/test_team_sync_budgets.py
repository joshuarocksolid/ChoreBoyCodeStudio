"""Team Sync budgets. Assertions leave headroom for a busy CI runner.

The spec numbers are the product budget. The assertion is three times that,
which still fails a real regression and does not flake on a loaded runner.
Measured milliseconds are appended to /tmp/team_sync_budgets.json.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import time

import pytest

from app.features.team_sync.core.merge3way import merge_lines
from app.features.team_sync.core.mailbox import MailScan, publish_out, render_message
from app.features.team_sync.core.repo import TeamRepo
from app.features.team_sync.core.service import TeamSyncService
from app.features.shop_sharing.model import Machine
from tests.unit.features.team_sync.conftest import write_account

pytestmark = [pytest.mark.integration, pytest.mark.performance, pytest.mark.timeout(180)]

_RECORD = Path("/tmp/team_sync_budgets.json")
_HEADROOM = 3


def _note(name: str, elapsed_ms: float, budget_ms: float) -> None:
    payload = {}
    if _RECORD.is_file():
        payload = json.loads(_RECORD.read_text(encoding="utf-8"))
    payload[name] = {"measured_ms": round(elapsed_ms, 2), "budget_ms": budget_ms}
    _RECORD.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _budget(elapsed_ms: float, budget_ms: float, name: str) -> None:
    _note(name, elapsed_ms, budget_ms)
    assert elapsed_ms <= budget_ms * _HEADROOM, f"{name} took {elapsed_ms:.1f} ms"


def test_status_of_500_files(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    for index in range(500):
        (root / f"file_{index:03d}.py").write_text(f"VALUE = {index}\n", encoding="utf-8")
    repo = TeamRepo(str(root))
    repo.init_repo()
    repo.commit("seed", "Sam", "sam@example.test", "aaaa1111", "pc", datetime.now(timezone.utc))
    started = time.perf_counter()
    changes = repo.status()
    elapsed = (time.perf_counter() - started) * 1000
    assert changes == []
    _budget(elapsed, 150, "status_500")


def test_inbound_scan_with_nothing_new(tmp_path: Path) -> None:
    account = write_account(tmp_path / "Mails", "maple", "sam@example.test")
    (account / "zip_in" / "19990101010101010!.zip").write_bytes(b"PK\x03\x04not ours")
    scan = MailScan(roots=(str(account),))
    scan.scan()
    started = time.perf_counter()
    assert scan.scan() == []
    elapsed = (time.perf_counter() - started) * 1000
    _budget(elapsed, 20, "scan_nothing_new")


def test_send_three_files(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    mails = tmp_path / "Mails"
    account = write_account(mails, "maple", "sam@example.test")
    (mails / ".pc-watchdog").write_text(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")
    for name in ("a.py", "b.py", "c.py"):
        (root / name).write_text(name + "\n", encoding="utf-8")
    service = TeamSyncService(
        str(root),
        machine=Machine(home=tmp_path / "home", hostname="pc", local_state=tmp_path / "state", default_home=tmp_path / "default"),
        mail_roots=[str(account)],
    )
    from app.features.team_sync.api import ShareRequest

    service.share(ShareRequest(project_name="Three", my_name="Sam", my_shop="Maple"))
    for name in ("a.py", "b.py", "c.py"):
        (root / name).write_text(name + " changed\n", encoding="utf-8")
    started = time.perf_counter()
    service.save_only("three files")
    bundle = service._repo.create_bundle("main", [])
    message = render_message(
        sender_name="Sam",
        sender_email="sam@example.test",
        recipient_name="Ana",
        recipient_email="ana@example.test",
        subject="CBCS-SYNC/1 push p_perf Three",
        body="CBCS-SYNC/1\nverb: push\n",
        when=datetime.now(timezone.utc),
        message_id="perf@three",
    )
    publish_out(account, "20261102120000099", message, {"Three.cbcsbundle": bundle})
    elapsed = (time.perf_counter() - started) * 1000
    assert (account / "out").is_dir()
    _budget(elapsed, 1000, "send_3_files")


def test_import_50_commit_bundle(tmp_path: Path) -> None:
    origin = tmp_path / "origin"
    origin.mkdir()
    target = origin / "mod.py"
    target.write_text("value = 0\n", encoding="utf-8")
    repo = TeamRepo(str(origin))
    repo.init_repo()
    now = datetime.now(timezone.utc)
    repo.commit("0", "Sam", "sam@example.test", "aaaa1111", "pc", now)
    for index in range(1, 50):
        target.write_text(f"value = {index}\n", encoding="utf-8")
        repo.commit(str(index), "Sam", "sam@example.test", "aaaa1111", "pc", now)
    bundle = repo.create_bundle("main", [])
    copy = TeamRepo(str(tmp_path / "copy"))
    copy.init_repo()
    started = time.perf_counter()
    refs = copy.import_pack(bundle)
    elapsed = (time.perf_counter() - started) * 1000
    assert copy.count_since(refs["refs/heads/main"], []) == 50
    _budget(elapsed, 2000, "import_50")


def test_merge_2000_line_file() -> None:
    base = tuple(f"line {index}" for index in range(2000))
    ours = list(base)
    theirs = list(base)
    ours[10] = "ours"
    theirs[1500] = "theirs"
    started = time.perf_counter()
    merged = merge_lines(base, tuple(ours), tuple(theirs))
    elapsed = (time.perf_counter() - started) * 1000
    assert merged.merged_lines() is not None
    _budget(elapsed, 150, "merge_2000")


def test_history_first_page_of_1000(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    path = root / "only.py"
    path.write_text("value = 0\n", encoding="utf-8")
    repo = TeamRepo(str(root))
    repo.init_repo()
    now = datetime.now(timezone.utc)
    repo.commit("0", "Sam", "sam@example.test", "aaaa1111", "pc", now)
    for index in range(1, 1000):
        path.write_text(f"value = {index}\n", encoding="utf-8")
        repo.commit(str(index), "Sam", "sam@example.test", "aaaa1111", "pc", now)
    started = time.perf_counter()
    page = repo.history(limit=200)
    elapsed = (time.perf_counter() - started) * 1000
    assert len(page) == 200
    _budget(elapsed, 200, "history_page")


def test_blame_2000_lines(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    path = root / "wide.py"
    path.write_text("\n".join(f"line {index}" for index in range(2000)) + "\n", encoding="utf-8")
    repo = TeamRepo(str(root))
    repo.init_repo()
    now = datetime.now(timezone.utc)
    repo.commit("seed", "Sam", "sam@example.test", "aaaa1111", "pc", now)
    text = path.read_text(encoding="utf-8").replace("line 3", "line 3 edited")
    path.write_text(text, encoding="utf-8")
    repo.commit("edit", "Ana", "ana@example.test", "bbbb2222", "pc", now)
    started = time.perf_counter()
    lines = repo.blame("wide.py")
    elapsed = (time.perf_counter() - started) * 1000
    assert len(lines) == 2000
    _budget(elapsed, 400, "blame_2000")
