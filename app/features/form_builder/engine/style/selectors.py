"""Selectors of a style sheet and the widgets they match (UX-STYLE-005). Qt-free.

``parse_selectors`` reads the text before a ``{``. ``StyleIndex`` is built once
per document revision and answers which widgets a selector reaches; it follows
Qt's cascade: a rule in a widget's own sheet reaches that widget and its
descendants only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.style.sheet import Sheet
from app.features.form_builder.engine.style.tokenizer import COMMENT, DELIM, HASH, IDENT, WS, tokenize
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.style.classes import effective_class, widget_chain
from app.features.form_builder.engine.style.properties import is_known_state
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import (
    BoolValue,
    CStringValue,
    EnumValue,
    NumberValue,
    StringValue,
    Value,
)

DESCENDANT = " "
CHILD = ">"

#: Pseudo-state to the words the match chip adds ("3 widgets · when hovered").
STATE_WORDS: Dict[str, str] = {
    "hover": "hovered",
    "pressed": "pressed",
    "checked": "checked",
    "unchecked": "not checked",
    "disabled": "disabled",
    "enabled": "enabled",
    "focus": "focused",
    "selected": "selected",
    "open": "open",
    "closed": "closed",
    "on": "on",
    "off": "off",
    "editable": "editable",
    "read-only": "read only",
    "active": "active",
    "window": "in a window",
    "default": "the default",
    "flat": "flat",
    "indeterminate": "partly checked",
}


@dataclass(frozen=True)
class AttrTest:
    name: str
    op: str
    value: str


@dataclass(frozen=True)
class Compound:
    type_name: str = ""
    classes: Tuple[str, ...] = ()
    ident: str = ""
    attrs: Tuple[AttrTest, ...] = ()
    #: ``("hover", "!pressed")``
    states: Tuple[str, ...] = ()
    subcontrol: str = ""


@dataclass(frozen=True)
class Selector:
    parts: Tuple[Compound, ...]
    combinators: Tuple[str, ...]
    text: str
    #: False for text the matcher cannot place (an empty selector, ``+``, ``~``).
    valid: bool = True

    def state_words(self) -> Tuple[str, ...]:
        words: List[str] = []
        for compound in self.parts[-1:]:
            for state in compound.states:
                negated = state.startswith("!")
                word = STATE_WORDS.get(state.lstrip("!"), state.lstrip("!"))
                words.append(("not " + word) if negated else word)
        return tuple(words)


def parse_selectors(text: str) -> Tuple[Selector, ...]:
    """One ``Selector`` for each comma-separated group of ``text``."""
    tokens, _problems = tokenize(text)
    groups: List[List] = [[]]
    depth = 0
    for token in tokens:
        if token.kind == DELIM and token.text in "[(":
            depth += 1
        elif token.kind == DELIM and token.text in "])":
            depth = max(0, depth - 1)
        if token.kind == DELIM and token.text == "," and depth == 0:
            groups.append([])
            continue
        if token.kind != COMMENT:
            groups[-1].append(token)
    return tuple(_selector(group, text) for group in groups)


def _selector(tokens: List, whole: str) -> Selector:
    while tokens and tokens[0].kind == WS:
        tokens.pop(0)
    while tokens and tokens[-1].kind == WS:
        tokens.pop()
    shown = whole[tokens[0].start : tokens[-1].end] if tokens else ""
    if not tokens:
        return Selector((), (), "", False)
    parts: List[Compound] = []
    combinators: List[str] = []
    valid = True
    type_name = ""
    classes: List[str] = []
    ident = ""
    attrs: List[AttrTest] = []
    states: List[str] = []
    subcontrol = ""
    started = False
    pending = ""
    index = 0
    count = len(tokens)

    def close() -> None:
        nonlocal type_name, classes, ident, attrs, states, subcontrol, started
        parts.append(Compound(type_name, tuple(classes), ident, tuple(attrs), tuple(states), subcontrol))
        type_name, classes, ident, attrs, states, subcontrol, started = "", [], "", [], [], "", False

    while index < count:
        token = tokens[index]
        if token.kind == WS:
            if started:
                close()
                pending = DESCENDANT
            index += 1
            continue
        if token.kind == DELIM and token.text in ">+~":
            if started:
                close()
            elif not parts:
                valid = False
            if token.text != ">":
                valid = False
            pending = CHILD if token.text == ">" else token.text
            index += 1
            continue
        if pending and not started and parts:
            combinators.append(pending)
            pending = ""
        started = True
        if token.kind == IDENT and not type_name and not classes and not ident and not attrs and not states:
            type_name = token.text
        elif token.kind == DELIM and token.text == "*" and not type_name:
            type_name = "*"
        elif token.kind == HASH:
            ident = token.text[1:]
        elif token.kind == DELIM and token.text == "." and index + 1 < count and tokens[index + 1].kind == IDENT:
            classes.append(tokens[index + 1].text)
            index += 1
        elif token.kind == DELIM and token.text == "[":
            end = index + 1
            while end < count and not (tokens[end].kind == DELIM and tokens[end].text == "]"):
                end += 1
            attrs.append(_attribute(tokens[index + 1 : end]))
            index = end
        elif token.kind == DELIM and token.text == ":":
            double = index + 1 < count and tokens[index + 1].kind == DELIM and tokens[index + 1].text == ":"
            if double:
                index += 1
            negate = index + 1 < count and tokens[index + 1].kind == DELIM and tokens[index + 1].text == "!"
            if negate:
                index += 1
            if index + 1 < count and tokens[index + 1].kind == IDENT:
                word = tokens[index + 1].text
                if double:
                    subcontrol = word
                else:
                    states.append(("!" if negate else "") + word.lower())
                index += 1
            else:
                valid = False
        else:
            valid = False
        index += 1
    if started:
        close()
    elif pending:
        valid = False
    return Selector(tuple(parts), tuple(combinators), shown, valid and bool(parts))


def _attribute(tokens: Sequence) -> AttrTest:
    inner = [token for token in tokens if token.kind != WS]
    if not inner:
        return AttrTest("", "", "")
    name = inner[0].text
    if len(inner) == 1:
        return AttrTest(name, "", "")
    op_parts: List[str] = []
    position = 1
    while position < len(inner) and inner[position].kind == DELIM:
        op_parts.append(inner[position].text)
        position += 1
    value_text = "".join(token.text for token in inner[position:])
    if len(value_text) >= 2 and value_text[0] in "\"'" and value_text[-1] == value_text[0]:
        value_text = value_text[1:-1]
    return AttrTest(name, "".join(op_parts), value_text)


@dataclass(frozen=True)
class RuleMatch:
    """The widgets one rule reaches. ``rule`` indexes ``Sheet.rules``; -1 is the ``*`` Qt wraps around bare declarations."""

    rule: int
    selector: str
    ids: Tuple[NodeId, ...]
    states: Tuple[str, ...] = ()
    valid: bool = True

    @property
    def count(self) -> int:
        return len(self.ids)


@dataclass
class _Facts:
    node: WidgetNode
    name: str
    chain: FrozenSet[str]
    parent: Optional[NodeId]
    effective: str


class StyleIndex:
    """Class chain, name and parent of every widget of a document, built once."""

    def __init__(self, document: UiDocument, table: Optional[QtClassTable] = None) -> None:
        self.document = document
        table = table if table is not None else QtClassTable.shared()
        self._table = table
        self.facts: Dict[NodeId, _Facts] = {}
        self.order: List[NodeId] = []
        self.by_name: Dict[str, List[NodeId]] = {}
        self.by_class: Dict[str, List[NodeId]] = {}
        self.children: Dict[NodeId, List[NodeId]] = {}
        for node in document.iter_widgets():
            parent = self._widget_parent(node)
            chain, effective = self._chain(node)
            self.facts[node.id] = _Facts(node, node.object_name, chain, parent, effective)
            self.order.append(node.id)
            if node.object_name:
                self.by_name.setdefault(node.object_name, []).append(node.id)
            for class_name in chain:
                self.by_class.setdefault(class_name, []).append(node.id)
            if parent is not None:
                self.children.setdefault(parent, []).append(node.id)

    def _widget_parent(self, node: WidgetNode) -> Optional[NodeId]:
        for ancestor in self.document.ancestors(node.id):
            found = self.document.node(ancestor)
            if isinstance(found, WidgetNode):
                return found.id
        return None

    def _chain(self, node: WidgetNode) -> Tuple[FrozenSet[str], str]:
        chain = widget_chain(self.document, node, self._table)
        return frozenset(chain), effective_class(chain)

    def subtree(self, owner: NodeId) -> List[NodeId]:
        found: List[NodeId] = []
        stack = [owner]
        while stack:
            current = stack.pop()
            if current in self.facts:
                found.append(current)
            stack.extend(reversed(self.children.get(current, ())))
        return found

    def attribute_text(self, node_id: NodeId, name: str) -> Optional[str]:
        facts = self.facts[node_id]
        entry = facts.node.prop(name)
        value: Optional[Value] = entry.value if entry is not None else None
        if value is None:
            info = self._table.property_info(facts.effective, name)
            value = info.default if info is not None else None
        return _value_text(value)

    def matches(self, selector: Selector, node_id: NodeId) -> bool:
        if not selector.valid:
            return False
        return self._match_from(selector, len(selector.parts) - 1, node_id)

    def _match_from(self, selector: Selector, position: int, node_id: NodeId) -> bool:
        if not self._compound(selector.parts[position], node_id):
            return False
        if position == 0:
            return True
        combinator = selector.combinators[position - 1] if position - 1 < len(selector.combinators) else DESCENDANT
        parent = self.facts[node_id].parent
        if combinator == CHILD:
            return parent is not None and self._match_from(selector, position - 1, parent)
        if combinator != DESCENDANT:
            return False
        while parent is not None:
            if self._match_from(selector, position - 1, parent):
                return True
            parent = self.facts[parent].parent
        return False

    def _compound(self, compound: Compound, node_id: NodeId) -> bool:
        facts = self.facts[node_id]
        if compound.type_name and compound.type_name != "*" and compound.type_name not in facts.chain:
            return False
        for class_name in compound.classes:
            if facts.node.class_name != class_name:
                return False
        if compound.ident and compound.ident != facts.name:
            return False
        for test in compound.attrs:
            if not self._attr(test, node_id):
                return False
        # Qt matches a state it doesn't know never, negated or not.
        return all(is_known_state(state) for state in compound.states)

    def _attr(self, test: AttrTest, node_id: NodeId) -> bool:
        actual = self.attribute_text(node_id, test.name)
        if actual is None:
            return False
        if not test.op:
            return True
        if test.op == "=":
            return actual == test.value
        if test.op == "~=":
            return test.value in actual.split()
        if test.op == "|=":
            return actual == test.value or actual.startswith(test.value + "-")
        if test.op == "^=":
            return actual.startswith(test.value)
        if test.op == "$=":
            return actual.endswith(test.value)
        if test.op == "*=":
            return test.value in actual
        return False

    def candidates(self, selector: Selector, pool: Set[NodeId]) -> Iterable[NodeId]:
        """Widgets of ``pool`` the last compound could match, found by name or class first."""
        last = selector.parts[-1]
        if last.ident:
            return [node_id for node_id in self.by_name.get(last.ident, ()) if node_id in pool]
        if last.type_name and last.type_name != "*":
            return [node_id for node_id in self.by_class.get(last.type_name, ()) if node_id in pool]
        return [node_id for node_id in self.order if node_id in pool]


def match_sheet(index: StyleIndex, owner: NodeId, sheet: Sheet) -> Tuple[RuleMatch, ...]:
    """Per rule, the widgets of ``owner``'s subtree it reaches, in document order."""
    if owner not in index.facts:
        return ()
    subtree = index.subtree(owner)
    pool = set(subtree)
    rank = {node_id: position for position, node_id in enumerate(index.order)}
    found: List[RuleMatch] = []
    if sheet.declarations and not sheet.rules:
        found.append(RuleMatch(-1, "*", tuple(sorted(subtree, key=rank.__getitem__)), (), True))
        return tuple(found)
    for position, rule in enumerate(sheet.rules):
        selectors = parse_selectors(rule.selector)
        reached: Set[NodeId] = set()
        words: List[str] = []
        valid = any(selector.valid for selector in selectors)
        for selector in selectors:
            if not selector.valid:
                continue
            for word in selector.state_words():
                if word not in words:
                    words.append(word)
            for node_id in index.candidates(selector, pool):
                if node_id not in reached and index.matches(selector, node_id):
                    reached.add(node_id)
        found.append(
            RuleMatch(position, rule.selector, tuple(sorted(reached, key=rank.__getitem__)), tuple(words), valid)
        )
    return tuple(found)


def _value_text(value: Optional[Value]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (StringValue, CStringValue)):
        return value.text
    if isinstance(value, BoolValue):
        return "true" if value.value else "false"
    if isinstance(value, EnumValue):
        return value.key()[1]
    if isinstance(value, NumberValue):
        return str(value.value)
    plain = getattr(value, "value", None)
    if isinstance(plain, (int, float, str)):
        return str(plain)
    return None
