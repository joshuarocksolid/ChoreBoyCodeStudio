"""Form > Go to code. Same command as F12."""

from __future__ import annotations

from typing import Any

from app.features.form_builder.integration.form_menu_ext import FormMenuItem
from app.features.form_builder.integration.keys_ext.code import go_to_code


def register(registry: Any) -> None:
    registry.add(FormMenuItem("form.action.goToCode", ("Go to code",), go_to_code, hint="F12", rank=0))
