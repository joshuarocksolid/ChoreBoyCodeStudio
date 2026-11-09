"""Problems fix buttons for the style sheet codes (FB033, FB034, FB038)."""

from __future__ import annotations

from app.features.form_builder.engine.commands.catalog import SetProperty
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.integration.problem_fixes import FixContext, ProblemFix
from app.features.form_builder.qtside.style import gateway

TITLE = "Edit style sheet"
_SELECTOR = '*[cbcsInvalid="true"]'
_OUTLINE = '*[cbcsInvalid="true"] { border: 1px solid #c62828; }'


def edit_style_sheet(context: FixContext) -> None:
    gateway.open_drawer(context.session, context.diagnostic.location.node_id)


def add_outline_style(context: FixContext) -> None:
    root = context.session.document.root
    if not isinstance(root, WidgetNode):
        return
    current = ""
    value = root.value("styleSheet")
    if isinstance(value, StringValue):
        current = value.text
    if _SELECTOR in current:
        return
    text = current.rstrip()
    text = (text + "\n" + _OUTLINE) if text else _OUTLINE
    with context.session.log.transaction("Add the red outline style") as txn:
        txn.execute(
            SetProperty(root.id, "styleSheet", StringValue(text), undo_label="Add the red outline style")
        )


def register(registry: object) -> None:
    for code in ("FB033", "FB034"):
        registry.add(ProblemFix(code, "edit-style-sheet", TITLE, edit_style_sheet))  # type: ignore[attr-defined]
    registry.add(  # type: ignore[attr-defined]
        ProblemFix("FB038", "add-outline", "Add the red outline style", add_outline_style)
    )
