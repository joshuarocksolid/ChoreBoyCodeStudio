# pyright: reportAttributeAccessIssue=false
"""A preview flush uses the path the tab has now, including after Save As."""

from __future__ import annotations

from types import SimpleNamespace

from app.shell.editor_tab_factory import flush_open_draft


def test_flush_open_draft_reads_the_path_at_call_time() -> None:
    seen = []
    paths = {"buf": "/shop/invoice.ui"}

    class Workflow:
        def path_for_buffer_id(self, buffer_id: str) -> str:
            return paths[buffer_id]

    class History:
        def flush_pending_autosaves(self, paths_now: tuple) -> None:
            seen.append(paths_now)

    window = SimpleNamespace(
        _editor_tab_workflow=Workflow(),
        _local_history_workflow=History(),
    )
    flush_open_draft(window, "buf")
    paths["buf"] = "/shop/renamed.ui"
    flush_open_draft(window, "buf")
    assert seen == [("/shop/invoice.ui",), ("/shop/renamed.ui",)]
