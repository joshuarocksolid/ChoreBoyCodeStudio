"""Designer form canvas model host."""

from __future__ import annotations

from PySide2.QtWidgets import QWidget

from app.designer.canvas.drop_rules import can_insert_widget
from app.designer.model import LayoutItem, SpacerItem, UIModel, WidgetNode
from app.designer.palette.widget_registry import PaletteWidgetDefinition


class FormCanvas(QWidget):
    """Canvas host that mutates `UIModel` during insert operations."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model: UIModel | None = None

    @property
    def model(self) -> UIModel | None:
        return self._model

    def load_model(self, model: UIModel) -> None:
        self._model = model

    def insert_palette_widget(
        self,
        *,
        parent_object_name: str,
        definition: PaletteWidgetDefinition,
    ) -> WidgetNode | SpacerItem:
        if self._model is None:
            raise ValueError("No form model loaded.")

        parent_widget = self._model.root_widget.find_by_object_name(parent_object_name)
        if parent_widget is None:
            raise ValueError(f"Parent widget not found: {parent_object_name}")

        parent_has_layout = parent_widget.layout is not None
        if not can_insert_widget(
            parent_class_name=parent_widget.class_name,
            child_class_name=definition.class_name,
            is_layout_item=definition.is_layout_item,
            parent_has_layout=parent_has_layout,
        ):
            raise ValueError(
                "Widget insertion is not allowed for the selected parent."
            )

        if definition.is_layout_item:
            spacer = SpacerItem(name=self._generate_unique_object_name(definition.default_object_name_prefix))
            assert parent_widget.layout is not None
            parent_widget.layout.items.append(LayoutItem(spacer=spacer))
            return spacer

        widget = WidgetNode(
            class_name=definition.class_name,
            object_name=self._generate_unique_object_name(definition.default_object_name_prefix),
        )
        if parent_widget.layout is not None:
            parent_widget.layout.items.append(LayoutItem(widget=widget))
        else:
            parent_widget.children.append(widget)
        return widget

    def _generate_unique_object_name(self, prefix: str) -> str:
        assert self._model is not None
        names = set(self._model.collect_object_names())
        if prefix not in names:
            return prefix
        index = 1
        while True:
            candidate = f"{prefix}{index}"
            if candidate not in names:
                return candidate
            index += 1
