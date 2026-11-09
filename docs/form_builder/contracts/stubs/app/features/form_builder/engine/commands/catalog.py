"""The command catalog (CONTRACTS.md section 3.5).

Each class is the parameter record of one command. Semantics are in the
docstrings and in CONTRACTS.md 3.5; the owning WP is in brackets. A WP that
needs a command not listed here adds a module under
``engine/commands/catalog_ext/`` (discovered in sorted module order) and lists it
in its PR; it never edits this file.

Common rules for every command:
* Ids that do not exist raise CommandRejected (stale UI state is normal).
* Names chosen by the planner use ``UiDocument.unique_name`` (Designer suffix rule).
* New property entries are inserted by rank (``QtClassTable.property_rank``).
* A command that would change nothing applies zero ops (``noop``) unless noted.
* Every command sets the selection after it (``ctx.select``) as noted; default
  is "unchanged minus removed ids".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Hashable, Literal, Optional, Tuple

from app.features.form_builder.engine.commands.base import PlanContext
from app.features.form_builder.engine.commands.placement import Placement
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec
from app.features.form_builder.engine.ui4.values import RectValue, SizeValue, Value


class _CommandBase:
    """Default protocol members (implementations override as documented)."""

    command_type: ClassVar[str] = ""
    merge_token: Optional[str] = None

    @property
    def label(self) -> str:
        ...

    def merge_key(self) -> Optional[Hashable]:
        """None unless the class documents a key."""
        ...

    def apply(self, doc: UiDocument, ctx: PlanContext) -> Any:
        ...


# =============================================================================
# Structure  [M1.2 unless noted]
# =============================================================================


@dataclass(frozen=True)
class InsertFragment(_CommandBase):
    """Insert, paste, duplicate, Alt-drag clone, palette drop, template insert.

    ``fragment`` has ``id=None`` everywhere; the planner allocates ids pre-order.
    The whole rename map is computed before inserting, against
    ``doc.names()`` plus names already chosen for this fragment. Name
    collisions are renamed with the suffix rule; references INSIDE the
    fragment (buddy, tab stops, zorder, addaction, connections: rewritten in the
    specs; cbcs formulas: RenameParticipants with ``scope`` = inserted ids)
    follow the renames, applied simultaneously; references to names outside the
    fragment are kept (LOGIC_DESIGN 2.13). Connections in the fragment are added
    only when both ends exist after the paste. Custom widget declarations and
    resource includes are merged by class name / location (an existing
    declaration wins; a conflicting one is reported in the result).
    ``placement`` decides the parent; inserting into a container without a layout
    with ``auto_layout=True`` first applies a QVBoxLayout (pain 1) in the same entry.
    Result: ``InsertResult(ids, renames, conflicts)``. Selects the inserted top-level ids.
    """

    command_type: ClassVar[str] = "insert_fragment"
    placement: Placement
    fragment: Fragment
    auto_layout: bool = True


@dataclass(frozen=True)
class InsertResult:
    ids: Tuple[NodeId, ...]
    renames: Tuple[Tuple[str, str], ...]
    conflicts: Tuple[str, ...] = ()


@dataclass(frozen=True)
class DeleteNodes(_CommandBase):
    """Delete widgets, layouts (Break layout is separate), spacers, actions, action
    groups, items, pages, connections, button groups, custom widget declarations.

    Ids inside another deleted id's subtree are ignored. A deleted widget's layout
    item is removed too, except in grid and form layouts where the empty cell
    stays (Designer parity; SimplifyGrid compacts).
    Native references to deleted names are removed in the same entry:
    connections with that sender or receiver, tab stops, zorder entries,
    addaction refs, ``buddy`` properties naming them, ``buttonGroup`` attributes
    of a deleted group. ``cbcs*`` logic references are NOT removed (they become
    FB101 problems; LOGIC_DESIGN 2.13). References to a name that another
    surviving node also uses (FB010) are NOT removed. DeleteParticipants may
    add ops.
    Selects the nearest surviving sibling, else the parent.
    """

    command_type: ClassVar[str] = "delete_nodes"
    ids: Tuple[NodeId, ...]


@dataclass(frozen=True)
class MoveNodes(_CommandBase):
    """Move/reparent existing content, keeping ids (drag, Alt+arrows, outline drag).

    ``ids`` must be siblings-or-not; they are moved in document order to
    consecutive positions starting at ``placement``. Moving a node into its own
    subtree is rejected. A grid move changes only the moved items' cells
    (pain 21). Moving the last item out of a layout leaves the layout empty
    (never deleted implicitly). Selects the moved ids.
    """

    command_type: ClassVar[str] = "move_nodes"
    ids: Tuple[NodeId, ...]
    placement: Placement
    merge_token: Optional[str] = None

    # merge_key() = ("move", ids): repeated Alt+arrow presses within 1 s
    # (one UX-NUDGE-001 gesture token) merge into one step.


@dataclass(frozen=True)
class Wrap(_CommandBase):
    """Wrap sibling layout items (same parent layout, or same layout-less
    container) into a new container widget and/or a new layout (Ctrl+G).

    ``container_class`` None means "layout only" (Designer's Lay Out on a
    selection inside a layout: the items move into a new nested layout at the
    position of the first one). With a container, the new widget takes the first
    item's position and gets ``layout_class`` (default QVBoxLayout). Items keep
    their relative order (document order of their layout items). For grid
    parents, ``cells`` gives each wrapped item's (row, column) in the new grid
    (measured by the Qt side from the live geometry); None places them in
    reading order. Selects the new container (or layout).
    """

    command_type: ClassVar[str] = "wrap"
    ids: Tuple[NodeId, ...]
    container_class: Optional[str]
    layout_class: str = "QVBoxLayout"
    cells: Optional[Tuple[Tuple[NodeId, int, int], ...]] = None


@dataclass(frozen=True)
class Unwrap(_CommandBase):
    """Remove a container widget (or a nested layout) and put its children into
    its parent layout at its position, in its visual order (Ctrl+Shift+G).
    Properties of the removed container are dropped (undo restores them).
    Rejected for the root widget and for page containers. Selects the children."""

    command_type: ClassVar[str] = "unwrap"
    id: NodeId


@dataclass(frozen=True)
class ApplyLayout(_CommandBase):
    """Give a container without a layout a layout (Designer "Lay Out ..." on a
    container). Children become items in ``order`` (ids measured by the Qt side
    from geometry: top-to-bottom, left-to-right), or with ``cells`` for grid/form.
    Their ``geometry`` properties are removed (undo restores). Selects the layout."""

    command_type: ClassVar[str] = "apply_layout"
    widget: NodeId
    layout_class: str
    order: Tuple[NodeId, ...] = ()
    cells: Optional[Tuple[Tuple[NodeId, int, int, int, int], ...]] = None


@dataclass(frozen=True)
class BreakLayout(_CommandBase):
    """Remove a layout and keep sizes (R3 41, pain 5). The owner widget's children
    stay as free children with ``geometry`` set from ``geometries`` (live rects in
    the owner's coordinates, measured by the Qt side). A nested layout's items
    move up into the parent layout at its position instead. The UI confirms first.
    Selects the owner widget."""

    command_type: ClassVar[str] = "break_layout"
    layout: NodeId
    geometries: Tuple[Tuple[NodeId, RectValue], ...] = ()


@dataclass(frozen=True)
class MorphLayout(_CommandBase):
    """Change a layout's class (box <-> grid <-> form). Items keep order; cells are
    assigned by the Designer morph rules (R3 54): box->grid one row/column per
    item, grid->box reading order, form<->grid two columns. Properties the new
    class lacks are removed (undo restores)."""

    command_type: ClassVar[str] = "morph_layout"
    layout: NodeId
    new_class: str


@dataclass(frozen=True)
class MorphWidget(_CommandBase):
    """Change a widget's class (R3 55, Designer morph menu). Properties the new
    class has (per the class table) are kept; others are removed and listed in
    the result. Children, layout and items are kept when the new class can hold
    them, else rejected."""

    command_type: ClassVar[str] = "morph_widget"
    id: NodeId
    new_class: str


@dataclass(frozen=True)
class SimplifyGrid(_CommandBase):
    """Remove empty rows and columns of a grid, shifting cells (R3 43)."""

    command_type: ClassVar[str] = "simplify_grid"
    layout: NodeId


@dataclass(frozen=True)
class AdjustSize(_CommandBase):
    """Set ``geometry`` width/height to ``size`` (the live sizeHint, measured by
    the Qt side) (R3 42)."""

    command_type: ClassVar[str] = "adjust_size"
    id: NodeId
    size: SizeValue


@dataclass(frozen=True)
class SetZOrder(_CommandBase):
    """Raise/lower (R3 32, pain 24). ``order`` is the full new stacking order of
    the parent's direct child widget names, bottom to top, built by the caller
    from the REAL child list (``query.tree.child_stack_order``). Writes the
    parent's ``zorder`` field; an order equal to document order clears it."""

    command_type: ClassVar[str] = "set_zorder"
    parent: NodeId
    order: Tuple[str, ...]


# =============================================================================
# Properties  [M1.2; editors in M4.3]
# =============================================================================


@dataclass(frozen=True)
class SetProperty(_CommandBase):
    """Set (``value`` not None) or reset (``value`` None: remove the entry, R3 146)
    one property or attribute on one node.

    ``stdset``: None keeps the existing entry's stdset (or none for new entries);
    "0" makes a dynamic property. Setting a value semantically equal to the
    current one is a noop. Text containing characters outside the XML 1.0 Char
    range is rejected (CommandRejected). ``cbcsSplitterSizes`` (comma-separated
    ints on a QSplitter, ``stdset="0"``) is set through this command.
    ``merge_key()`` = ``("set_property", owner, kind, name)``
    so rapid edits within one gesture (``merge_token``) merge.
    """

    command_type: ClassVar[str] = "set_property"
    owner: NodeId
    name: str
    value: Optional[Value]
    kind: Literal["property", "attribute"] = "property"
    stdset: Optional[str] = None
    merge_token: Optional[str] = None


@dataclass(frozen=True)
class SetPropertyMany(_CommandBase):
    """Multi-selection edit (R3 147): the same change on every owner whose class
    has the property (class table) or already has the entry; others are skipped
    and reported. One entry. ``merge_key()`` = ``("set_many", owners, kind, name)``."""

    command_type: ClassVar[str] = "set_property_many"
    owners: Tuple[NodeId, ...]
    name: str
    value: Optional[Value]
    kind: Literal["property", "attribute"] = "property"
    stdset: Optional[str] = None
    merge_token: Optional[str] = None


@dataclass(frozen=True)
class Rename(_CommandBase):
    """Change a widget/layout/spacer/action/action-group/button-group name.

    Rejected when ``new_name`` is not a Python identifier, is a keyword, starts
    with ``cbcs``, is reserved for formulas (LOGIC_DESIGN 4.5) or is already used
    (CommandRejected with FB011/FB106/FB010). Updates every native reference in
    the same entry: buddy cstrings, tab stops, zorder, addaction, connection
    sender/receiver, action ``menu`` fields, ``buttonGroup`` attribute values
    (when a button group is renamed), and ``<class>`` when the root is renamed
    and ``<class>`` equalled the old name. When the old name is shared with
    another node (FB010), the node is renamed but NO references are rewritten. RenameParticipants
    (M6.0b: formula tokens, step targets, error-label references) add their ops.
    Updating ``self.ui.oldName`` in user code is NOT part of this command
    (integration offers it separately through CBCS rename-refactor).
    """

    command_type: ClassVar[str] = "rename"
    id: NodeId
    new_name: str


@dataclass(frozen=True)
class SetLayoutCell(_CommandBase):
    """Set row/column/rowspan/colspan/alignment of a layout item (None clears an
    optional field). Rejected when the result overlaps another item in a grid."""

    command_type: ClassVar[str] = "set_layout_cell"
    item: NodeId
    row: Optional[int] = None
    column: Optional[int] = None
    rowspan: Optional[int] = None
    colspan: Optional[int] = None
    alignment: Optional[str] = None


@dataclass(frozen=True)
class SetLayoutStretch(_CommandBase):
    """Set the layout's ``stretch``/``rowstretch``/``columnstretch``/
    ``rowminimumheight``/``columnminimumwidth`` field (comma list text, None
    clears). ``merge_key()`` = ``("layout_stretch", layout, field)``."""

    command_type: ClassVar[str] = "set_layout_stretch"
    layout: NodeId
    field: Literal["stretch", "rowstretch", "columnstretch", "rowminimumheight", "columnminimumwidth"]
    value: Optional[str]
    merge_token: Optional[str] = None


@dataclass(frozen=True)
class SetGeometry(_CommandBase):
    """Set ``geometry`` of a free-floating widget or the root (page-edge resize).
    ``merge_key()`` = ``("geometry", id)``."""

    command_type: ClassVar[str] = "set_geometry"
    id: NodeId
    rect: RectValue
    merge_token: Optional[str] = None


# =============================================================================
# Containers and items  [M4.2, M4.4]
# =============================================================================


@dataclass(frozen=True)
class MovePage(_CommandBase):
    """Reorder a page of a page container (``from_index`` -> ``to_index``, both in
    the pre-move list). Also updates ``currentIndex`` so the same page stays
    current."""

    command_type: ClassVar[str] = "move_page"
    container: NodeId
    from_index: int
    to_index: int


@dataclass(frozen=True)
class SetItems(_CommandBase):
    """Replace a list/combo/tree/table widget's ``items`` (and, for tables and
    trees, ``rows``/``columns`` headers) wholesale (the item editors commit a whole
    list). Specs have ``id=None``; ids are allocated. ``None`` leaves that slot."""

    command_type: ClassVar[str] = "set_items"
    widget: NodeId
    items: Optional[Tuple[NodeSpec, ...]] = None
    rows: Optional[Tuple[NodeSpec, ...]] = None
    columns: Optional[Tuple[NodeSpec, ...]] = None


# =============================================================================
# Actions and main windows  [M5.1]
# =============================================================================


@dataclass(frozen=True)
class CreateAction(_CommandBase):
    """Add an ``<action>`` on the form root (``group`` None) or in an action group,
    and optionally an ``<addaction>`` at ``ref_at``. ``spec`` has ``id=None``."""

    command_type: ClassVar[str] = "create_action"
    spec: NodeSpec
    group: Optional[NodeId] = None
    ref_at: Optional[Placement] = None


@dataclass(frozen=True)
class AddActionRef(_CommandBase):
    """Insert ``<addaction name=..>`` (an action name, a menu widget name, or
    ``separator``) into a menu, menubar or toolbar (pain 17 drag)."""

    command_type: ClassVar[str] = "add_action_ref"
    placement: Placement
    name: str


@dataclass(frozen=True)
class CreateMenu(_CommandBase):
    """"Type here" on a menubar or menu: a QMenu child widget with ``title`` plus its
    addaction ref at ``placement``. Result: the menu id."""

    command_type: ClassVar[str] = "create_menu"
    placement: Placement
    title: str


# =============================================================================
# Connections, tab order, buddies, button groups  [M5.6, M6.1]
# =============================================================================


@dataclass(frozen=True)
class AddConnection(_CommandBase):
    """Append (``index`` None) or insert a ``<connection>``. Signatures are stored
    normalised as written by Designer (``clicked()``, ``toggled(bool)``)."""

    command_type: ClassVar[str] = "add_connection"
    sender: str
    signal: str
    receiver: str
    slot: str
    index: Optional[int] = None


@dataclass(frozen=True)
class EditConnection(_CommandBase):
    """Change any of a connection's four fields (None keeps)."""

    command_type: ClassVar[str] = "edit_connection"
    id: NodeId
    sender: Optional[str] = None
    signal: Optional[str] = None
    receiver: Optional[str] = None
    slot: Optional[str] = None


@dataclass(frozen=True)
class MoveConnection(_CommandBase):
    command_type: ClassVar[str] = "move_connection"
    id: NodeId
    to_index: int


@dataclass(frozen=True)
class SetTabStops(_CommandBase):
    """Write ``<tabstops>`` (None removes the element: Qt's default order applies)."""

    command_type: ClassVar[str] = "set_tabstops"
    names: Optional[Tuple[str, ...]]


@dataclass(frozen=True)
class SetBuddy(_CommandBase):
    """Set (``target`` a widget name) or clear (None) a label's ``buddy`` cstring."""

    command_type: ClassVar[str] = "set_buddy"
    label_widget: NodeId
    target: Optional[str]


@dataclass(frozen=True)
class SetButtonGroup(_CommandBase):
    """Put buttons in a group (creating ``<buttongroup name=group>`` when absent)
    or take them out (``group`` None). A group left with no members is removed."""

    command_type: ClassVar[str] = "set_button_group"
    buttons: Tuple[NodeId, ...]
    group: Optional[str]


@dataclass(frozen=True)
class SetFormSlots(_CommandBase):
    """Replace the form's ``<slots>`` declaration (None removes it)."""

    command_type: ClassVar[str] = "set_form_slots"
    signals: Optional[Tuple[str, ...]]
    slots: Optional[Tuple[str, ...]]


# =============================================================================
# Promotion, resources, form settings  [M5.2, M5.4, M5.5b]
# =============================================================================


@dataclass(frozen=True)
class Promote(_CommandBase):
    """Promote widgets to ``class_name`` (declared from ``declaration``, a
    ``customwidget`` spec with id=None, merged by class name), or demote
    (``class_name`` None: back to the declaration's ``extends``; a declaration
    nobody uses any more is removed). Python module path goes in ``header``."""

    command_type: ClassVar[str] = "promote"
    ids: Tuple[NodeId, ...]
    class_name: Optional[str]
    declaration: Optional[NodeSpec] = None


@dataclass(frozen=True)
class SetCustomWidget(_CommandBase):
    """Add, replace (same class_name) or remove (``spec`` None) a declaration."""

    command_type: ClassVar[str] = "set_custom_widget"
    class_name: str
    spec: Optional[NodeSpec]


@dataclass(frozen=True)
class SetResourceIncludes(_CommandBase):
    """Replace the ``<resources>`` include list (order kept as given)."""

    command_type: ClassVar[str] = "set_resource_includes"
    locations: Tuple[str, ...]


@dataclass(frozen=True)
class SetFormField(_CommandBase):
    """Set a ``ui``-node field (author, comment, exportmacro, class_name,
    layoutdefault, layoutfunction, pixmapfunction, language, displayname,
    idbasedtr, label, connectslotsbyname) or replace the ``includes`` list
    (``field="includes"``, ``value`` a tuple of include specs)."""

    command_type: ClassVar[str] = "set_form_field"
    field: str
    value: object


# =============================================================================
# Whole document  [M2.2]
# =============================================================================


@dataclass(frozen=True)
class ReplaceDocument(_CommandBase):
    """Replace the document with ``text`` parsed by the reader: View XML commit,
    draft restore, local-history restore, external reload ("take theirs").

    Parse failure raises CommandRejected carrying the UiReadError (code, line,
    column); the document is untouched and the caller keeps the text in View
    XML. Success applies one ReplaceRootOp (all non-document ids fresh).
    Selection after: nodes whose object names existed before keep being selected
    (matched by name); else the root.
    ``reason`` is recorded for the undo label ("Edit XML", "Restore draft",
    "Reload from disk").
    """

    command_type: ClassVar[str] = "replace_document"
    text: str
    reason: Literal["xml_edit", "draft", "history", "reload"] = "xml_edit"


# =============================================================================
# Logic  [M6.0b]
# =============================================================================


@dataclass(frozen=True)
class SetLogic(_CommandBase):
    """Set or clear one ``cbcs*`` logic property through the logic storage codec
    (``engine.logic.storage``): ``text`` is the canonical serialized value (formula
    text or canonical JSON) or None to remove. Writes ``stdset="0"`` and a
    ``<string notr="true">`` value. Also maintains the root's ``cbcsLogic`` version
    (added on first logic property, removed with the last). Refused (FB402) when
    the document's logic version is newer than supported. Text outside the
    XML 1.0 Char range is rejected. Layout keys (``CBCS_LAYOUT_KEYS``) are
    refused here; they go through SetProperty.
    ``merge_key()`` = ``("logic", owner, key)``."""

    command_type: ClassVar[str] = "set_logic"
    owner: NodeId
    key: str
    text: Optional[str]
    merge_token: Optional[str] = None
