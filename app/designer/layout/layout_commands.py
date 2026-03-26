"""Model-level layout command helpers for designer forms."""

from __future__ import annotations

from app.designer.model import LayoutItem, LayoutNode, WidgetNode

_SUPPORTED_LAYOUT_CLASSES = {"QVBoxLayout", "QHBoxLayout", "QGridLayout"}


def apply_layout_to_widget(widget: WidgetNode, layout_class_name: str, *, layout_object_name: str) -> None:
    """Apply a layout to widget and move direct children into layout items."""
    if layout_class_name not in _SUPPORTED_LAYOUT_CLASSES:
        raise ValueError(f"Unsupported layout class: {layout_class_name}")
    if widget.layout is not None:
        raise ValueError(f"Widget already has layout: {widget.object_name}")

    items = [LayoutItem(widget=child) for child in widget.children]
    widget.children = []
    widget.layout = LayoutNode(
        class_name=layout_class_name,
        object_name=layout_object_name,
        items=items,
    )


def break_layout(widget: WidgetNode) -> None:
    """Remove layout from widget and move contained widgets back to children."""
    if widget.layout is None:
        return
    restored_children: list[WidgetNode] = []
    for item in widget.layout.items:
        if item.widget is not None:
            restored_children.append(item.widget)
    widget.children.extend(restored_children)
    widget.layout = None


def align_widgets(widgets: list[WidgetNode], mode: str) -> bool:
    """Align freeform widgets by geometry."""
    if len(widgets) < 2:
        return False
    geometries = [_geometry_for_widget(widget) for widget in widgets]
    if any(geometry is None for geometry in geometries):
        return False
    reference = geometries[0]
    assert reference is not None
    ref_left = int(reference.get("x", 0))
    ref_top = int(reference.get("y", 0))
    ref_width = int(reference.get("width", 0))
    ref_height = int(reference.get("height", 0))
    ref_right = ref_left + ref_width
    ref_bottom = ref_top + ref_height
    ref_center_x = ref_left + int(ref_width / 2)
    ref_center_y = ref_top + int(ref_height / 2)

    changed = False
    for geometry in geometries[1:]:
        assert geometry is not None
        width = int(geometry.get("width", 0))
        height = int(geometry.get("height", 0))
        if mode == "left":
            changed |= _set_geometry_field(geometry, "x", ref_left)
        elif mode == "right":
            changed |= _set_geometry_field(geometry, "x", ref_right - width)
        elif mode == "top":
            changed |= _set_geometry_field(geometry, "y", ref_top)
        elif mode == "bottom":
            changed |= _set_geometry_field(geometry, "y", ref_bottom - height)
        elif mode == "center_horizontal":
            changed |= _set_geometry_field(geometry, "x", ref_center_x - int(width / 2))
        elif mode == "center_vertical":
            changed |= _set_geometry_field(geometry, "y", ref_center_y - int(height / 2))
        else:
            return False
    return changed


def distribute_widgets(widgets: list[WidgetNode], axis: str) -> bool:
    """Distribute widgets evenly along one axis."""
    if len(widgets) < 3:
        return False
    geometries = [_geometry_for_widget(widget) for widget in widgets]
    if any(geometry is None for geometry in geometries):
        return False
    valid_geometries = [geometry for geometry in geometries if geometry is not None]
    key = "x" if axis == "horizontal" else "y" if axis == "vertical" else ""
    if not key:
        return False

    sorted_geometries = sorted(valid_geometries, key=lambda geometry: int(geometry.get(key, 0)))
    start = int(sorted_geometries[0].get(key, 0))
    end = int(sorted_geometries[-1].get(key, 0))
    step = (end - start) / float(len(sorted_geometries) - 1)
    changed = False
    for index, geometry in enumerate(sorted_geometries[1:-1], start=1):
        target = int(round(start + (step * index)))
        changed |= _set_geometry_field(geometry, key, target)
    return changed


def adjust_widgets_to_default_size(widgets: list[WidgetNode]) -> bool:
    """Adjust selected widget geometries to class default size."""
    if not widgets:
        return False
    changed = False
    for widget in widgets:
        geometry = _geometry_for_widget(widget)
        if geometry is None:
            continue
        default_width, default_height = _default_size_for_class(widget.class_name)
        changed |= _set_geometry_field(geometry, "width", default_width)
        changed |= _set_geometry_field(geometry, "height", default_height)
    return changed


def _geometry_for_widget(widget: WidgetNode) -> dict[str, int] | None:
    geometry_property = widget.properties.get("geometry")
    if geometry_property is None or geometry_property.value_type != "rect":
        return None
    value = geometry_property.value
    if not isinstance(value, dict):
        return None
    return value


def _set_geometry_field(geometry: dict[str, int], key: str, value: int) -> bool:
    current = int(geometry.get(key, 0))
    if current == int(value):
        return False
    geometry[key] = int(value)
    return True


def _default_size_for_class(class_name: str) -> tuple[int, int]:
    if class_name in {
        "QWidget",
        "QFrame",
        "QGroupBox",
        "QTabWidget",
        "QScrollArea",
        "QStackedWidget",
        "QSplitter",
        "QMainWindow",
    }:
        return (220, 140)
    if class_name == "QTableWidget":
        return (180, 110)
    return (120, 32)
