"""JSON-line protocol helpers for Python Console metadata requests."""

from __future__ import annotations

from dataclasses import asdict
import json
from typing import Any

from app.intelligence.completion_models import CompletionEnvelope, CompletionItem, CompletionKind

REPL_CONTROL_PROTOCOL = "cbcs_repl_control_v1"


def completion_item_to_dict(item: CompletionItem) -> dict[str, Any]:
    """Serialize a completion item for the REPL control channel."""

    payload = asdict(item)
    payload["kind"] = item.kind.value
    return payload


def completion_item_from_dict(payload: dict[str, Any]) -> CompletionItem:
    """Parse a completion item from the REPL control channel."""

    try:
        kind = CompletionKind(str(payload.get("kind", CompletionKind.SYMBOL.value)))
    except ValueError:
        kind = CompletionKind.SYMBOL
    return CompletionItem(
        label=str(payload.get("label") or ""),
        insert_text=str(payload.get("insert_text") or payload.get("label") or ""),
        kind=kind,
        detail=str(payload.get("detail") or ""),
        documentation=str(payload.get("documentation") or ""),
        signature=str(payload.get("signature") or ""),
        return_type=str(payload.get("return_type") or ""),
        source_file_path=payload.get("source_file_path") if isinstance(payload.get("source_file_path"), str) else None,
        engine=str(payload.get("engine") or ""),
        source=str(payload.get("source") or ""),
        confidence=str(payload.get("confidence") or ""),
        semantic_kind=str(payload.get("semantic_kind") or ""),
        replacement_start=_optional_int(payload.get("replacement_start")),
        replacement_end=_optional_int(payload.get("replacement_end")),
        trigger_kind=str(payload.get("trigger_kind") or ""),
        trigger_character=str(payload.get("trigger_character") or ""),
        side_effect_risk=str(payload.get("side_effect_risk") or ""),
    )


def envelope_to_dict(envelope: CompletionEnvelope) -> dict[str, Any]:
    """Serialize a completion envelope for JSON transport."""

    return {
        "items": [completion_item_to_dict(item) for item in envelope.items],
        "degradation_reason": envelope.degradation_reason,
        "source": envelope.source,
        "confidence": envelope.confidence,
    }


def envelope_from_dict(payload: dict[str, Any]) -> CompletionEnvelope:
    """Parse a completion envelope from JSON transport."""

    raw_items = payload.get("items", [])
    items = [
        completion_item_from_dict(item)
        for item in raw_items
        if isinstance(item, dict)
    ] if isinstance(raw_items, list) else []
    return CompletionEnvelope(
        items=items,
        degradation_reason=str(payload.get("degradation_reason") or ""),
        source=str(payload.get("source") or ""),
        confidence=str(payload.get("confidence") or ""),
    )


def dumps_message(payload: dict[str, Any]) -> bytes:
    """Return one UTF-8 JSON-line protocol message."""

    return (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")


def loads_message(raw_line: bytes) -> dict[str, Any]:
    """Parse one UTF-8 JSON-line protocol message."""

    payload = json.loads(raw_line.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("REPL control message must be a JSON object.")
    return payload


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None
