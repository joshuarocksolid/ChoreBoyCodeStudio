"""Designer editor surface shell widget."""

from __future__ import annotations

from pathlib import Path

from PySide2.QtCore import Qt, Signal
from PySide2.QtGui import QKeySequence
from PySide2.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QShortcut,
    QSplitter,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.designer.canvas import FormCanvas, SelectionController
from app.designer.commands import CommandStack, SnapshotCommand
from app.designer.connections import ConnectionEditorPanel
from app.designer.inspector import ObjectInspector
from app.designer.io import read_ui_file, read_ui_string
from app.designer.io.ui_writer import write_ui_string
from app.designer.layout import apply_layout_to_widget, break_layout
from app.designer.modes import (
    BuddyEditorPanel,
    DESIGNER_MODE_DEFINITIONS,
    MODE_BUDDY,
    MODE_SIGNALS_SLOTS,
    MODE_TAB_ORDER,
    MODE_WIDGET,
    DesignerModeController,
    TabOrderEditorPanel,
)
from app.designer.model import ConnectionModel, PropertyValue, UIModel, WidgetNode
from app.designer.palette.palette_panel import PalettePanel
from app.designer.preview import configure_preview_widget, load_widget_from_ui_xml, probe_ui_xml_compatibility
from app.designer.properties import PropertyEditorController, PropertyEditorPanel
from app.designer.validation import build_validation_issues


class DesignerEditorSurface(QWidget):
    """Host widget for visual `.ui` designer workflows."""

    dirty_state_changed = Signal(bool)
    mode_changed = Signal(str)

    def __init__(self, file_path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._file_path = str(Path(file_path).expanduser().resolve())
        self._model: UIModel | None = None
        self._is_dirty = False
        self._mode_shortcuts: list[QShortcut] = []
        self._pending_connection_source: str | None = None
        self._selection_controller = SelectionController(self)
        self._property_editor = PropertyEditorController()
        self._command_stack = CommandStack(self._apply_snapshot_xml)
        self._mode_controller = DesignerModeController(self)
        self._build_layout()
        self._install_mode_shortcuts()
        self._mode_controller.mode_changed.connect(self._handle_mode_changed)
        self._selection_controller.selection_changed.connect(self._handle_selection_changed)
        self._load_file_into_model()

    @property
    def file_path(self) -> str:
        return self._file_path

    @property
    def model(self) -> UIModel | None:
        return self._model

    @property
    def selected_object_name(self) -> str | None:
        return self._selection_controller.selected_object_name

    @property
    def is_dirty(self) -> bool:
        return self._is_dirty

    @property
    def can_undo(self) -> bool:
        return self._command_stack.can_undo

    @property
    def can_redo(self) -> bool:
        return self._command_stack.can_redo

    @property
    def current_mode(self) -> str:
        return self._mode_controller.current_mode

    def set_mode(self, mode_id: str) -> bool:
        """Set active designer editing mode."""
        return self._mode_controller.set_mode(mode_id)

    def serialize_to_ui_string(self) -> str:
        """Serialize current model into deterministic `.ui` XML."""
        if self._model is None:
            raise ValueError("No model loaded for designer surface.")
        return write_ui_string(self._model)

    def mark_saved(self) -> None:
        """Clear dirty flag after successful save."""
        self._set_dirty(False)

    def undo(self) -> bool:
        """Undo previous designer mutation."""
        if not self._command_stack.undo():
            return False
        self._set_dirty(True)
        return True

    def redo(self) -> bool:
        """Redo previously undone designer mutation."""
        if not self._command_stack.redo():
            return False
        self._set_dirty(True)
        return True

    def preview_current_form(self) -> bool:
        """Preview current form with QUiLoader-generated widget."""
        try:
            ui_xml = self.serialize_to_ui_string()
            preview_widget = load_widget_from_ui_xml(ui_xml)
        except Exception as exc:
            self._error_label.setText(f"Preview failed: {exc}")
            self._error_label.setVisible(True)
            return False
        configure_preview_widget(preview_widget, window_title=f"Preview — {Path(self._file_path).name}")
        preview_widget.show()
        return True

    def run_compatibility_check(self) -> str:
        """Run QUiLoader compatibility check and return status message."""
        try:
            ui_xml = self.serialize_to_ui_string()
        except ValueError as exc:
            return f"Compatibility check failed: {exc}"
        result = probe_ui_xml_compatibility(ui_xml)
        if result.is_compatible:
            return result.message
        return result.message

    def add_resource_include(self, resource_location: str) -> bool:
        """Add `<resources><include .../></resources>` entry to model."""
        normalized = resource_location.strip()
        if not normalized or self._model is None:
            return False
        if any(resource.location == normalized for resource in self._model.resources):
            return False
        before_xml = self.serialize_to_ui_string()
        from app.designer.model import ResourceModel

        self._model.resources.append(ResourceModel(location=normalized))
        self._refresh_validation_issues()
        self._refresh_tab_order_panel()
        self._refresh_buddy_panel()
        self._error_label.setVisible(False)
        after_xml = self.serialize_to_ui_string()
        self._command_stack.push(
            SnapshotCommand(
                description=f"add resource {normalized}",
                before_xml=before_xml,
                after_xml=after_xml,
            )
        )
        self._set_dirty(True)
        return True

    def _build_layout(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._mode_bar = QWidget(self)
        self._mode_bar.setObjectName("designer.surface.modeBar")
        mode_layout = QHBoxLayout(self._mode_bar)
        mode_layout.setContentsMargins(8, 6, 8, 6)
        mode_layout.setSpacing(4)
        self._mode_buttons: dict[str, QToolButton] = {}
        for mode_def in DESIGNER_MODE_DEFINITIONS:
            button = QToolButton(self._mode_bar)
            button.setCheckable(True)
            button.setText(f"{mode_def.display_name} ({mode_def.shortcut})")
            button.clicked.connect(lambda _checked=False, mode_id=mode_def.mode_id: self.set_mode(mode_id))
            self._mode_buttons[mode_def.mode_id] = button
            mode_layout.addWidget(button)
        mode_layout.addStretch(1)
        self._mode_status_label = QLabel("", self._mode_bar)
        mode_layout.addWidget(self._mode_status_label, 0)
        root_layout.addWidget(self._mode_bar, 0)

        self._splitter = QSplitter(self)
        self._splitter.setChildrenCollapsible(False)
        root_layout.addWidget(self._splitter, 1)

        self._palette_panel = PalettePanel(self._splitter)
        self._palette_panel.widget_insert_requested.connect(self._handle_palette_insert_request)
        self._canvas = FormCanvas(self._splitter)
        self._canvas.set_selection_controller(self._selection_controller)
        self._inspector_tabs = QTabWidget(self._splitter)
        self._object_inspector = ObjectInspector(self._inspector_tabs)
        self._object_inspector.set_selection_controller(self._selection_controller)
        self._object_inspector.set_reparent_callback(self._handle_inspector_reparent_request)
        self._object_inspector.reparent_rejected.connect(self._handle_inspector_reparent_rejected)
        self._property_panel = PropertyEditorPanel(self._inspector_tabs)
        self._property_panel.property_edited.connect(self._handle_property_edited)
        self._property_panel.property_reset_requested.connect(self._handle_property_reset_requested)
        self._connection_panel = ConnectionEditorPanel(self._inspector_tabs)
        self._connection_panel.add_requested.connect(self._handle_add_connection_request)
        self._connection_panel.remove_requested.connect(self._handle_remove_connection_request)
        self._connection_panel.connection_edited.connect(self._handle_connection_edited)
        self._tab_order_panel = TabOrderEditorPanel(self._inspector_tabs)
        self._tab_order_panel.tab_order_changed.connect(self._handle_tab_order_changed)
        self._buddy_panel = BuddyEditorPanel(self._inspector_tabs)
        self._buddy_panel.buddy_assignment_changed.connect(self._handle_buddy_assignment_changed)
        self._inspector_tabs.addTab(self._object_inspector, "Object Inspector")
        self._inspector_tabs.addTab(self._property_panel, "Property Editor")
        self._inspector_tabs.addTab(self._connection_panel, "Connections")
        self._inspector_tabs.addTab(self._tab_order_panel, "Tab Order")
        self._inspector_tabs.addTab(self._buddy_panel, "Buddies")
        self._splitter.addWidget(self._palette_panel)
        self._splitter.addWidget(self._canvas)
        self._splitter.addWidget(self._inspector_tabs)
        self._splitter.setSizes([280, 760, 320])

        self._validation_list = QListWidget(self)
        self._validation_list.setObjectName("designer.surface.validationList")
        root_layout.addWidget(self._validation_list, 0)

        self._error_label = QLabel("", self)
        self._error_label.setObjectName("designer.surface.errorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.setVisible(False)
        root_layout.addWidget(self._error_label, 0)
        self._refresh_mode_bar()

    def _load_file_into_model(self) -> None:
        try:
            model = read_ui_file(self._file_path)
        except (OSError, ValueError) as exc:
            self._error_label.setText(f"Failed to load UI file: {exc}")
            self._error_label.setVisible(True)
            return
        self._model = model
        self._canvas.load_model(model)
        self._object_inspector.bind_model(model)
        self._connection_panel.bind_connections(model.connections)
        self._refresh_tab_order_panel()
        self._refresh_buddy_panel()
        self._refresh_validation_issues()
        self._set_dirty(False)

    def _handle_selection_changed(self, object_name: str) -> None:
        if self._model is None or not object_name:
            self._property_panel.bind_widget(None, [])
            self._handle_signals_mode_selection(object_name)
            return
        widget = self._model.root_widget.find_by_object_name(object_name)
        if widget is None:
            self._property_panel.bind_widget(None, [])
            self._handle_signals_mode_selection(object_name)
            return
        self._property_panel.bind_widget(widget, self._property_editor.field_definitions_for_widget(widget))
        self._handle_signals_mode_selection(object_name)

    def _refresh_validation_issues(self) -> None:
        self._validation_list.clear()
        if self._model is None:
            return
        for issue in build_validation_issues(self._model):
            self._validation_list.addItem(f"[{issue.severity}] {issue.code} — {issue.message}")

    def _handle_property_edited(self, object_name: str, property_name: str, value: object) -> None:
        self._apply_property_mutation(
            object_name=object_name,
            property_name=property_name,
            operation="set",
            value=value,
        )

    def _handle_property_reset_requested(self, object_name: str, property_name: str) -> None:
        self._apply_property_mutation(
            object_name=object_name,
            property_name=property_name,
            operation="reset",
            value=None,
        )

    def _apply_property_mutation(
        self,
        object_name: str,
        property_name: str,
        operation: str,
        value: object | None,
    ) -> None:
        if self._model is None:
            return
        widget = self._model.root_widget.find_by_object_name(object_name)
        if widget is None:
            return
        if property_name == "objectName" and operation == "set" and isinstance(value, str):
            duplicate = self._model.root_widget.find_by_object_name(value)
            if duplicate is not None and duplicate is not widget:
                self._error_label.setText("Object name must be unique.")
                self._error_label.setVisible(True)
                self._property_panel.bind_widget(widget, self._property_editor.field_definitions_for_widget(widget))
                return
        before_xml = self.serialize_to_ui_string()
        try:
            if operation == "set":
                self._property_editor.set_property(widget, property_name, value)
            else:
                self._property_editor.reset_property(widget, property_name)
        except (ValueError, TypeError) as exc:
            self._error_label.setText(str(exc))
            self._error_label.setVisible(True)
            self._property_panel.bind_widget(widget, self._property_editor.field_definitions_for_widget(widget))
            return
        self._error_label.setVisible(False)
        self._canvas.load_model(self._model)
        self._object_inspector.bind_model(self._model)
        self._refresh_validation_issues()
        self._refresh_tab_order_panel()
        self._refresh_buddy_panel()
        if property_name == "objectName":
            self._selection_controller.set_selected_object_name(widget.object_name)
        else:
            self._selection_controller.set_selected_object_name(widget.object_name)
        after_xml = self.serialize_to_ui_string()
        if before_xml == after_xml:
            return
        description_prefix = "set" if operation == "set" else "reset"
        self._command_stack.push(
            SnapshotCommand(
                description=f"{description_prefix} {property_name}",
                before_xml=before_xml,
                after_xml=after_xml,
            )
        )
        self._set_dirty(True)

    def _handle_add_connection_request(self) -> None:
        if self._model is None:
            return
        selected_name = self.selected_object_name or self._model.root_widget.object_name
        sender_widget = self._model.root_widget.find_by_object_name(selected_name) or self._model.root_widget
        before_xml = self.serialize_to_ui_string()
        self._append_connection(
            sender_object_name=sender_widget.object_name,
            receiver_object_name=self._model.root_widget.object_name,
        )
        after_xml = self.serialize_to_ui_string()
        if before_xml == after_xml:
            self._error_label.setText("Connection already exists.")
            self._error_label.setVisible(True)
            return
        self._connection_panel.bind_connections(self._model.connections)
        self._refresh_validation_issues()
        self._error_label.setVisible(False)
        self._command_stack.push(
            SnapshotCommand(
                description="add connection",
                before_xml=before_xml,
                after_xml=after_xml,
            )
        )
        self._set_dirty(True)

    def _append_connection(self, sender_object_name: str, receiver_object_name: str) -> None:
        if self._model is None:
            return
        sender_widget = self._model.root_widget.find_by_object_name(sender_object_name)
        signal_name = "customSignal()"
        if sender_widget is not None and sender_widget.class_name in {"QPushButton", "QCheckBox", "QRadioButton"}:
            signal_name = "clicked()"
        candidate = ConnectionModel(
            sender=sender_object_name,
            signal=signal_name,
            receiver=receiver_object_name,
            slot="setFocus()",
        )
        if candidate in self._model.connections:
            return
        self._model.connections.append(candidate)

    def _handle_remove_connection_request(self, index: int) -> None:
        if self._model is None:
            return
        if index < 0 or index >= len(self._model.connections):
            return
        before_xml = self.serialize_to_ui_string()
        self._model.connections.pop(index)
        self._connection_panel.bind_connections(self._model.connections)
        self._refresh_validation_issues()
        self._error_label.setVisible(False)
        self._command_stack.push(
            SnapshotCommand(
                description="remove connection",
                before_xml=before_xml,
                after_xml=self.serialize_to_ui_string(),
            )
        )
        self._set_dirty(True)

    def _handle_connection_edited(self, index: int, field_name: str, value: str) -> None:
        if self._model is None:
            return
        if index < 0 or index >= len(self._model.connections):
            return
        if not value.strip():
            self._error_label.setText("Connection fields cannot be empty.")
            self._error_label.setVisible(True)
            self._connection_panel.bind_connections(self._model.connections)
            return
        from dataclasses import replace

        connection = self._model.connections[index]
        before_xml = self.serialize_to_ui_string()
        updated_connection = replace(connection, **{field_name: value.strip()})
        self._model.connections[index] = updated_connection
        self._connection_panel.bind_connections(self._model.connections)
        self._refresh_validation_issues()
        self._error_label.setVisible(False)
        after_xml = self.serialize_to_ui_string()
        if before_xml == after_xml:
            return
        self._command_stack.push(
            SnapshotCommand(
                description=f"edit connection {field_name}",
                before_xml=before_xml,
                after_xml=after_xml,
            )
        )
        self._set_dirty(True)

    def _handle_tab_order_changed(self, ordered_object_names: list[str]) -> None:
        if self._model is None:
            return
        candidates = self._default_tab_order_candidates()
        filtered: list[str] = [name for name in ordered_object_names if name in candidates]
        for candidate in candidates:
            if candidate not in filtered:
                filtered.append(candidate)
        before_xml = self.serialize_to_ui_string()
        self._model.tab_stops = filtered
        self._refresh_tab_order_panel()
        self._error_label.setVisible(False)
        after_xml = self.serialize_to_ui_string()
        if before_xml == after_xml:
            return
        self._command_stack.push(
            SnapshotCommand(
                description="edit tab order",
                before_xml=before_xml,
                after_xml=after_xml,
            )
        )
        self._set_dirty(True)

    def _handle_buddy_assignment_changed(self, label_object_name: str, buddy_object_name: str) -> None:
        if self._model is None:
            return
        label_widget = self._model.root_widget.find_by_object_name(label_object_name)
        if label_widget is None or label_widget.class_name != "QLabel":
            return
        before_xml = self.serialize_to_ui_string()
        if buddy_object_name:
            label_widget.properties["buddy"] = PropertyValue(value_type="cstring", value=buddy_object_name)
        else:
            label_widget.properties.pop("buddy", None)
        self._refresh_buddy_panel()
        self._refresh_validation_issues()
        self._error_label.setVisible(False)
        after_xml = self.serialize_to_ui_string()
        if before_xml == after_xml:
            return
        self._command_stack.push(
            SnapshotCommand(
                description=f"set buddy {label_object_name}",
                before_xml=before_xml,
                after_xml=after_xml,
            )
        )
        self._set_dirty(True)

    def _handle_palette_insert_request(self, class_name: str) -> None:
        if self._model is None:
            return
        before_xml = self.serialize_to_ui_string()
        if not self._canvas.insert_widget_by_class_name(class_name):
            self._error_label.setText("Widget insertion is not allowed for the selected parent.")
            self._error_label.setVisible(True)
            return
        self._error_label.setVisible(False)
        self._object_inspector.bind_model(self._model)
        self._refresh_validation_issues()
        self._refresh_tab_order_panel()
        self._refresh_buddy_panel()
        after_xml = self.serialize_to_ui_string()
        self._command_stack.push(
            SnapshotCommand(
                description=f"insert {class_name}",
                before_xml=before_xml,
                after_xml=after_xml,
            )
        )
        self._set_dirty(True)

    def _handle_inspector_reparent_request(self, source_object_name: str, target_object_name: str) -> bool:
        if self._model is None:
            return False
        before_xml = self.serialize_to_ui_string()
        if not self._object_inspector.reparent_widget(source_object_name, target_object_name):
            self._handle_inspector_reparent_rejected(self._object_inspector.last_reparent_error)
            return False
        self._canvas.load_model(self._model)
        self._refresh_validation_issues()
        self._refresh_tab_order_panel()
        self._refresh_buddy_panel()
        self._error_label.setVisible(False)
        after_xml = self.serialize_to_ui_string()
        if before_xml == after_xml:
            return True
        self._command_stack.push(
            SnapshotCommand(
                description=f"reparent {source_object_name} -> {target_object_name}",
                before_xml=before_xml,
                after_xml=after_xml,
            )
        )
        self._set_dirty(True)
        return True

    def _handle_inspector_reparent_rejected(self, message: str) -> None:
        if not message:
            return
        self._error_label.setText(message)
        self._error_label.setVisible(True)

    def apply_layout_to_selection(self, layout_class_name: str) -> bool:
        """Apply layout to selected widget (or root when none selected)."""
        if self._model is None:
            return False
        target = self._resolve_selected_widget()
        if target is None:
            return False
        layout_name_map = {
            "QVBoxLayout": "verticalLayout",
            "QHBoxLayout": "horizontalLayout",
            "QGridLayout": "gridLayout",
        }
        layout_object_name = layout_name_map.get(layout_class_name, "layout")
        before_xml = self.serialize_to_ui_string()
        try:
            apply_layout_to_widget(target, layout_class_name, layout_object_name=layout_object_name)
        except ValueError as exc:
            self._error_label.setText(str(exc))
            self._error_label.setVisible(True)
            return False
        self._error_label.setVisible(False)
        self._canvas.load_model(self._model)
        self._object_inspector.bind_model(self._model)
        self._refresh_validation_issues()
        self._refresh_tab_order_panel()
        self._refresh_buddy_panel()
        self._command_stack.push(
            SnapshotCommand(
                description=f"layout {layout_class_name}",
                before_xml=before_xml,
                after_xml=self.serialize_to_ui_string(),
            )
        )
        self._set_dirty(True)
        return True

    def break_layout_for_selection(self) -> bool:
        """Break layout for selected widget (or root when none selected)."""
        if self._model is None:
            return False
        target = self._resolve_selected_widget()
        if target is None:
            return False
        if target.layout is None:
            return False
        before_xml = self.serialize_to_ui_string()
        break_layout(target)
        self._canvas.load_model(self._model)
        self._object_inspector.bind_model(self._model)
        self._refresh_validation_issues()
        self._refresh_tab_order_panel()
        self._refresh_buddy_panel()
        self._error_label.setVisible(False)
        self._command_stack.push(
            SnapshotCommand(
                description="break layout",
                before_xml=before_xml,
                after_xml=self.serialize_to_ui_string(),
            )
        )
        self._set_dirty(True)
        return True

    def _resolve_selected_widget(self) -> WidgetNode | None:
        if self._model is None:
            return None
        selected_name = self._selection_controller.selected_object_name
        if not selected_name:
            return self._model.root_widget
        return self._model.root_widget.find_by_object_name(selected_name)

    def _set_dirty(self, is_dirty: bool) -> None:
        if self._is_dirty == is_dirty:
            return
        self._is_dirty = is_dirty
        self.dirty_state_changed.emit(is_dirty)

    def _apply_snapshot_xml(self, snapshot_xml: str) -> None:
        model = read_ui_string(snapshot_xml)
        self._model = model
        self._canvas.load_model(model)
        self._object_inspector.bind_model(model)
        self._connection_panel.bind_connections(model.connections)
        self._refresh_tab_order_panel()
        self._refresh_buddy_panel()
        self._refresh_validation_issues()

    def _install_mode_shortcuts(self) -> None:
        shortcut_map = {
            MODE_WIDGET: "F3",
            MODE_SIGNALS_SLOTS: "F4",
            MODE_BUDDY: "F5",
            MODE_TAB_ORDER: "F6",
        }
        for mode_id, shortcut_text in shortcut_map.items():
            shortcut = QShortcut(QKeySequence(shortcut_text), self)
            shortcut.setContext(Qt.WidgetWithChildrenShortcut)
            shortcut.activated.connect(lambda mode=mode_id: self.set_mode(mode))
            self._mode_shortcuts.append(shortcut)

    def _handle_mode_changed(self, mode_id: str) -> None:
        self._pending_connection_source = None
        if mode_id == MODE_SIGNALS_SLOTS:
            self._inspector_tabs.setCurrentWidget(self._connection_panel)
        if mode_id == MODE_TAB_ORDER:
            self._inspector_tabs.setCurrentWidget(self._tab_order_panel)
        if mode_id == MODE_BUDDY:
            self._inspector_tabs.setCurrentWidget(self._buddy_panel)
        self._refresh_mode_bar()
        self.mode_changed.emit(mode_id)

    def _handle_signals_mode_selection(self, object_name: str) -> None:
        if self._mode_controller.current_mode != MODE_SIGNALS_SLOTS:
            return
        if self._model is None or not object_name:
            return
        if self._pending_connection_source is None:
            self._pending_connection_source = object_name
            self._error_label.setText(f"Signals mode: source selected ({object_name}). Select a target widget.")
            self._error_label.setVisible(True)
            return
        if self._pending_connection_source == object_name:
            return
        before_xml = self.serialize_to_ui_string()
        self._append_connection(
            sender_object_name=self._pending_connection_source,
            receiver_object_name=object_name,
        )
        after_xml = self.serialize_to_ui_string()
        self._pending_connection_source = None
        self._connection_panel.bind_connections(self._model.connections)
        self._refresh_validation_issues()
        if before_xml == after_xml:
            self._error_label.setText("Signals mode: identical connection already exists.")
            self._error_label.setVisible(True)
            return
        self._error_label.setText("Signals mode: connection created.")
        self._error_label.setVisible(True)
        self._command_stack.push(
            SnapshotCommand(
                description="connect widgets",
                before_xml=before_xml,
                after_xml=after_xml,
            )
        )
        self._set_dirty(True)

    def _refresh_tab_order_panel(self) -> None:
        if self._model is None:
            self._tab_order_panel.bind_tab_order([])
            return
        candidates = self._default_tab_order_candidates()
        ordered: list[str] = [name for name in self._model.tab_stops if name in candidates]
        for candidate in candidates:
            if candidate not in ordered:
                ordered.append(candidate)
        self._tab_order_panel.bind_tab_order(ordered)

    def _default_tab_order_candidates(self) -> list[str]:
        if self._model is None:
            return []
        candidates: list[str] = []
        seen: set[str] = set()
        for object_name in self._model.collect_object_names():
            if object_name == self._model.root_widget.object_name:
                continue
            widget = self._model.root_widget.find_by_object_name(object_name)
            if widget is None:
                continue
            if widget.class_name in {"QLabel"}:
                continue
            if object_name in seen:
                continue
            seen.add(object_name)
            candidates.append(object_name)
        return candidates

    def _refresh_buddy_panel(self) -> None:
        if self._model is None:
            self._buddy_panel.bind_buddy_rows([], [])
            return
        candidates = self._buddy_candidates()
        rows: list[tuple[str, str]] = []
        for object_name in self._model.collect_object_names():
            widget = self._model.root_widget.find_by_object_name(object_name)
            if widget is None or widget.class_name != "QLabel":
                continue
            buddy_property = widget.properties.get("buddy")
            current_buddy = ""
            if isinstance(buddy_property, PropertyValue):
                current_buddy = str(buddy_property.value)
            rows.append((widget.object_name, current_buddy))
        self._buddy_panel.bind_buddy_rows(rows, candidates)

    def _buddy_candidates(self) -> list[str]:
        if self._model is None:
            return []
        candidates: list[str] = []
        seen: set[str] = set()
        for object_name in self._model.collect_object_names():
            if object_name == self._model.root_widget.object_name:
                continue
            widget = self._model.root_widget.find_by_object_name(object_name)
            if widget is None:
                continue
            if widget.class_name == "QLabel":
                continue
            if object_name in seen:
                continue
            seen.add(object_name)
            candidates.append(object_name)
        return candidates

    def _refresh_mode_bar(self) -> None:
        current_mode = self._mode_controller.current_mode
        for mode_id, button in self._mode_buttons.items():
            button.setChecked(mode_id == current_mode)
        mode_names = {
            MODE_WIDGET: "Widget Editing Mode",
            MODE_SIGNALS_SLOTS: "Signals/Slots Mode",
            MODE_BUDDY: "Buddy Mode",
            MODE_TAB_ORDER: "Tab Order Mode",
        }
        self._mode_status_label.setText(mode_names.get(current_mode, "Mode"))

