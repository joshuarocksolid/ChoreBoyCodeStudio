"""Team Sync budgets. Assertions use the spec numbers.

Measured milliseconds are appended to /tmp/team_sync_budgets.json.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import time

import pytest

from app.features.team_sync.core.merge3way import merge_lines
from app.features.team_sync.core.mailbox import MailScan
from app.features.team_sync.core.repo import TeamRepo
from app.features.team_sync.core.service import TeamSyncService
from app.features.shop_sharing.model import Machine
from tests.unit.features.team_sync.conftest import write_account

pytestmark = [pytest.mark.integration, pytest.mark.performance, pytest.mark.timeout(180)]

_RECORD = Path("/tmp/team_sync_budgets.json")
_HEADROOM = 1


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
    import io
    import zipfile

    account = write_account(tmp_path / "Mails", "maple", "sam@example.test")
    for index in range(50):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(
                "m/_headers_",
                "Subject: CBCS-SYNC/1 note p_aaaaaaaaaaaaaaaa Notes\r\nFrom: A <a@b.test>\r\n\r\n",
            )
            archive.writestr("m/textfile0", "CBCS-SYNC/1\nverb: note\n")
        (account / "zip_in" / f"cbcs_{index:03d}.zip").write_bytes(buffer.getvalue())
    for index in range(200):
        (account / "zip_in" / f"other_{index:03d}.txt").write_text("mail\n", encoding="utf-8")
    scan = MailScan(roots=(str(account),))
    scan.scan()
    started = time.perf_counter()
    assert scan.scan() == []
    elapsed = (time.perf_counter() - started) * 1000
    _budget(elapsed, 20, "scan_nothing_new")


def test_history_of_210_commits(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    for index in range(500):
        folder = root / f"mod_{index // 20:02d}"
        folder.mkdir(exist_ok=True)
        lines = "\n".join(f"line {index} {row}" for row in range(100)) + "\n"
        (folder / f"file_{index:03d}.py").write_text(lines, encoding="utf-8")
    repo = TeamRepo(str(root))
    repo.init_repo()
    now = datetime.now(timezone.utc)
    repo.commit("seed", "Sam", "sam@example.test", "aaaa1111", "pc", now)
    for index in range(1, 210):
        for offset in range(3):
            number = (index * 3 + offset) % 500
            path = root / f"mod_{number // 20:02d}" / f"file_{number:03d}.py"
            path.write_text(path.read_text(encoding="utf-8") + f"# {index}\n", encoding="utf-8")
        repo.commit(str(index), "Sam", "sam@example.test", "aaaa1111", "pc", now)
    started = time.perf_counter()
    page = repo.history(limit=200)
    elapsed = (time.perf_counter() - started) * 1000
    assert len(page) == 200
    assert page[0].files == ()
    _budget(elapsed, 200, "history_210")


def test_history_flat_directory_and_first_paint(tmp_path: Path, qapp: object) -> None:
    """500 files in one directory used to make history walk every tree. The list must not."""
    del qapp
    root = tmp_path / "flat"
    root.mkdir()
    for index in range(500):
        (root / f"file_{index:03d}.py").write_text(f"value = {index}\n", encoding="utf-8")
    repo = TeamRepo(str(root))
    repo.init_repo()
    now = datetime.now(timezone.utc)
    repo.commit("seed", "Sam", "sam@example.test", "aaaa1111", "pc", now)
    for index in range(1, 210):
        for offset in range(3):
            number = (index * 3 + offset) % 500
            path = root / f"file_{number:03d}.py"
            path.write_text(path.read_text(encoding="utf-8") + f"# {index}\n", encoding="utf-8")
        repo.commit(str(index), "Sam", "sam@example.test", "aaaa1111", "pc", now)
    started = time.perf_counter()
    page = repo.history(limit=200)
    elapsed = (time.perf_counter() - started) * 1000
    assert len(page) == 200
    assert page[0].files == ()
    _budget(elapsed, 200, "history_flat_210")

    from app.features.team_sync.ui.history_tab import HistoryTab
    from app.features.team_sync.ui.ports import SyncPorts
    from app.qt.QtWidgets import QApplication

    class _HistoryApi:
        def history(self, **kwargs: object) -> object:
            return repo.history(**kwargs)  # type: ignore[arg-type]

        def change_diff(self, change_id: str, against: object = None) -> object:
            return repo.diff_commits(change_id, against if isinstance(against, str) else None)

    tab = HistoryTab()
    started = time.perf_counter()
    tab.open_history(
        _HistoryApi(),
        SyncPorts(),
        show_lanes=False,
        show_ids=False,
        advanced=False,
        on_action=lambda _key, _change: None,
    )
    elapsed = (time.perf_counter() - started) * 1000
    assert tab._list.count() == 200
    _budget(elapsed, 200, "history_tab_paint")
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    tab.deleteLater()


def test_status_with_three_incoming(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    for index in range(80):
        (root / f"file_{index:03d}.py").write_text(f"value = {index}\n", encoding="utf-8")
    mails = tmp_path / "Mails"
    account = write_account(mails, "maple", "sam@example.test")
    (mails / ".pc-watchdog").write_text(
        datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8"
    )
    service = TeamSyncService(
        str(root),
        machine=Machine(
            home=tmp_path / "home",
            hostname="pc",
            local_state=tmp_path / "state",
            default_home=tmp_path / "default",
        ),
        mail_roots=[str(account)],
    )
    from app.features.team_sync.api import ShareRequest

    service.share(ShareRequest(project_name="Incoming", my_name="Sam", my_shop="Maple"))
    seed = service._repo.create_bundle("main", [])
    peer = TeamRepo(str(tmp_path / "peer"))
    peer.init_repo()
    refs = peer.import_pack(seed)
    peer.checkout(refs["refs/heads/main"], "main")
    previous = refs["refs/heads/main"]
    for index in range(3):
        (Path(peer.root) / "file_000.py").write_text(f"peer {index}\n", encoding="utf-8")
        tip = peer.commit(str(index), "Ana", "ana@example.test", "bbbb2222", "pc", datetime.now(timezone.utc))
        bundle = peer.create_bundle("main", [previous])
        service._import_bundle_bytes(
            bundle,
            from_id="bbbb2222",
            bundle_id=f"b_{index:016x}",
            verified=True,
        )
        previous = tip
    assert len(service.incoming()) == 3
    started = time.perf_counter()
    status = service.status()
    elapsed = (time.perf_counter() - started) * 1000
    assert status.waiting == 3
    _budget(elapsed, 150, "status_3_incoming")


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
    from app.features.team_sync.api import Member, ShareRequest
    from app.features.team_sync.core.team import load_team, replace_member, save_team

    service.share(ShareRequest(project_name="Three", my_name="Sam", my_shop="Maple"))
    team = load_team(root)
    assert team is not None
    save_team(root, replace_member(team, Member("bbbb2222", "Ana", "Cedar", "ana@example.test")))
    me = service._require_me()
    service._repo.commit(
        "Ana joined",
        me.name,
        me.email,
        me.member_id,
        "pc",
        datetime.now(timezone.utc),
        paths=["cbcs/team.json"],
    )
    for name in ("a.py", "b.py", "c.py"):
        (root / name).write_text(name + " changed\n", encoding="utf-8")
    started = time.perf_counter()
    service.send("three files")
    elapsed = (time.perf_counter() - started) * 1000
    assert any((account / "out").iterdir())
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
