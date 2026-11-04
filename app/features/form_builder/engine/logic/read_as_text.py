"""The form's behavior as numbered English sentences. No Qt."""

from __future__ import annotations

import re
import weakref
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.logic.checks import (
    FormulaCheck,
    Length,
    OneOf,
    Pattern,
    Preset,
    Range,
    Required,
    Unique,
    read_checks,
)
from app.features.form_builder.engine.logic.events import read_events
from app.features.form_builder.engine.logic.events_catalog import class_chain, event_clause, step_words
from app.features.form_builder.engine.logic.formula.env import FormulaEnv
from app.features.form_builder.engine.logic.formula.speak import speak_text
from app.features.form_builder.engine.logic.formula_env import env_for
from app.features.form_builder.engine.logic.storage import FORMULA_KEYS
from app.features.form_builder.engine.query.tab_stops import buddy_of, caption, display_name, form_row_pairs
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import CStringValue, StringValue

_SUFFIXES = ("Label", "Spin", "Edit", "Button", "Check", "Combo", "Box", "View", "Widget")
_WRAPS = {
    "cbcsEnabledWhen": "%s is enabled only when %s.",
    "cbcsVisibleWhen": "%s is visible only when %s.",
    "cbcsReadOnlyWhen": "%s is read-only when %s.",
    "cbcsValue": "%s is always %s.",
    "cbcsDefault": "%s starts as %s.",
}
_KINDS = {
    "cbcsEnabledWhen": "condition",
    "cbcsVisibleWhen": "condition",
    "cbcsReadOnlyWhen": "condition",
    "cbcsValue": "value",
    "cbcsDefault": "value",
}


@dataclass(frozen=True)
class Sentence:
    number: int
    section: str
    text: str


# One page per live document. The revision sits in the value, so a freed
# document cannot leave its names for the next object that reuses the address.
_PREFERRED: "weakref.WeakKeyDictionary[UiDocument, Tuple[int, Dict[str, Tuple[str, bool]]]]" = (
    weakref.WeakKeyDictionary()
)


def widget_name(doc: Optional[UiDocument], name: str, env: object = None) -> str:
    """The name the Logic panel row shows for one widget.

    What ran uses this same function. A caption or buddy wins. A humanized
    object name is used when the form has neither. FormulaEnv's display is
    only the fallback when the document has no spoken name.
    """
    if isinstance(doc, UiDocument):
        shown = spoken_display(doc, name).replace("&", "")
        if shown:
            return shown
    widgets = getattr(env, "widgets", None) or {}
    facts = widgets.get(name) if hasattr(widgets, "get") else None
    display = getattr(facts, "display", "") if facts is not None else ""
    if isinstance(display, str) and display and display != name:
        return display.replace("&", "")
    return name


def spoken_display(doc: UiDocument, name: str) -> str:
    """The name a sentence uses. A fallback that collides becomes the split object name."""
    preferred = _preferred(doc)
    mine, mine_fallback = preferred.get(name, (_humanize(name), True))
    folded = mine.casefold()
    taken = {text.casefold() for key, (text, _flag) in preferred.items() if key != name}
    if mine_fallback and folded in taken:
        return _split_name(name)
    return mine


def _preferred(doc: UiDocument) -> Dict[str, Tuple[str, bool]]:
    """Object name to (spoken, fallback). Fallback is the humanized object name.

    Spoken names come from captions and the tree, not from formula text, so a
    rule commit (revision moves, structure does not) hits.
    """
    revision = getattr(doc, "structure_revision", None)
    face = getattr(doc, "face_revision", None)
    stamp = (revision, face)
    cached = _PREFERRED.get(doc) if isinstance(revision, int) and isinstance(face, int) else None
    if cached is not None and cached[0] == stamp:
        return cached[1]
    patched = _patch_preferred(doc, cached, revision, face)
    if patched is not None:
        _PREFERRED[doc] = (stamp, patched)
        return patched
    doc._reset_added_widgets()
    captions: Dict[str, str] = {}
    for label_id, field in form_row_pairs(doc):
        if field in captions:
            continue
        text = caption(doc, label_id)
        label = doc.get(label_id)
        own = label.object_name if isinstance(label, WidgetNode) else ""
        if text and text != own:
            captions[field] = text
    found: Dict[str, Tuple[str, bool]] = {}
    for node in doc.iter_preorder():
        if not isinstance(node, WidgetNode) or not node.object_name:
            continue
        name = node.object_name
        shown = display_name(doc, name)
        if shown and shown != name:
            found[name] = (shown, False)
        elif name in captions:
            found[name] = (captions[name], False)
        else:
            found[name] = (_humanize(name), True)
    if isinstance(revision, int) and isinstance(face, int):
        _PREFERRED[doc] = (stamp, found)
    return found


def _patch_preferred(
    doc: UiDocument,
    cached: Optional[Tuple[object, Dict[str, Tuple[str, bool]]]],
    revision: object,
    face: object,
) -> Optional[Dict[str, Tuple[str, bool]]]:
    """One label text edit rewrites the names that show that caption."""
    if cached is None or not isinstance(revision, int) or not isinstance(face, int):
        return None
    old = cached[0]
    if not isinstance(old, tuple) or len(old) < 2:
        return None
    if old[0] != revision:
        if not isinstance(old[0], int):
            return None
        added = doc.added_widgets_since(old[0])
        if not added:
            return None
        return _patch_added_spoken(doc, dict(cached[1]), added)
    edits = [
        edit
        for edit in getattr(doc, "_face_edits", ())
        if isinstance(old[1], int) and edit[0] > old[1]
    ]
    if len(edits) != 1 or edits[0][2] != "text":
        return None
    node = doc.get(edits[0][1])
    if not isinstance(node, WidgetNode) or not node.object_name:
        return None
    found = dict(cached[1])
    names = [node.object_name]
    target = buddy_of(doc, node.id)
    if target and target not in names:
        names.append(target)
    for label_id, field in form_row_pairs(doc):
        if label_id == node.id and field not in names:
            names.append(field)
            break
    for name in names:
        _put_spoken(doc, found, name)
    return found


def _patch_added_spoken(
    doc: UiDocument,
    found: Dict[str, Tuple[str, bool]],
    added: Tuple[object, ...],
) -> Dict[str, Tuple[str, bool]]:
    """One inserted widget keeps the names already spoken. A new caption wins only when it is first."""
    for node_id in added:
        node = doc.get(node_id)  # type: ignore[arg-type]
        if not isinstance(node, WidgetNode) or not node.object_name:
            continue
        name = node.object_name
        text = caption(doc, node.id)
        shown = text if text and text != name else ""
        buddy = buddy_of(doc, node.id)
        if buddy and shown:
            current = found.get(buddy)
            if current is None or current[0] != shown:
                source = ""
                for label_id, field in form_row_pairs(doc):
                    if field == buddy:
                        label = doc.get(label_id)
                        source = label.object_name if isinstance(label, WidgetNode) else ""
                        break
                if _label_before(doc, name, source):
                    found[buddy] = (shown, False)
        if shown:
            found[name] = (shown, False)
        else:
            found[name] = (_humanize(name), True)
    return found


def _label_before(doc: UiDocument, name: str, other: str) -> bool:
    if not other or other == name:
        return True
    for node in doc.iter_preorder():
        if not isinstance(node, WidgetNode):
            continue
        if node.object_name == name:
            return True
        if node.object_name == other:
            return False
    return True


def _put_spoken(doc: UiDocument, found: Dict[str, Tuple[str, bool]], name: str) -> None:
    shown = display_name(doc, name)
    if shown and shown != name:
        found[name] = (shown, False)
        return
    for label_id, field in form_row_pairs(doc):
        if field != name:
            continue
        text = caption(doc, label_id)
        label = doc.get(label_id)
        own = label.object_name if isinstance(label, WidgetNode) else ""
        if text and text != own:
            found[name] = (text, False)
            return
        break
    found[name] = (_humanize(name), True)


def _split_name(name: str) -> str:
    parts = re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", name)
    if not parts:
        return name
    return " ".join(part.lower() for part in parts)


def behavior_text(doc: UiDocument, env: Optional[FormulaEnv] = None) -> Tuple[Sentence, ...]:
    """STATE, then CHECKS, then EVENTS. Empty sections are left out. Numbers run through."""
    base = env if env is not None else env_for(doc, None, QtClassTable.shared())
    spoken = _speaking(doc, base)
    displays = {name: spoken_display(doc, name) for name in spoken.widgets}
    pending: List[Tuple[str, str]] = []
    pending.extend(_state(doc, spoken, displays))
    pending.extend(_checks(doc, displays))
    pending.extend(_events(doc, spoken, displays))
    return tuple(
        Sentence(index, section, text) for index, (section, text) in enumerate(pending, start=1)
    )


def page_text(sentences: Sequence[Sentence]) -> str:
    """The copy and print text. Section titles, a blank line, then ``N. text``."""
    lines: List[str] = []
    last = ""
    for sentence in sentences:
        if sentence.section != last:
            if lines:
                lines.append("")
            lines.append(sentence.section)
            lines.append("")
            last = sentence.section
        lines.append("%d. %s" % (sentence.number, sentence.text))
    return "\n".join(lines)


def _speaking(doc: UiDocument, env: FormulaEnv) -> FormulaEnv:
    widgets = {}
    for name, facts in env.widgets.items():
        widgets[name] = replace(facts, display=spoken_display(doc, name))
    return replace(env, widgets=widgets)


def _humanize(name: str) -> str:
    text = name
    for suffix in _SUFFIXES:
        if text.endswith(suffix) and len(text) > len(suffix):
            text = text[: -len(suffix)]
            break
    parts = re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", text)
    if not parts:
        return name
    words = [parts[0][:1].upper() + parts[0][1:].lower()]
    words.extend(part.lower() for part in parts[1:])
    return " ".join(words)


def _stored(node: object, key: str) -> Optional[str]:
    try:
        value = node.value(key)  # type: ignore[attr-defined]
    except Exception:
        return None
    if isinstance(value, (StringValue, CStringValue)):
        return value.text
    return None


def _speak_formula(text: str, env: FormulaEnv, kind: str) -> str:
    return speak_text(text, env, kind)


def _state(doc: UiDocument, env: FormulaEnv, displays: Dict[str, str]) -> List[Tuple[str, str]]:
    found: List[Tuple[str, str]] = []
    for node in doc.iter_preorder():
        if not isinstance(node, WidgetNode) or not node.object_name:
            continue
        display = displays.get(node.object_name, node.object_name)
        for key in FORMULA_KEYS:
            text = _stored(node, key)
            if text is None or not text.strip():
                continue
            spoken = _speak_formula(text, env, _KINDS.get(key, "value"))
            template = _WRAPS.get(key)
            if spoken and template is not None:
                sentence = template % (display, spoken)
            else:
                sentence = "%s is calculated as `%s`." % (display, text.strip())
            found.append(("STATE", sentence))
    return found


def _checks(doc: UiDocument, displays: Dict[str, str]) -> List[Tuple[str, str]]:
    found: List[Tuple[str, str]] = []
    for node in doc.iter_preorder():
        if not isinstance(node, WidgetNode) or not node.object_name:
            continue
        text = _stored(node, "cbcsValidate")
        if text is None or not text.strip():
            continue
        read = read_checks(text)
        display = displays.get(node.object_name, node.object_name)
        for check in read.checks:
            found.append(("CHECKS", _check_sentence(display, check)))
    return found


def _check_sentence(display: str, check: object) -> str:
    message = str(getattr(check, "message", "") or "").strip()
    if isinstance(check, Required):
        sentence = "%s is required." % display
    elif isinstance(check, Preset):
        sentence = "%s must be a valid %s." % (display, check.name)
    elif isinstance(check, Range):
        sentence = "%s must be in range." % display
    elif isinstance(check, Length):
        sentence = "%s must be the right length." % display
    elif isinstance(check, Pattern):
        sentence = "%s must match the pattern." % display
    elif isinstance(check, OneOf):
        sentence = "%s must be one of the allowed values." % display
    elif isinstance(check, FormulaCheck):
        sentence = "%s must pass its check." % display
    elif isinstance(check, Unique):
        sentence = "%s must be unique." % display
    else:
        sentence = "%s must pass its check." % display
    if not message:
        return sentence
    if not message.endswith("."):
        message = "%s." % message
    return "%s %s" % (sentence, message)


def _events(doc: UiDocument, env: FormulaEnv, displays: Dict[str, str]) -> List[Tuple[str, str]]:
    found: List[Tuple[str, str]] = []
    classes = QtClassTable.shared()
    for state in read_events(doc):
        display = displays.get(state.sender, state.sender)
        chain = _chain(doc, state.sender, classes)
        clause = event_clause(state.signal_name, chain, display)
        parts: List[str] = []
        for step in state.steps:
            target = step.target or doc.root.object_name
            named = displays.get(target, target)
            words = step_words(
                step,
                named,
                is_form=target == doc.root.object_name,
                target_chain=_chain(doc, target, classes),
            )
            piece = _mid_sentence(words)
            if step.when and step.when.strip():
                spoken = _speak_formula(step.when, env, "condition")
                extra = spoken if spoken else "`%s`" % step.when.strip()
                piece = "%s, only if %s" % (piece, extra)
            parts.append(piece)
        if not parts:
            continue
        found.append(("EVENTS", "When %s, %s." % (clause, _join_steps(parts))))
    return found


def _mid_sentence(words: str) -> str:
    """Step words sit after 'When …,'. The first letter drops, and so does an empty call."""
    text = words.strip()
    if text.endswith("()"):
        text = text[:-2].rstrip()
    if not text:
        return ""
    return text[0].lower() + text[1:]


def _join_steps(parts: Sequence[str]) -> str:
    if len(parts) == 1:
        return parts[0]
    return "%s, then %s" % (", ".join(parts[:-1]), parts[-1])


def _chain(doc: UiDocument, name: str, classes: QtClassTable) -> Tuple[str, ...]:
    found = doc.by_name(name)
    node = doc.get(found[0]) if found else None
    class_name = str(getattr(node, "class_name", "") or "").rsplit(".", 1)[-1]
    if not class_name:
        return ()
    return class_chain(classes, class_name)


__all__ = ["Sentence", "behavior_text", "page_text", "spoken_display"]
