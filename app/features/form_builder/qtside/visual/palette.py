"""Palette popover (UX-PED-085). The brush editor opens in place; Esc goes back first."""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from app.features.form_builder.engine.ui4.values import (
    BrushValue,
    ColorRole,
    ColorValue,
    PaletteValue,
)
from app.features.form_builder.qtside.inspector.api import (
    EditorHost,
    EditorKey,
    Mixed,
    Registrar,
    RowValue,
    ValueSpec,
    Written,
)
from app.features.form_builder.qtside.inspector.editors._popover import RowPopover
from app.features.form_builder.qtside.visual.brush import BrushForm
from app.features.form_builder.qtside.visual.color_picker import ColorPicker, Swatch
from app.features.form_builder.qtside.visual.common import (
    RowSummary,
    begin_popover,
    owner_name,
    part_name,
    refit_widget,
)
from app.qt.QtCore import QEvent, QObject, Qt
from app.qt.QtGui import QColor, QFont, QPalette
from app.qt.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

_ROLES = (
    ("Window", "Window"),
    ("Window text", "WindowText"),
    ("Base (field background)", "Base"),
    ("Alternate base", "AlternateBase"),
    ("Text", "Text"),
    ("Placeholder text", "PlaceholderText"),
    ("Button", "Button"),
    ("Button text", "ButtonText"),
    ("Bright text", "BrightText"),
    ("Highlight", "Highlight"),
    ("Highlighted text", "HighlightedText"),
    ("Link", "Link"),
    ("Visited link", "LinkVisited"),
    ("Tooltip background", "ToolTipBase"),
    ("Tooltip text", "ToolTipText"),
    ("Light", "Light"),
    ("Midlight", "Midlight"),
    ("Mid", "Mid"),
    ("Dark", "Dark"),
    ("Shadow", "Shadow"),
)
_GROUPS = ("active", "inactive", "disabled")
_GROUP_ENUM = {"active": "Active", "inactive": "Inactive", "disabled": "Disabled"}
_STATE_LABELS = (("active", "Active"), ("inactive", "Inactive"), ("disabled", "Disabled"))


def _key(name: str) -> object:
    return getattr(getattr(Qt, "Key", Qt), name)


def _event(name: str) -> object:
    return getattr(getattr(QEvent, "Type", QEvent), name)


def _focus(name: str) -> object:
    return getattr(getattr(Qt, "FocusPolicy", Qt), name)


def _role_enum(name: str) -> object:
    return getattr(getattr(QPalette, "ColorRole", QPalette), name)


def _group_enum(name: str) -> object:
    return getattr(getattr(QPalette, "ColorGroup", QPalette), name)


def palette_summary(palette: Optional[PaletteValue], *, mixed: bool) -> str:
    if mixed:
        return "Mixed"
    count = 0 if palette is None else _changed_count(palette)
    if count == 0:
        return "Default"
    if count == 1:
        return "1 colour changed"
    return "%d colours changed" % count


def _changed_count(palette: PaletteValue) -> int:
    found = set()
    for group in _GROUPS:
        for role in getattr(palette, group):
            found.add(role.role)
    return len(found)


def _solid(color: ColorValue) -> BrushValue:
    return BrushValue(brushstyle="SolidPattern", color=color)


def palette_from_button(color: ColorValue) -> PaletteValue:
    """The roles Qt derives from one button colour, written in every state group."""
    button = QColor(color.red, color.green, color.blue, 255 if color.alpha is None else color.alpha)
    try:
        built = QPalette(button)
    except TypeError:
        built = QPalette()
        built.setColor(_role_enum("Button"), button)  # type: ignore[arg-type]
    groups = {}
    for group in _GROUPS:
        roles = []
        for _label, role in _ROLES:
            qcolor = built.color(_group_enum(_GROUP_ENUM[group]), _role_enum(role))  # type: ignore[arg-type]
            alpha = qcolor.alpha()
            roles.append(ColorRole(role, _solid(ColorValue(
                qcolor.red(), qcolor.green(), qcolor.blue(), None if alpha >= 255 else alpha
            ))))
        groups[group] = tuple(roles)
    return PaletteValue(active=groups["active"], inactive=groups["inactive"], disabled=groups["disabled"])


class _RoleList(QListWidget):
    def __init__(self, parent: QWidget, on_open: object) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.paletteRoles")
        self.setAccessibleName(part_name("Palette", "roles"))
        self._on_open = on_open
        self.setProperty("fbEnterStays", True)

    def keyPressEvent(self, event: object) -> None:  # noqa: N802
        if event.key() in (_key("Key_Return"), _key("Key_Enter")):  # type: ignore[attr-defined]
            self._on_open("all" if not self.property("perState") else "active")
            event.accept()  # type: ignore[attr-defined]
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]


class _EscFilter(QObject):
    """First Esc leaves the in-place brush editor. The popover sees the next one."""

    def __init__(self, editor: "PaletteEditor") -> None:
        super().__init__(editor._root)
        self._editor = editor

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        popover = self._editor._popover
        if popover is None or popover.closed:
            app = QApplication.instance()
            if app is not None:
                app.removeEventFilter(self)
            return False
        if event.type() != _event("KeyPress"):
            return False
        if event.key() != _key("Key_Escape"):  # type: ignore[attr-defined]
            return False
        if self._editor.consume_escape():
            return True
        return False


class PaletteEditor:
    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        del spec
        self._host = host
        self._root = QWidget(parent)
        layout = QHBoxLayout(self._root)
        layout.setContentsMargins(0, 0, 0, 0)
        self._summary = RowSummary(host.label or "Palette", self._root)
        self._summary.set_opener(self._open)
        layout.addWidget(self._summary, 1)
        self._palette = PaletteValue()
        self._written = False
        self._per_state = False
        self._popover: Optional[RowPopover] = None
        self._page = "list"
        self._brush_role = ""
        self._brush_group = "all"
        self._filter: Optional[_EscFilter] = None
        self._roles: Dict[str, Dict[str, BrushValue]] = {}
        self._confirming = False

    @property
    def widget(self) -> QWidget:
        return self._root

    def show(self, value: RowValue) -> None:
        mixed = isinstance(value, Mixed)
        self._written = isinstance(value, Written) and isinstance(value.value, PaletteValue)
        self._palette = value.value if self._written else PaletteValue()  # type: ignore[assignment]
        self._roles = _index(self._palette)
        if self._popover is None or self._popover.closed:
            # While the popover is open the person's "Show each state" choice
            # stands; a live re-show must not fold their state edit into all.
            self._per_state = _differs(self._roles)
        text = palette_summary(self._palette if self._written else None, mixed=mixed)
        self._summary.set_summary(text)
        self._summary.show_state(value, self._host.chrome.faint)

    def consume_escape(self) -> bool:
        if self._confirming:
            self._confirming = False
            self._show_list()
            return True
        if self._page != "list":
            self._show_list()
            return True
        return False

    def _open(self) -> None:
        if self._popover is not None and not self._popover.closed:
            return
        popover = begin_popover(
            self._host,
            self._summary,
            "Change palette of %s" % owner_name(self._host),
            large=True,
        )
        self._stack = QWidget(popover)
        stack = QVBoxLayout(self._stack)
        stack.setContentsMargins(0, 0, 0, 0)
        self._list_page = QWidget(self._stack)
        list_layout = QVBoxLayout(self._list_page)
        list_layout.setContentsMargins(0, 0, 0, 0)
        self._roles_list = _RoleList(self._list_page, self._open_current)
        self._states = QCheckBox("Show each state", self._list_page)
        self._states.setObjectName("formBuilder.paletteStates")
        self._states.setAccessibleName(part_name("Palette", "show each state"))
        self._states.setChecked(self._per_state)
        self._states.toggled.connect(self._toggle_states)
        self._start = QPushButton("Start from a colour\u2026", self._list_page)
        self._start.setAccessibleName(part_name("Palette", "start from a colour"))
        self._start.clicked.connect(self._start_from)
        list_layout.addWidget(self._states)
        list_layout.addWidget(self._roles_list, 1)
        list_layout.addWidget(self._start)
        self._brush_page = QWidget(self._stack)
        self._brush_layout = QVBoxLayout(self._brush_page)
        self._brush_layout.setContentsMargins(0, 0, 0, 0)
        back = QPushButton("\u2039 Palette", self._brush_page)
        back.setAccessibleName(part_name("Palette", "back"))
        back.clicked.connect(self._show_list)
        self._brush_layout.addWidget(back)
        self._brush_form = None
        self._start_page = QWidget(self._stack)
        self._start_layout = QVBoxLayout(self._start_page)
        self._start_layout.setContentsMargins(0, 0, 0, 0)
        start_back = QPushButton("\u2039 Palette", self._start_page)
        start_back.setAccessibleName(part_name("Palette", "back"))
        start_back.clicked.connect(self._show_list)
        self._start_layout.addWidget(start_back)
        self._start_picker = None
        use = QPushButton("Use this colour", self._start_page)
        use.setAccessibleName(part_name("Palette", "use this colour"))
        use.clicked.connect(self._apply_start)
        self._start_layout.addWidget(use)
        self._confirm = QWidget(self._stack)
        confirm_layout = QVBoxLayout(self._confirm)
        self._confirm_label = QLabel(self._confirm)
        self._confirm_label.setWordWrap(True)
        replace = QPushButton("Replace", self._confirm)
        replace.setAccessibleName(part_name("Palette", "replace"))
        cancel = QPushButton("Cancel", self._confirm)
        cancel.setAccessibleName(part_name("Palette", "cancel"))
        replace.clicked.connect(self._confirm_replace)
        cancel.clicked.connect(self._show_list)
        confirm_layout.addWidget(self._confirm_label)
        confirm_layout.addWidget(replace)
        confirm_layout.addWidget(cancel)
        stack.addWidget(self._list_page)
        stack.addWidget(self._brush_page)
        stack.addWidget(self._start_page)
        stack.addWidget(self._confirm)
        popover.body().addWidget(self._stack)
        popover.set_reset(self._host.reset if self._written else None)
        self._popover = popover
        self._pending = ColorValue(26, 127, 55)
        self._fill_roles()
        self._show_list()
        popover.open_popover()
        self._filter = _EscFilter(self)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self._filter)
        self._roles_list.setFocus()

    def _fill_roles(self) -> None:
        self._roles_list.clear()
        self._roles_list.setProperty("perState", self._per_state)
        for label, role in _ROLES:
            item = QListWidgetItem(self._roles_list)
            row = QWidget(self._roles_list)
            layout = QHBoxLayout(row)
            layout.setContentsMargins(4, 2, 4, 2)
            name = QLabel(label, row)
            written = role in self._roles and any(self._roles[role].values())
            if written:
                font = QFont(name.font())
                font.setBold(True)
                name.setFont(font)
            layout.addWidget(name, 1)
            if self._per_state:
                for group, caption in _STATE_LABELS:
                    layout.addWidget(self._swatch(row, role, group, caption))
            else:
                layout.addWidget(self._swatch(row, role, "all", "All states"))
            reset = QToolButton(row)
            reset.setText("\u21ba")
            reset.setAccessibleName(part_name("Palette", "reset " + label.split(" (", 1)[0]))
            reset.setFocusPolicy(_focus("NoFocus"))  # type: ignore[arg-type]
            reset.setVisible(written)
            reset.clicked.connect(lambda _checked=False, name=role: self._reset_role(name))
            layout.addWidget(reset)
            item.setSizeHint(row.sizeHint())
            self._roles_list.addItem(item)
            self._roles_list.setItemWidget(item, row)
        self._roles_list.setCurrentRow(0)

    def _swatch(self, parent: QWidget, role: str, group: str, caption: str) -> Swatch:
        swatch = Swatch(parent, 16)
        swatch.set_tokens(self._host.chrome)
        swatch.setAccessibleName(part_name("Palette", caption))
        brush = self._brush_for(role, group)
        color = brush.color if brush is not None else None
        swatch.set_color(color, hollow=color is None)
        swatch.setToolTip(caption)
        swatch.mousePressEvent = lambda event, name=role, which=group: self._open_brush(name, which)  # type: ignore[method-assign]
        return swatch

    def _brush_for(self, role: str, group: str) -> Optional[BrushValue]:
        stored = self._roles.get(role, {})
        if group == "all":
            return stored.get("active") or stored.get("all")
        return stored.get(group)

    def _open_current(self, group: str) -> None:
        row = self._roles_list.currentRow()
        if row < 0:
            return
        _label, role = _ROLES[row]
        self._open_brush(role, "all" if not self._per_state else group)

    def _ensure_brush(self) -> None:
        if self._brush_form is not None:
            return
        form = BrushForm(self._brush_page, self._host, self._brush_changed)
        self._brush_form = form
        self._brush_layout.addWidget(form)

    def _ensure_start(self) -> None:
        if self._start_picker is not None:
            return
        picker = ColorPicker(
            self._start_page,
            on_color=self._hold_start,
            on_invalid=self._host.invalid,
            row="Colour",
        )
        picker.set_tokens(self._host.chrome)
        self._start_picker = picker
        self._start_layout.insertWidget(1, picker)

    def _open_brush(self, role: str, group: str) -> None:
        self._page = "brush"
        self._brush_role = role
        self._brush_group = group
        self._ensure_brush()
        current = self._brush_for(role, group) or BrushValue(brushstyle="NoBrush")
        form = self._brush_form
        if form is not None:
            form.set_brush(current)
        self._list_page.hide()
        self._start_page.hide()
        self._confirm.hide()
        self._brush_page.show()
        if form is not None:
            form.setFocus()
        refit_widget(self._brush_page)

    def _show_list(self) -> None:
        self._page = "list"
        self._confirming = False
        self._brush_page.hide()
        self._start_page.hide()
        self._confirm.hide()
        self._list_page.show()
        self._fill_roles()
        self._roles_list.setFocus()
        if self._popover is not None and not self._popover.closed:
            refit_widget(self._list_page)

    def _brush_changed(self, brush: BrushValue) -> None:
        role = self._brush_role
        stored = dict(self._roles.get(role, {}))
        if self._brush_group == "all" or not self._per_state:
            for group in _GROUPS:
                stored[group] = brush
        else:
            stored[self._brush_group] = brush
        self._roles[role] = stored
        self._commit()

    def _reset_role(self, role: str) -> None:
        self._roles.pop(role, None)
        self._commit()
        self._fill_roles()

    def _toggle_states(self, checked: bool) -> None:
        self._per_state = bool(checked)
        if self._per_state:
            for role, stored in list(self._roles.items()):
                source = stored.get("active") or stored.get("all")
                if source is None:
                    continue
                for group in _GROUPS:
                    stored.setdefault(group, source)
                self._roles[role] = stored
        if self._roles:
            self._commit()
        self._fill_roles()

    def _start_from(self) -> None:
        self._page = "start"
        self._ensure_start()
        self._list_page.hide()
        self._brush_page.hide()
        self._confirm.hide()
        self._start_page.show()
        if self._start_picker is not None:
            self._start_picker.setFocus()
        refit_widget(self._start_page)

    def _hold_start(self, color: ColorValue) -> None:
        self._pending = color

    def _apply_start(self) -> None:
        count = len(self._roles)
        if count:
            self._confirming = True
            self._confirm_label.setText("Replace the %d colours you set?" % count)
            self._start_page.hide()
            self._confirm.show()
            return
        self._write_derived(self._pending)

    def _confirm_replace(self) -> None:
        self._confirming = False
        self._write_derived(self._pending)

    def _write_derived(self, color: ColorValue) -> None:
        derived = palette_from_button(color)
        self._roles = _index(derived)
        self._per_state = False
        if self._states is not None:
            self._states.blockSignals(True)
            self._states.setChecked(False)
            self._states.blockSignals(False)
        self._commit()
        self._show_list()

    def _commit(self) -> None:
        popover = self._popover
        if popover is None:
            return
        self._palette = _assemble(self._roles)
        self._written = True
        self._host.commit(self._palette, session=popover.session)
        self._summary.set_summary(palette_summary(self._palette, mixed=False))
        popover.set_reset(self._host.reset)


def _index(palette: PaletteValue) -> Dict[str, Dict[str, BrushValue]]:
    found: Dict[str, Dict[str, BrushValue]] = {}
    for group in _GROUPS:
        for role in getattr(palette, group):
            found.setdefault(role.role, {})[group] = role.brush
    return found


def _differs(roles: Dict[str, Dict[str, BrushValue]]) -> bool:
    for stored in roles.values():
        brushes = [stored.get(group) for group in _GROUPS]
        if any(brush != brushes[0] for brush in brushes):
            return True
    return False


def _assemble(roles: Dict[str, Dict[str, BrushValue]]) -> PaletteValue:
    groups = {}
    for group in _GROUPS:
        collected = []
        for _label, role in _ROLES:
            brush = roles.get(role, {}).get(group)
            if brush is not None:
                collected.append(ColorRole(role, brush))
        groups[group] = tuple(collected)
    return PaletteValue(active=groups["active"], inactive=groups["inactive"], disabled=groups["disabled"])


def register(registrar: Registrar) -> None:
    registrar.editor(EditorKey(PaletteValue.ELEMENT), PaletteEditor, baseline=False)
