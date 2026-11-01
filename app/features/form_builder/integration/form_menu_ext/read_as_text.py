"""Form > Read Behavior as Text. Same page as the Logic panel link."""

from __future__ import annotations

from typing import Any

from app.features.form_builder.integration.form_menu_ext import FormMenuItem


def _open(surface: Any) -> None:
    from app.features.form_builder.qtside.logic_panel.read_as_text import show_behavior_text

    show_behavior_text(surface)


def register(registry: Any) -> None:
    registry.add(
        FormMenuItem(
            "form.action.readBehaviorAsText",
            ("Read Behavior as Text",),
            _open,
            rank=0,
        )
    )
