"""Component export/import helpers for designer widget subtrees."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path

from app.core import constants
from app.designer.canvas.drop_rules import can_insert_widget
from app.designer.io import read_ui_file, write_ui_file
from app.designer.model import UIModel, WidgetNode

_COMPONENTS_DIRNAME = "components"


@dataclass(frozen=True)
class ComponentDescriptor:
    """Descriptor for one saved designer component."""

    name: str
    file_path: str
    root_class_name: str
    root_object_name: str


def _components_dir_for_ui_file(ui_file_path: str) -> Path:
    ui_file = Path(ui_file_path).resolve()
    return ui_file.parent / constants.PROJECT_META_DIRNAME / _COMPONENTS_DIRNAME


def save_component_from_widget(ui_file_path: str, component_name: str, widget: WidgetNode) -> ComponentDescriptor:
    """Persist selected widget subtree as reusable `.ui` component file."""
    normalized_name = component_name.strip()
    if not normalized_name:
        raise ValueError("Component name cannot be empty.")
    components_dir = _components_dir_for_ui_file(ui_file_path)
    components_dir.mkdir(parents=True, exist_ok=True)
    output_file = components_dir / f"{normalized_name}.ui"
    model = UIModel(
        form_class_name=normalized_name,
        root_widget=copy.deepcopy(widget),
    )
    write_ui_file(model, str(output_file))
    return ComponentDescriptor(
        name=normalized_name,
        file_path=str(output_file),
        root_class_name=model.root_widget.class_name,
        root_object_name=model.root_widget.object_name,
    )


def list_components(ui_file_path: str) -> list[ComponentDescriptor]:
    """List saved reusable components for current project."""
    components_dir = _components_dir_for_ui_file(ui_file_path)
    if not components_dir.is_dir():
        return []
    descriptors: list[ComponentDescriptor] = []
    for file_path in sorted(components_dir.glob("*.ui")):
        try:
            model = read_ui_file(str(file_path))
        except Exception:
            continue
        descriptors.append(
            ComponentDescriptor(
                name=file_path.stem,
                file_path=str(file_path),
                root_class_name=model.root_widget.class_name,
                root_object_name=model.root_widget.object_name,
            )
        )
    return descriptors


def insert_component_widget(
    *,
    ui_file_path: str,
    component_name: str,
    target_parent: WidgetNode,
    existing_object_names: list[str] | None = None,
) -> WidgetNode:
    """Load component subtree and insert under target parent when valid."""
    descriptor_map = {component.name: component for component in list_components(ui_file_path)}
    descriptor = descriptor_map.get(component_name)
    if descriptor is None:
        raise ValueError(f"Component not found: {component_name}")
    model = read_ui_file(descriptor.file_path)
    widget = copy.deepcopy(model.root_widget)
    if not can_insert_widget(
        parent_class_name=target_parent.class_name,
        child_class_name=widget.class_name,
        is_layout_item=False,
        parent_has_layout=target_parent.layout is not None,
    ):
        raise ValueError("Selected target cannot accept this component.")
    names_in_use = set(existing_object_names or [])
    _ensure_unique_object_names(widget, names_in_use)
    if target_parent.layout is not None:
        from app.designer.model import LayoutItem

        target_parent.layout.items.append(LayoutItem(widget=widget))
    else:
        target_parent.children.append(widget)
    return widget


def _ensure_unique_object_names(widget: WidgetNode, names_in_use: set[str]) -> None:
    original_name = widget.object_name
    if original_name in names_in_use:
        widget.object_name = _next_available_name(original_name, names_in_use)
    names_in_use.add(widget.object_name)
    for child in widget.children:
        _ensure_unique_object_names(child, names_in_use)
    if widget.layout is not None:
        for item in widget.layout.items:
            if item.widget is not None:
                _ensure_unique_object_names(item.widget, names_in_use)


def _next_available_name(base_name: str, names_in_use: set[str]) -> str:
    index = 1
    while True:
        candidate = f"{base_name}{index}"
        if candidate not in names_in_use:
            return candidate
        index += 1
