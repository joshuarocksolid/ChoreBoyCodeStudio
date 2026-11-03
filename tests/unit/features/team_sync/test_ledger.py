"""The ledger is one sqlite file used by the shell's background pool."""

from __future__ import annotations

import threading
from pathlib import Path

from app.features.team_sync.core.ledger import Ledger


def test_a_row_written_on_one_thread_is_readable_on_another(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.sqlite")
    ledger.mark_seen("invite-1", "2026-11-02T21:40:00Z", "ok")
    seen: list = []
    errors: list = []

    def on_other_thread() -> None:
        try:
            seen.append(ledger.has_seen("invite-1"))
            ledger.add_outbox(
                bundle_id="b1",
                recipient="ana@example.test",
                part_idx=1,
                part_total=1,
                verb="invite",
                change_id="c1",
                tip="t1",
                created_at="2026-11-02T21:40:01Z",
                out_folder="20261102214001000",
                state="queued",
            )
        except Exception as exc:
            errors.append(exc)

    worker = threading.Thread(target=on_other_thread)
    worker.start()
    worker.join()
    assert errors == []
    assert seen == [True]
    assert ledger.outbox_part("b1", "ana@example.test", 1) is not None
