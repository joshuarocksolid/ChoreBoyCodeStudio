"""Class-aware signals/slots connection editing panel."""

from __future__ import annotations

from collections.abc import Sequence

from PySide2.QtCore import Qt, Signal
from PySide2.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from app.designer.connections.signal_slot_metadata import (
    ConnectionObjectOption,
    has_class_specific_signal_catalog,
    has_class_specific_slot_catalog,
    is_signal_slot_pair_compatible,
    signal_choices_for_class,
    slot_choices_for_class,
)
from app.designer.model import ConnectionModel


class ConnectionEditorPanel(QWidget):
    """List connections with class-aware signal/slot pickers."""

    add_requested = Signal()
    remove_requested = Signal(int)
    connection_edited = Signal(int, str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("designer.connections.panel")
        self._connections: list[ConnectionModel] = []
        self._object_options: list[ConnectionObjectOption] = []
        self._object_class_by_name: dict[str, str] = {}
        self._is_populating = False
        self._summary_label = QLabel("No signal/slot connections.", self)
        self._summary_label.setObjectName("designer.connections.summary")
        self._validation_label = QLabel("", self)
        self._validation_label.setObjectName("designer.connections.validation")
        self._validation_label.setWordWrap(True)
        self._validation_label.setVisible(False)
        self._table = QTableWidget(0, 4, self)
        self._table.setObjectName("designer.connections.table")
        self._table.setHorizontalHeaderLabels(["Sender", "Signal", "Receiver", "Slot"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.SingleSelection)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)

        self._add_button = QPushButton("Add Default Connection", self)
        self._add_button.setObjectName("designer.connections.btn.add")
        self._add_button.clicked.connect(self.add_requested.emit)
        self._remove_button = QPushButton("Remove Selected", self)
        self._remove_button.setObjectName("designer.connections.btn.remove")
        self._remove_button.clicked.connect(self._emit_remove_selected)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(6)
        button_row.addWidget(self._add_button, 0)
        button_row.addWidget(self._remove_button, 0)
        button_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(self._summary_label, 0)
        layout.addWidget(self._validation_label, 0)
        layout.addWidget(self._table, 1)
        layout.addLayout(button_row, 0)
        self._refresh_summary()

    def bind_connection_context(self, object_options: Sequence[ConnectionObjectOption]) -> None:
        """Bind sender/receiver options with known object/class metadata."""
        self._object_options = list(object_options)
        self._object_class_by_name = {option.object_name: option.class_name for option in self._object_options}

    def bind_connections(self, connections: list[ConnectionModel]) -> None:
        self._is_populating = True
        self._connections = list(connections)
        self._table.setRowCount(len(self._connections))
        for row, connection in enumerate(self._connections):
            self._bind_connection_row(row, connection)
        self._is_populating = False
        self._refresh_validation_summary()
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        count = len(self._connections)
        if count == 0:
            self._summary_label.setText("No signal/slot connections.")
            self._remove_button.setEnabled(False)
            return
        self._summary_label.setText(f"{count} connection(s)")
        self._remove_button.setEnabled(True)

    def _emit_remove_selected(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._connections):
            return
        self.remove_requested.emit(row)

    def _bind_connection_row(self, row: int, connection: ConnectionModel) -> None:
        sender_combo = self._build_object_combo(connection.sender)
        receiver_combo = self._build_object_combo(connection.receiver)
        signal_combo = self._build_signature_combo(
            signal_choices_for_class(self._class_for_object(connection.sender)),
            connection.signal,
        )
        slot_combo = self._build_signature_combo(
            self._compatible_slot_choices(
                receiver_object_name=connection.receiver,
                signal_signature=connection.signal,
            ),
            connection.slot,
        )

        sender_combo.currentIndexChanged.connect(
            lambda _index, row_index=row, sender_widget=sender_combo, signal_widget=signal_combo: self
            ._handle_sender_changed(row_index, sender_widget, signal_widget)
        )
        signal_combo.currentIndexChanged.connect(
            lambda _index, row_index=row, signal_widget=signal_combo, receiver_widget=receiver_combo, slot_widget=slot_combo: self
            ._handle_signal_changed(row_index, signal_widget, receiver_widget, slot_widget)
        )
        receiver_combo.currentIndexChanged.connect(
            lambda _index, row_index=row, receiver_widget=receiver_combo, signal_widget=signal_combo, slot_widget=slot_combo: self
            ._handle_receiver_changed(row_index, receiver_widget, signal_widget, slot_widget)
        )
        slot_combo.currentIndexChanged.connect(
            lambda _index, row_index=row, slot_widget=slot_combo: self._emit_combo_edit(
                row_index, "slot", slot_widget
            )
        )

        self._table.setCellWidget(row, 0, sender_combo)
        self._table.setCellWidget(row, 1, signal_combo)
        self._table.setCellWidget(row, 2, receiver_combo)
        self._table.setCellWidget(row, 3, slot_combo)

    def _build_object_combo(self, current_object_name: str) -> QComboBox:
        combo = QComboBox(self._table)
        combo.setObjectName("designer.connections.combo.object")
        for option in self._object_options:
            label = f"{option.object_name} ({option.class_name})"
            combo.addItem(label, option.object_name)
        if combo.findData(current_object_name) < 0 and current_object_name:
            fallback_class_name = self._class_for_object(current_object_name)
            combo.addItem(f"{current_object_name} ({fallback_class_name})", current_object_name)
        current_index = combo.findData(current_object_name)
        combo.setCurrentIndex(current_index if current_index >= 0 else 0)
        return combo

    def _build_signature_combo(self, options: Sequence[str], current_value: str) -> QComboBox:
        combo = QComboBox(self._table)
        combo.setObjectName("designer.connections.combo.signature")
        for option in options:
            combo.addItem(option, option)
        if current_value and combo.findData(current_value) < 0:
            combo.addItem(f"{current_value} (legacy)", current_value)
        current_index = combo.findData(current_value)
        combo.setCurrentIndex(current_index if current_index >= 0 else 0)
        return combo

    def _handle_sender_changed(self, row: int, sender_combo: QComboBox, signal_combo: QComboBox) -> None:
        sender_object_name = self._combo_value(sender_combo)
        signal_signature = self._combo_value(signal_combo)
        signal_choices = signal_choices_for_class(self._class_for_object(sender_object_name))
        self._replace_signature_options(
            signal_combo,
            signal_choices,
            signal_signature,
            allow_legacy_preferred=False,
        )
        self._emit_combo_edit(row, "sender", sender_combo)
        self._emit_combo_edit(row, "signal", signal_combo)

    def _handle_signal_changed(
        self,
        row: int,
        signal_combo: QComboBox,
        receiver_combo: QComboBox,
        slot_combo: QComboBox,
    ) -> None:
        signal_signature = self._combo_value(signal_combo)
        receiver_object_name = self._combo_value(receiver_combo)
        slot_signature = self._combo_value(slot_combo)
        slot_choices = self._compatible_slot_choices(receiver_object_name, signal_signature)
        self._replace_signature_options(
            slot_combo,
            slot_choices,
            slot_signature,
            allow_legacy_preferred=False,
        )
        self._emit_combo_edit(row, "signal", signal_combo)
        self._emit_combo_edit(row, "slot", slot_combo)

    def _handle_receiver_changed(
        self,
        row: int,
        receiver_combo: QComboBox,
        signal_combo: QComboBox,
        slot_combo: QComboBox,
    ) -> None:
        receiver_object_name = self._combo_value(receiver_combo)
        signal_signature = self._combo_value(signal_combo)
        slot_signature = self._combo_value(slot_combo)
        slot_choices = self._compatible_slot_choices(receiver_object_name, signal_signature)
        self._replace_signature_options(
            slot_combo,
            slot_choices,
            slot_signature,
            allow_legacy_preferred=False,
        )
        self._emit_combo_edit(row, "receiver", receiver_combo)
        self._emit_combo_edit(row, "slot", slot_combo)

    def _replace_signature_options(
        self,
        combo: QComboBox,
        options: Sequence[str],
        preferred_value: str,
        *,
        allow_legacy_preferred: bool = True,
    ) -> None:
        combo.blockSignals(True)
        combo.clear()
        for option in options:
            combo.addItem(option, option)
        if allow_legacy_preferred and preferred_value and combo.findData(preferred_value) < 0:
            combo.addItem(f"{preferred_value} (legacy)", preferred_value)
        preferred_index = combo.findData(preferred_value)
        combo.setCurrentIndex(preferred_index if preferred_index >= 0 else 0)
        combo.blockSignals(False)

    def _compatible_slot_choices(self, receiver_object_name: str, signal_signature: str) -> tuple[str, ...]:
        class_name = self._class_for_object(receiver_object_name)
        candidate_slots = slot_choices_for_class(class_name)
        compatible = tuple(
            slot_signature
            for slot_signature in candidate_slots
            if is_signal_slot_pair_compatible(signal_signature, slot_signature)
        )
        if compatible:
            return compatible
        return candidate_slots

    def _emit_combo_edit(self, row: int, field_name: str, combo: QComboBox) -> None:
        if self._is_populating:
            return
        if row < 0 or row >= len(self._connections):
            return
        value = self._combo_value(combo)
        if not value:
            return
        self.connection_edited.emit(row, field_name, value)

    def _refresh_validation_summary(self) -> None:
        warnings: list[str] = []
        for connection in self._connections:
            sender_class = self._class_for_object(connection.sender)
            receiver_class = self._class_for_object(connection.receiver)
            if not has_class_specific_signal_catalog(sender_class):
                warnings.append(
                    f"Sender '{connection.sender}' ({sender_class}) has no class-aware signal catalog."
                )
            if not has_class_specific_slot_catalog(receiver_class):
                warnings.append(
                    f"Receiver '{connection.receiver}' ({receiver_class}) has no class-aware slot catalog."
                )
            if not is_signal_slot_pair_compatible(connection.signal, connection.slot):
                warnings.append(
                    f"Potential mismatch: {connection.signal} -> {connection.slot} for "
                    f"{connection.sender} -> {connection.receiver}."
                )
        if not warnings:
            self._validation_label.setVisible(False)
            return
        self._validation_label.setText("Connection warnings: " + " ".join(warnings))
        self._validation_label.setVisible(True)

    def _class_for_object(self, object_name: str) -> str:
        return self._object_class_by_name.get(object_name, "QWidget")

    def _combo_value(self, combo: QComboBox) -> str:
        return str(combo.currentData() or "")
