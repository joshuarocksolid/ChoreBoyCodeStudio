"""Catalog semantics (CONTRACTS.md section 3.5)."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.ops import MoveNodeOp
from app.features.form_builder.engine.commands.catalog import (
    AddActionRef,
    AddConnection,
    AdjustSize,
    ApplyLayout,
    BreakLayout,
    CreateAction,
    CreateMenu,
    DeleteNodes,
    EditConnection,
    InsertFragment,
    InsertResult,
    MorphLayout,
    MorphWidget,
    MoveConnection,
    MoveNodes,
    MovePage,
    Promote,
    Rename,
    ReplaceDocument,
    SetBuddy,
    SetButtonGroup,
    SetCustomWidget,
    SetFormField,
    SetFormSlots,
    SetGeometry,
    SetItems,
    SetLayoutCell,
    SetLayoutStretch,
    SetLogic,
    SetProperty,
    SetPropertyMany,
    SetResourceIncludes,
    SetTabStops,
    SetZOrder,
    SimplifyGrid,
    Unwrap,
    Wrap,
)
from app.features.form_builder.engine.commands.placement import (
    InActionList,
    InBoxLayout,
    InContainer,
    InGridCell,
)
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.tree import child_stack_order, references_to
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutItemNode, WidgetNode
from app.features.form_builder.engine.ui4.schema import HeaderDecl
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.values import (
    CStringValue,
    NumberValue,
    RectValue,
    SizeValue,
    StringValue,
)
from tests.form_builder.engine.commands._support import (
    BOX,
    FREE,
    GRID,
    SHARED,
    STACK,
    button_spec,
    cell_of,
    nid,
    open_log,
    prop_text,
)


def _entry_text(entry: PropertyEntry) -> str:
    if isinstance(entry.value, (StringValue, CStringValue)):
        return entry.value.text
    raise AssertionError(type(entry.value).__name__)


def _layout(doc: UiDocument) -> NodeId:
    assert doc.root.layout is not None
    return doc.root.layout.id


def _item(doc: UiDocument, name: str) -> LayoutItemNode:
    parent = doc.parent(nid(doc, name))
    assert isinstance(parent, LayoutItemNode)
    return parent


def test_insert_renames_collisions_and_keeps_only_live_connections() -> None:
    log = open_log(BOX)
    doc = log.document
    fragment = Fragment(
        nodes=(button_spec("okButton", "Go"), button_spec("fresh", "F")),
        connections=(
            NodeSpec(
                "connection",
                None,
                (
                    ("sender", "okButton"),
                    ("signal", "clicked()"),
                    ("receiver", "label"),
                    ("slot", "clear()"),
                ),
            ),
            NodeSpec(
                "connection",
                None,
                (
                    ("sender", "ghost"),
                    ("signal", "clicked()"),
                    ("receiver", "ghost"),
                    ("slot", "clear()"),
                ),
            ),
        ),
    )
    outcome = log.execute(InsertFragment(InBoxLayout(_layout(doc), 1), fragment))
    result = outcome.result
    assert isinstance(result, InsertResult)
    assert ("okButton", "okButton_2") in result.renames
    assert doc.node(nid(doc, "okButton_2")).prop("text") is not None
    senders = [node.field("sender") for node in doc.ui.children("connections")]
    assert senders == ["okButton_2"]


def test_drop_onto_a_layoutless_widget_creates_a_vbox() -> None:
    log = open_log(FREE)
    doc = log.document
    log.execute(InsertFragment(InContainer(doc.root.id, 0), Fragment(nodes=(button_spec("extra"),))))
    assert doc.root.layout is not None
    assert doc.root.layout.class_name == "QVBoxLayout"
    assert "extra" in doc.names()


def test_delete_in_a_box_removes_the_item_and_native_references_but_keeps_logic() -> None:
    log = open_log(BOX)
    doc = log.document
    button = nid(doc, "okButton")
    label = nid(doc, "label")
    log.execute(SetBuddy(label, "okButton"))
    log.execute(SetTabStops(("okButton", "label")))
    log.execute(AddConnection("okButton", "clicked", "label", "clear"))
    log.execute(SetLogic(label, "cbcsEnabledWhen", "okButton"))
    codes = log.execute(DeleteNodes((button,))).result
    assert codes == ()
    assert "okButton" not in doc.names()
    assert doc.root.layout is not None
    assert len(doc.root.layout.items) == 1
    assert doc.ui.children("connections") == ()
    stops = doc.ui.field("tabstops")
    assert stops == ("label",)
    assert doc.node(label).prop("buddy") is None
    logic = doc.node(label).prop("cbcsEnabledWhen")
    assert logic is not None
    assert _entry_text(logic) == "okButton"


def test_delete_in_a_grid_leaves_the_cell_empty() -> None:
    log = open_log(GRID)
    doc = log.document
    log.execute(DeleteNodes((nid(doc, "b"),)))
    assert "b" not in doc.names()
    layout = doc.root.layout
    assert layout is not None
    empty = [item for item in layout.items if item.content is None]
    assert len(layout.items) == 3
    assert len(empty) == 1
    assert (empty[0].row, empty[0].column) == (0, 1)


def test_delete_ignores_a_descendant_of_another_deleted_id() -> None:
    log = open_log(BOX)
    doc = log.document
    button = nid(doc, "okButton")
    item = doc.parent(button)
    assert item is not None
    log.execute(DeleteNodes((item.id, button)))
    assert "okButton" not in doc.names()
    assert log.can_undo()


@pytest.mark.pain("P-21")
def test_grid_move_changes_only_the_moved_cell() -> None:
    log = open_log(GRID)
    doc = log.document
    before_b = cell_of(doc, "b")
    before_c = cell_of(doc, "c")
    log.execute(MoveNodes((nid(doc, "a"),), InGridCell(_layout(doc), 1, 1)))
    assert cell_of(doc, "a") == (1, 1)
    assert cell_of(doc, "b") == before_b
    assert cell_of(doc, "c") == before_c


def test_move_in_a_box_uses_the_visual_index() -> None:
    log = open_log(BOX)
    doc = log.document
    layout = doc.root.layout
    assert layout is not None
    log.execute(MoveNodes((nid(doc, "okButton"),), InBoxLayout(layout.id, len(layout.items))))
    names = []
    for item in doc.root.layout.items:  # type: ignore[union-attr]
        content = item.content
        assert isinstance(content, WidgetNode)
        names.append(content.object_name)
    assert names == ["label", "okButton"]


def _box_of(count: int) -> str:
    rows = []
    for index in range(count):
        rows.append(
            "<item><widget class=\"QPushButton\" name=\"b%s\">"
            "<property name=\"text\"><string>x</string></property>"
            "</widget></item>" % index
        )
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<ui version=\"4.0\"><class>Form</class>"
        "<widget class=\"QWidget\" name=\"Form\">"
        "<layout class=\"QVBoxLayout\" name=\"verticalLayout\">%s</layout>"
        "</widget><resources/><connections/></ui>" % "".join(rows)
    )


def _box_names(doc: UiDocument) -> list:
    layout = doc.root.layout
    assert layout is not None
    names = []
    for item in layout.items:
        content = item.content
        assert isinstance(content, WidgetNode)
        names.append(content.object_name)
    return names


def test_reordering_siblings_moves_only_the_selection() -> None:
    """One selected sibling is one MoveNodeOp. Unselected siblings stay put."""
    log = open_log(_box_of(8))
    doc = log.document
    layout = doc.root.layout
    assert layout is not None
    button = nid(doc, "b0")
    carrier = doc.parent(button)
    assert carrier is not None
    log.execute(MoveNodes((button,), InBoxLayout(layout.id, len(layout.items))))
    entry = log.entries()[-1]
    assert len(entry.ops) == 1
    assert isinstance(entry.ops[0], MoveNodeOp)
    assert entry.ops[0].node == carrier.id
    assert _box_names(doc) == ["b1", "b2", "b3", "b4", "b5", "b6", "b7", "b0"]


def test_wrap_and_unwrap_round_trip_the_children() -> None:
    log = open_log(BOX)
    doc = log.document
    ids = (nid(doc, "okButton"), nid(doc, "label"))
    container = log.execute(Wrap(ids, "QFrame", "QVBoxLayout")).result
    assert doc.node(container).field("class_name") == "QFrame"
    assert doc.root.layout is not None
    assert len(doc.root.layout.items) == 1
    log.execute(Unwrap(container))
    names = []
    assert doc.root.layout is not None
    for item in doc.root.layout.items:
        content = item.content
        assert isinstance(content, WidgetNode)
        names.append(content.object_name)
    assert names == ["okButton", "label"]


def test_apply_layout_removes_geometry() -> None:
    log = open_log(FREE)
    doc = log.document
    order = (nid(doc, "label"), nid(doc, "okButton"))
    for name in ("label", "okButton"):
        log.execute(SetGeometry(nid(doc, name), RectValue(0, 0, 20, 10)))
    layout_id = log.execute(ApplyLayout(doc.root.id, "QVBoxLayout", order)).result
    assert doc.node(layout_id).field("class_name") == "QVBoxLayout"
    assert doc.node(nid(doc, "label")).prop("geometry") is None
    assert doc.root.layout is not None
    assert len(doc.root.layout.items) == 2


@pytest.mark.parity("R3-41")
def test_break_layout_keeps_measured_geometry() -> None:
    log = open_log(BOX)
    doc = log.document
    button = nid(doc, "okButton")
    label = nid(doc, "label")
    layout = _layout(doc)
    rect = RectValue(1, 2, 30, 40)
    log.execute(BreakLayout(layout, ((button, rect), (label, RectValue(0, 50, 10, 10)))))
    assert doc.root.layout is None
    entry = doc.node(button).prop("geometry")
    assert entry is not None
    assert entry.value == rect


@pytest.mark.parity("R3-54")
def test_morph_vbox_to_grid_uses_one_column() -> None:
    log = open_log(BOX)
    doc = log.document
    log.execute(MorphLayout(_layout(doc), "QGridLayout"))
    assert doc.root.layout is not None
    assert doc.root.layout.class_name == "QGridLayout"
    assert cell_of(doc, "okButton") == (0, 0)
    assert cell_of(doc, "label") == (1, 0)


def test_morph_widget_keeps_properties_when_the_class_table_is_empty() -> None:
    log = open_log(BOX)
    doc = log.document
    dropped = log.execute(MorphWidget(nid(doc, "okButton"), "QLabel")).result
    assert dropped == ()
    assert doc.node(nid(doc, "okButton")).field("class_name") == "QLabel"
    assert prop_text(doc, "okButton") == "OK"


def test_simplify_grid_closes_an_empty_row() -> None:
    log = open_log(GRID)
    doc = log.document
    log.execute(SetLayoutCell(_item(doc, "c").id, row=2, column=0))
    log.execute(SimplifyGrid(_layout(doc)))
    assert cell_of(doc, "a") == (0, 0)
    assert cell_of(doc, "b") == (0, 1)
    assert cell_of(doc, "c") == (1, 0)


def test_adjust_size_writes_the_measured_size() -> None:
    log = open_log(FREE)
    doc = log.document
    log.execute(SetGeometry(nid(doc, "okButton"), RectValue(4, 5, 10, 10)))
    log.execute(AdjustSize(nid(doc, "okButton"), SizeValue(80, 24)))
    entry = doc.node(nid(doc, "okButton")).prop("geometry")
    assert entry is not None
    assert entry.value == RectValue(4, 5, 80, 24)


@pytest.mark.parity("R3-32")
@pytest.mark.pain("P-24")
def test_z_order_comes_from_the_real_child_list_and_document_order_clears_it() -> None:
    log = open_log(FREE)
    doc = log.document
    root = doc.root.id
    natural = child_stack_order(doc, root)
    assert natural == tuple(child.object_name for child in doc.root.child_widgets)
    log.execute(SetZOrder(root, tuple(reversed(natural))))
    assert child_stack_order(doc, root) == tuple(reversed(natural))
    assert doc.root.field("zorder") == tuple(reversed(natural))
    log.execute(SetZOrder(root, natural))
    assert doc.root.field("zorder") is None
    assert child_stack_order(doc, root) == natural


@pytest.mark.parity("R3-146")
def test_reset_removes_the_property_and_an_equal_value_is_a_noop() -> None:
    log = open_log(BOX)
    doc = log.document
    owner = nid(doc, "okButton")
    same = log.execute(SetProperty(owner, "text", StringValue("OK")))
    assert same.noop
    assert not log.can_undo()
    log.execute(SetProperty(owner, "text", StringValue("Go")))
    log.execute(SetProperty(owner, "text", None))
    assert prop_text(doc, "okButton") is None
    assert log.undo_label() == "Reset"


@pytest.mark.parity("R3-147")
def test_multi_edit_is_one_step_for_every_owner() -> None:
    log = open_log(BOX)
    doc = log.document
    owners = (nid(doc, "okButton"), nid(doc, "label"))
    skipped = log.execute(SetPropertyMany(owners, "text", StringValue("Same"))).result
    assert skipped == ()
    assert prop_text(doc, "okButton") == "Same"
    assert prop_text(doc, "label") == "Same"
    assert len(log.entries()) == 1
    assert log.undo()
    assert prop_text(doc, "okButton") == "OK"
    assert prop_text(doc, "label") == "Hi"


def test_rename_rewrites_every_native_reference() -> None:
    log = open_log(FREE)
    doc = log.document
    button = nid(doc, "okButton")
    label = nid(doc, "label")
    log.execute(SetBuddy(label, "okButton"))
    log.execute(SetTabStops(("okButton",)))
    log.execute(SetZOrder(doc.root.id, ("okButton", "label")))
    log.execute(AddConnection("okButton", "clicked", "label", "clear"))
    log.execute(AddActionRef(InActionList(doc.root.id, 0), "okButton"))
    log.execute(
        CreateAction(NodeSpec("action", None, (("name", "openFile"), ("menu", "okButton"))))
    )
    log.execute(SetButtonGroup((button,), "groupA"))
    group = next(node.id for node in doc.iter_preorder() if node.kind == "buttongroup")
    kinds = {kind for _node, kind in references_to(doc, "okButton")}
    assert {"buddy", "tabstop", "zorder", "connection.sender", "addaction", "action.menu"} <= kinds
    log.execute(Rename(button, "submitButton"))
    assert references_to(doc, "okButton") == ()
    assert references_to(doc, "submitButton")
    log.execute(Rename(group, "groupB"))
    attr = doc.node(button).attr("buttonGroup")
    assert attr is not None
    assert _entry_text(attr) == "groupB"


def test_rename_of_a_shared_name_does_not_rewrite_references() -> None:
    log = open_log(SHARED)
    doc = log.document
    target = doc.by_name("same")[0]
    codes = log.execute(Rename(target, "other")).result
    assert codes == ("FB010",)
    assert doc.node(nid(doc, "caption")).prop("buddy") is not None
    buddy = doc.node(nid(doc, "caption")).prop("buddy")
    assert buddy is not None
    assert _entry_text(buddy) == "same"


def test_moving_a_shared_name_keeps_document_order() -> None:
    log = open_log(SHARED)
    doc = log.document
    root = doc.root
    first = doc.by_name("same")[0]
    log.execute(MoveNodes((first,), InContainer(root.id, len(root.child_widgets))))
    fresh = UiDocument.from_spec(doc.to_spec())
    assert doc.by_name("same") == fresh.by_name("same")
    assert doc.by_name("same")[0] != first


@pytest.mark.parametrize(
    ("name", "code"),
    [("form", "FB106"), ("class", "FB011"), ("okButton", "FB010"), ("cbcsThing", "FB106")],
)
def test_rename_rejects_illegal_names(name: str, code: str) -> None:
    log = open_log(BOX)
    doc = log.document
    with pytest.raises(CommandRejected) as caught:
        log.execute(Rename(nid(doc, "label"), name))
    assert caught.value.code == code
    assert not log.can_undo()


def test_layout_cell_rejects_an_overlap_and_stretch_is_stored() -> None:
    log = open_log(GRID)
    doc = log.document
    item = _item(doc, "a")
    with pytest.raises(CommandRejected):
        log.execute(SetLayoutCell(item.id, row=0, column=1))
    assert cell_of(doc, "a") == (0, 0)
    log.execute(SetLayoutCell(item.id, row=2, column=2))
    assert cell_of(doc, "a") == (2, 2)
    log.execute(SetLayoutStretch(_layout(doc), "rowstretch", "1,0,0"))
    assert doc.root.layout is not None
    assert doc.root.layout.field("rowstretch") == "1,0,0"


def test_move_page_keeps_the_same_page_current() -> None:
    log = open_log(STACK)
    doc = log.document
    log.execute(MovePage(doc.root.id, 0, 1))
    names = [child.object_name for child in doc.root.child_widgets]
    assert names == ["pageB", "pageA"]
    current = doc.root.prop("currentIndex")
    assert current is not None
    assert isinstance(current.value, NumberValue)
    assert current.value.value == 1


def test_set_items_replaces_the_slot() -> None:
    log = open_log(BOX)
    doc = log.document
    button = nid(doc, "okButton")
    spec = NodeSpec(
        "item",
        None,
        (),
        (PropertyEntry("property", "text", StringValue("One")),),
    )
    log.execute(SetItems(button, items=(spec,)))
    items = doc.node(button).children("items")
    assert len(items) == 1
    entry = items[0].prop("text")
    assert entry is not None
    assert _entry_text(entry) == "One"


def test_menu_action_and_connection_commands() -> None:
    log = open_log(FREE)
    doc = log.document
    menu = log.execute(CreateMenu(InActionList(doc.root.id, 0), "File")).result
    assert doc.node(menu).field("class_name") == "QMenu"
    assert doc.node(menu).prop("title") is not None
    action = log.execute(
        CreateAction(
            NodeSpec("action", None, (("name", "quit"),)),
            ref_at=InActionList(menu, 0),
        )
    ).result
    assert doc.node(action).field("name") == "quit"
    ref = log.execute(AddActionRef(InActionList(menu, 1), "separator")).result
    assert doc.node(ref).field("name") == "separator"
    connection = log.execute(AddConnection("okButton", "clicked", "label", "clear")).result
    assert doc.node(connection).field("signal") == "clicked()"
    log.execute(EditConnection(connection, signal="pressed"))
    assert doc.node(connection).field("signal") == "pressed()"
    log.execute(MoveConnection(connection, 0))
    assert doc.node(connection).slot_index == 0


def test_slots_buddy_and_button_group() -> None:
    log = open_log(BOX)
    doc = log.document
    button = nid(doc, "okButton")
    label = nid(doc, "label")
    log.execute(SetBuddy(label, "okButton"))
    buddy = doc.node(label).prop("buddy")
    assert buddy is not None
    assert _entry_text(buddy) == "okButton"
    log.execute(SetBuddy(label, None))
    assert doc.node(label).prop("buddy") is None
    log.execute(SetButtonGroup((button,), "choice"))
    attr = doc.node(button).attr("buttonGroup")
    assert attr is not None
    assert _entry_text(attr) == "choice"
    log.execute(SetButtonGroup((button,), None))
    assert doc.ui.children("buttongroups") == ()
    log.execute(SetFormSlots(("clicked()",), ("on_clicked()",)))
    decl = doc.ui.field("form_slots")
    assert decl is not None
    assert decl.signals == ("clicked()",)  # type: ignore[attr-defined]
    log.execute(SetFormSlots(None, None))
    assert doc.ui.field("form_slots") is None


def test_promote_demote_resources_and_form_field() -> None:
    log = open_log(BOX)
    doc = log.document
    button = nid(doc, "okButton")
    declaration = NodeSpec(
        "customwidget",
        None,
        (
            ("class_name", "MyButton"),
            ("extends", "QPushButton"),
            ("header", HeaderDecl("my_button.h")),
        ),
    )
    log.execute(Promote((button,), "MyButton", declaration))
    assert doc.node(button).field("class_name") == "MyButton"
    assert doc.custom_widget("MyButton") is not None
    log.execute(Promote((button,), None))
    assert doc.node(button).field("class_name") == "QPushButton"
    assert doc.custom_widget("MyButton") is None
    log.execute(SetCustomWidget("MyButton", declaration))
    assert doc.custom_widget("MyButton") is not None
    log.execute(SetCustomWidget("MyButton", None))
    assert doc.custom_widget("MyButton") is None
    log.execute(SetResourceIncludes(("icons.qrc",)))
    locations = tuple(node.field("location") for node in doc.ui.children("resources"))
    assert locations == ("icons.qrc",)
    log.execute(SetFormField("author", "Ada"))
    assert doc.ui.field("author") == "Ada"


def test_replace_document_and_a_bad_file_leaves_the_form() -> None:
    log = open_log(BOX)
    doc = log.document
    fingerprint = doc.fingerprint()
    log.execute(ReplaceDocument(FREE, "reload"))
    assert log.undo_label() == "Reload from disk"
    assert doc.root.layout is None
    assert "pageA" not in doc.names()
    assert log.undo()
    assert doc.fingerprint() == fingerprint
    with pytest.raises(CommandRejected) as caught:
        log.execute(ReplaceDocument("<nope/>", "xml_edit"))
    assert caught.value.error is not None
    assert doc.fingerprint() == fingerprint
    assert not log.can_undo()


def test_set_logic_maintains_the_version_and_refuses_layout_keys() -> None:
    log = open_log(BOX)
    doc = log.document
    button = nid(doc, "okButton")
    log.execute(SetLogic(button, "cbcsEnabledWhen", "1"))
    marker = doc.root.prop("cbcsLogic")
    assert marker is not None
    assert _entry_text(marker) == '{"version":1}'
    assert marker.stdset == "0"
    entry = doc.node(button).prop("cbcsEnabledWhen")
    assert entry is not None
    assert entry.stdset == "0"
    log.execute(SetLogic(button, "cbcsEnabledWhen", None))
    assert doc.root.prop("cbcsLogic") is None
    with pytest.raises(CommandRejected):
        log.execute(SetLogic(button, "cbcsSplitterSizes", "1,2"))
    log.execute(SetProperty(button, "cbcsSplitterSizes", StringValue("10,20"), stdset="0"))
    assert doc.node(button).prop("cbcsSplitterSizes") is not None
    log.execute(SetProperty(doc.root.id, "cbcsLogic", StringValue('{"version":9}'), stdset="0"))
    with pytest.raises(CommandRejected) as caught:
        log.execute(SetLogic(button, "cbcsEnabledWhen", "1"))
    assert caught.value.code == "FB402"


def test_illegal_xml_text_is_rejected() -> None:
    log = open_log(BOX)
    doc = log.document
    fingerprint = doc.fingerprint()
    with pytest.raises(CommandRejected):
        log.execute(SetProperty(nid(doc, "okButton"), "text", StringValue("\x00")))
    assert doc.fingerprint() == fingerprint
    assert not log.can_undo()


def test_stale_id_is_rejected() -> None:
    log = open_log(BOX)
    with pytest.raises(CommandRejected):
        log.execute(DeleteNodes((NodeId(10**9),)))
    assert not log.can_undo()
