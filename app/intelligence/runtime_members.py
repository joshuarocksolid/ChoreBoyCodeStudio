"""Runtime member listing for whitelisted REPL targets, shared by runner and editor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Union

from app.intelligence.completion_models import CompletionItem, CompletionKind

RUNTIME_INTROSPECTION_PROVIDER = "runtime_introspection"
RUNTIME_RESOLVABLE_FIELDS: tuple[str, ...] = ("documentation", "signature")

_ITEM_ID_PREFIX = RUNTIME_INTROSPECTION_PROVIDER + ":"


@dataclass(frozen=True)
class RuntimeMember:
    """One name on a runtime target plus a kind derived without calling getattr."""

    name: str
    kind: CompletionKind


@dataclass(frozen=True)
class RuntimeMemberListing:
    """Every non-dunder name of one target, partitioned by a leading underscore.

    Build it with ``from_members``. The listing is never capped. ``visible`` is
    the only place a display limit applies, and it never spends a slot on a
    private name.
    """

    target_path: str
    public: tuple[RuntimeMember, ...]
    private: tuple[RuntimeMember, ...]

    @classmethod
    def from_members(cls, target_path: str, members: Sequence[RuntimeMember]) -> RuntimeMemberListing:
        return cls(
            target_path=target_path,
            public=tuple(member for member in members if not member.name.startswith("_")),
            private=tuple(member for member in members if member.name.startswith("_")),
        )

    def visible(self, prefix: str, *, limit: Optional[int] = None) -> list[CompletionItem]:
        """Popup items for ``prefix``. A ``_`` prefix reads private names uncapped."""

        lowered = prefix.lower()
        if prefix.startswith("_"):
            matches = [member for member in self.private if member.name.lower().startswith(lowered)]
        else:
            matches = [member for member in self.public if member.name.lower().startswith(lowered)]
            if limit is not None:
                matches = matches[: max(0, limit)]
        return [self._item(member) for member in matches]

    def _item(self, member: RuntimeMember) -> CompletionItem:
        return CompletionItem(
            label=member.name,
            insert_text=member.name,
            kind=member.kind,
            detail=f"{self.target_path} member",
            engine=RUNTIME_INTROSPECTION_PROVIDER,
            source=RUNTIME_INTROSPECTION_PROVIDER,
            confidence="runtime_inspection",
            item_id=RuntimeMemberRef(target_path=self.target_path, name=member.name).item_id,
            resolve_provider=RUNTIME_INTROSPECTION_PROVIDER,
            resolvable_fields=RUNTIME_RESOLVABLE_FIELDS,
        )


@dataclass(frozen=True)
class RuntimeMemberRef:
    """Address of one member. Owns the ``item_id`` format for runtime items.

    Target paths are dotted identifiers and names are identifiers, so ``:``
    separates them unambiguously.
    """

    target_path: str
    name: str

    @property
    def item_id(self) -> str:
        return f"{_ITEM_ID_PREFIX}{self.target_path}:{self.name}"

    @classmethod
    def from_item(cls, item: CompletionItem) -> Optional[RuntimeMemberRef]:
        if not item.item_id.startswith(_ITEM_ID_PREFIX):
            return None
        target_path, _, name = item.item_id[len(_ITEM_ID_PREFIX):].rpartition(":")
        if not target_path or not name:
            return None
        return cls(target_path=target_path, name=name)


@dataclass(frozen=True)
class RuntimeMemberDetail:
    """Lazily resolved metadata for one member."""

    signature: str
    documentation: str


@dataclass(frozen=True)
class RuntimeUnavailable:
    """Why a runtime listing or resolve produced nothing. Never cached."""

    reason: str


RuntimeListingResult = Union[RuntimeMemberListing, RuntimeUnavailable]
RuntimeDetailResult = Union[RuntimeMemberDetail, RuntimeUnavailable]


def first_paragraph(doc: str) -> str:
    """Return text up to the first blank line, stripped."""

    lines: list[str] = []
    for line in doc.strip().splitlines():
        if not line.strip():
            break
        lines.append(line)
    return "\n".join(lines).strip()
