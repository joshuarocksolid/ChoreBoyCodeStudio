"""Spacer rows (R3-46)."""

from __future__ import annotations

from app.features.form_builder.qtside.inspector.api import GroupId, Prop, Registrar, RowSpec


def register(registrar: Registrar) -> None:
    registrar.row(
        RowSpec(
            "sizeType",
            GroupId.CONTENT,
            "Size type",
            "How the gap grows or shrinks when its layout has room.",
            Prop("sizeType"),
            classes=("Spacer",),
        ),
        baseline=True,
    )
