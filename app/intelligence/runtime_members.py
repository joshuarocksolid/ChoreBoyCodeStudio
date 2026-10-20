from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Union

from app.intelligence.completion_models import CompletionItem, CompletionKind

RUNTIME_INTROSPECTION_PROVIDER = "runtime_introspection"
RUNTIME_RESOLVABLE_FIELDS: tuple[str, ...] = ("documentation", "signature")

_ITEM_ID_PREFIX = RUNTIME_INTROSPECTION_PROVIDER + ":"


@dataclass(frozen=True)
class RuntimeMember:
    name: str
    kind: CompletionKind
    short_type: str = ""


@dataclass(frozen=True)
class RuntimeMemberListing:
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
        """Every member whose name starts with ``prefix`` (any case), public first.

        Private and dunder names are included; the popup ranks private names
        last and shows dunders only after ``_`` is typed. ``limit`` is accepted
        for callers that still pass one, but the list is never cut.
        """

        _ = limit
        lowered = prefix.lower()
        return [
            self._item(member)
            for member in (*self.public, *self.private)
            if member.name.lower().startswith(lowered)
        ]

    def _item(self, member: RuntimeMember) -> CompletionItem:
        return CompletionItem(
            label=member.name,
            insert_text=member.name,
            kind=member.kind,
            detail="",
            engine=RUNTIME_INTROSPECTION_PROVIDER,
            source=RUNTIME_INTROSPECTION_PROVIDER,
            confidence="runtime_inspection",
            semantic_kind=member.short_type or member.kind.value,
            item_id=RuntimeMemberRef(target_path=self.target_path, name=member.name).item_id,
            resolve_provider=RUNTIME_INTROSPECTION_PROVIDER,
            resolvable_fields=RUNTIME_RESOLVABLE_FIELDS,
        )


@dataclass(frozen=True)
class RuntimeMemberRef:
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
    signature: str
    documentation: str
    owner: str = ""


@dataclass(frozen=True)
class RuntimeUnavailable:
    reason: str


RuntimeListingResult = Union[RuntimeMemberListing, RuntimeUnavailable]
RuntimeDetailResult = Union[RuntimeMemberDetail, RuntimeUnavailable]


def first_paragraph(doc: str) -> str:
    lines: list[str] = []
    for line in doc.strip().splitlines():
        if not line.strip():
            break
        lines.append(line)
    return "\n".join(lines).strip()
