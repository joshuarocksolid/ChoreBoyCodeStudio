"""Font editor registration. The popover lives in ``qtside.visual``.

The summary gains the Text colour swatch when the widget's own style sheet sets
one (UX-STYLE-011): "Sans Serif, 14 pt, Bold, then a square and the colour as hex".
"""

from __future__ import annotations

from app.features.form_builder.engine.style import colour_rows
from app.features.form_builder.engine.style.colors import hex_text
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import FontValue
from app.features.form_builder.qtside.inspector.api import EditorKey, Mixed, Registrar, RowValue
from app.features.form_builder.qtside.visual.font import FontEditor, font_summary


class FontColourEditor(FontEditor):
    def show(self, value: RowValue) -> None:
        super().show(value)
        if isinstance(value, Mixed):
            return
        colour = self._own_colour()
        if colour is None:
            return
        plain = font_summary(self._font if self._written else None, mixed=False)
        self._summary.set_summary("%s · ■ %s" % (plain, hex_text(*colour)))

    def _own_colour(self):  # type: ignore[no-untyped-def]
        owners = self._host.owner_ids()
        if len(owners) != 1:
            return None
        document = self._host.document()
        node = document.get(owners[0])
        if not isinstance(node, WidgetNode):
            return None
        return colour_rows.own_text_color(document, owners[0])


def register(registrar: Registrar) -> None:
    registrar.editor(EditorKey(FontValue.ELEMENT), FontColourEditor, baseline=True)


__all__ = ["FontColourEditor", "register"]
