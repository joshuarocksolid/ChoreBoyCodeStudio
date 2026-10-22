"""Unit tests for whitelisted REPL runtime introspection."""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from app.intelligence.completion_models import CompletionKind
from app.intelligence.runtime_introspection import RuntimeIntrospectionCoordinator, RuntimeIntrospectionQuery
from app.intelligence.runtime_members import (
    RuntimeMemberDetail,
    RuntimeMemberListing,
    RuntimeMemberRef,
    RuntimeUnavailable,
)
from app.runner import repl_introspection
from app.runner.repl_introspection import (
    ReplIntrospectionService,
    is_whitelisted_target_path,
)
from app.qt.qt_compat import QT_API

pytestmark = pytest.mark.unit

_SYNTHETIC_PATH = "PySide2.Synthetic"


def _use_synthetic_target(monkeypatch: pytest.MonkeyPatch, target: Any) -> None:
    monkeypatch.setattr(repl_introspection, "is_whitelisted_target_path", lambda path: path == _SYNTHETIC_PATH)
    monkeypatch.setattr(repl_introspection, "resolve_whitelisted_target", lambda _path: target)


def _listing(service: ReplIntrospectionService) -> RuntimeMemberListing:
    listing = service.list_members(_SYNTHETIC_PATH)
    assert isinstance(listing, RuntimeMemberListing)
    return listing


def test_is_whitelisted_target_path_accepts_trusted_modules() -> None:
    assert is_whitelisted_target_path("PySide2.QtCore")
    assert is_whitelisted_target_path("FreeCAD")
    assert not is_whitelisted_target_path("os.path")


def test_list_members_rejects_non_whitelisted_target() -> None:
    assert isinstance(ReplIntrospectionService().list_members("os.path"), RuntimeUnavailable)


def test_member_sorting_after_600_names_survives_cache_and_prefix_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attributes: dict[str, Any] = {f"Aaa{index:03d}": index for index in range(600)}
    attributes.update({f"_private{index:03d}": index for index in range(50)})
    attributes["zz_wanted"] = 1
    _use_synthetic_target(monkeypatch, type("Synthetic", (), attributes))
    coordinator = RuntimeIntrospectionCoordinator(runner_port=ReplIntrospectionService())
    query = RuntimeIntrospectionQuery(target_path=_SYNTHETIC_PATH, member_prefix="")

    coordinator.fetch_and_cache_from_runner(query, max_results=500)
    cached_all = coordinator.cached_items(query)
    cached_wanted = coordinator.cached_items(
        RuntimeIntrospectionQuery(target_path=_SYNTHETIC_PATH, member_prefix="zz_"),
        max_results=500,
    )

    assert cached_all is not None
    assert "zz_wanted" in {item.label for item in cached_all}
    assert {item.side_effect_risk for item in cached_all} == {""}
    assert {item.resolvable_fields for item in cached_all} == {("documentation", "signature")}
    assert [item.label for item in cached_wanted or []] == ["zz_wanted"]


def test_list_members_keeps_names_that_getattr_would_break(monkeypatch: pytest.MonkeyPatch) -> None:
    descriptor_reads: list[str] = []

    class Exploding:
        def __get__(self, instance: object, owner: object = None) -> object:
            descriptor_reads.append("exploding")
            raise RuntimeError("descriptor must not be read while listing")

    class Dynamic:
        exploding = Exploding()

        def __dir__(self) -> list[str]:
            return ["exploding", "virtual_only"]

        def __getattr__(self, name: str) -> object:
            descriptor_reads.append(name)
            if name == "virtual_only":
                return 1
            raise AttributeError(name)

    _use_synthetic_target(monkeypatch, Dynamic())

    kinds = {member.name: member.kind for member in _listing(ReplIntrospectionService()).public}

    assert descriptor_reads == []
    assert kinds == {"exploding": CompletionKind.ATTRIBUTE, "virtual_only": CompletionKind.ATTRIBUTE}


def test_list_members_classifies_class_members_statically(monkeypatch: pytest.MonkeyPatch) -> None:
    class Sample:
        @property
        def size(self) -> int:
            return 1

        @staticmethod
        def build() -> None:
            return None

        @classmethod
        def create(cls) -> None:
            return None

        def run(self) -> None:
            return None

        Inner = int
        value = 3

    _use_synthetic_target(monkeypatch, Sample)

    kinds = {member.name: member.kind for member in _listing(ReplIntrospectionService()).public}

    assert kinds == {
        "Inner": CompletionKind.CLASS,
        "build": CompletionKind.FUNCTION,
        "create": CompletionKind.METHOD,
        "run": CompletionKind.METHOD,
        "size": CompletionKind.PROPERTY,
        "value": CompletionKind.ATTRIBUTE,
    }


def test_resolve_member_reads_live_pyside_signature_and_first_doc_paragraph() -> None:
    qt_widgets = pytest.importorskip("app.qt.QtWidgets")
    live_doc = inspect.getdoc(qt_widgets.QPushButton.setText) or ""

    detail = ReplIntrospectionService().resolve_member(
        RuntimeMemberRef(target_path=QT_API + ".QtWidgets.QPushButton", name="setText")
    )

    assert isinstance(detail, RuntimeMemberDetail)
    assert detail.signature.startswith("setText(")
    assert detail.owner == "QAbstractButton method"
    assert "setText(" not in detail.documentation
    assert detail.documentation in live_doc
