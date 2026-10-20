from __future__ import annotations

from typing import Any, Optional, cast

import pytest

from app.intelligence.completion_models import CompletionItem, CompletionKind, CompletionResolveRequest
from app.intelligence.completion_resolver import CompletionResolver
from app.intelligence.runtime_members import (
    RuntimeMember,
    RuntimeMemberDetail,
    RuntimeMemberListing,
    RuntimeMemberRef,
)

pytestmark = pytest.mark.unit


class _FakeRuntimeMembers:
    def __init__(self, detail: Optional[RuntimeMemberDetail]) -> None:
        self._detail = detail
        self.refs: list[RuntimeMemberRef] = []

    def resolve_member(self, ref: RuntimeMemberRef) -> Optional[RuntimeMemberDetail]:
        self.refs.append(ref)
        return self._detail


def _runtime_item() -> CompletionItem:
    listing = RuntimeMemberListing.from_members(
        "PySide2.QtWidgets.QPushButton",
        [RuntimeMember(name="setText", kind=CompletionKind.METHOD)],
    )
    return listing.visible("set")[0]


def _resolve(runtime_members: _FakeRuntimeMembers, item: CompletionItem) -> CompletionItem:
    resolver = CompletionResolver(semantic_facade=cast(Any, None))
    resolver.bind_runtime_members(runtime_members)
    return resolver.resolve(
        CompletionResolveRequest(
            item=item,
            source_text="",
            cursor_position=0,
            current_file_path="/tmp/sample.py",
            project_root=None,
            context_fingerprint="fp",
        )
    )


def test_runtime_item_resolves_signature_and_documentation_for_its_owner() -> None:
    runtime_members = _FakeRuntimeMembers(RuntimeMemberDetail(signature="(self, text: str)", documentation="Set text."))

    resolved = _resolve(runtime_members, _runtime_item())

    assert runtime_members.refs == [RuntimeMemberRef(target_path="PySide2.QtWidgets.QPushButton", name="setText")]
    assert (resolved.signature, resolved.documentation, resolved.resolvable_fields) == (
        "(self, text: str)",
        "Set text.",
        (),
    )


def test_unavailable_runtime_resolve_leaves_item_unchanged() -> None:
    item = _runtime_item()

    assert _resolve(_FakeRuntimeMembers(None), item) == item
