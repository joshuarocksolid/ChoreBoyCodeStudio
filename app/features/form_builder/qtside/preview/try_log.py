"""Turn one burst of Try traces into the "What ran" lines.

A burst is everything that happened before the child returned to the event
loop: one rule refresh, one field leave, or one click. Rules in that burst
become a single "Rules ran (N)" line. A step that returned early becomes the
stopped sentence. The widget only paints these lines.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from app.features.form_builder.engine.ipc.protocol import SourceRef
from app.features.form_builder.engine.logic.events_catalog import event_words
from app.features.form_builder.engine.logic.storage import signal_property

_STEP_TRACE = re.compile(
    r"""self\._cbcs_trace\(\s*["']step["']\s*,\s*(['"])(?P<ref>.*?)\1"""
)


@dataclass(frozen=True)
class TryEvent:
    """One thing the stand-in observed. ``value`` is the trace payload."""

    kind: str
    ref: str = ""
    value: object = None
    method: str = ""


@dataclass(frozen=True)
class TryLine:
    """One row of "What ran". ``ref`` is the raw source key. ``details`` lists a grouped burst."""

    sentence: str
    ref: str
    source: SourceRef
    kind: str
    method: str = ""
    details: Tuple[str, ...] = ()


def step_counts(source: str) -> Dict[str, int]:
    """How many step traces each handler emits. Fewer at run time means the list stopped."""
    counts: Dict[str, int] = {}
    for match in _STEP_TRACE.finditer(source or ""):
        ref = match.group("ref")
        counts[ref] = counts.get(ref, 0) + 1
    return counts


def handler_ref(source: str, name: str) -> str:
    """The source reference inside ``def name``, or ``name`` when the handler has none."""
    marker = "def %s(" % name
    start = (source or "").find(marker)
    if start < 0:
        return name
    nxt = source.find("\n    def ", start + len(marker))
    body = source[start:] if nxt < 0 else source[start:nxt]
    match = _STEP_TRACE.search(body)
    if match is None:
        return name
    return match.group("ref")


_RULE_WORDS = {
    "cbcsEnabledWhen": "Enabled when",
    "cbcsVisibleWhen": "Visible when",
    "cbcsReadOnlyWhen": "Read-only when",
    "cbcsValue": "Value",
    "cbcsDefault": "Default",
    "cbcsValidate": "Checks",
}


def names_from_env(env: object) -> Tuple[Tuple[str, str], ...]:
    """Object name to FormulaEnv's display. A display equal to the object name is left out."""
    widgets = getattr(env, "widgets", None) or {}
    found = []
    for name, facts in widgets.items():
        display = getattr(facts, "display", "") or ""
        if not isinstance(display, str):
            continue
        display = display.replace("&", "")
        if display and display != name:
            found.append((str(name), display))
    found.sort()
    return tuple(found)


def names_for(doc: object) -> Tuple[Tuple[str, str], ...]:
    """Object name to the words the inspector says.

    That is ``spoken_display``: a caption or buddy when the form has one, and
    the split object name otherwise ("lineTotalLabel" becomes "Line total").
    Generated code keeps the object name. A name that already reads as itself
    is left out.
    """
    from app.features.form_builder.engine.logic.read_as_text import spoken_display
    from app.features.form_builder.engine.ui4.document import UiDocument

    if not isinstance(doc, UiDocument):
        return ()
    found = []
    for node in doc.iter_widgets():
        name = node.object_name or ""
        if not name:
            continue
        shown = spoken_display(doc, name).replace("&", "")
        if shown and shown != name:
            found.append((name, shown))
    found.sort()
    return tuple(found)


def source_label(ref: str, names: Optional[Mapping[str, str]] = None) -> str:
    """The Source column words. The raw key stays on the line for the tooltip and Copy."""
    text = ref or ""
    if ": When " in text:
        widget, _, signal = text.partition(": When ")
        return "%s · When %s" % (_widget_name(widget, names), signal.strip())
    widget, sep, key = text.partition(":")
    if not sep:
        return text
    words = _RULE_WORDS.get(key.strip(), key.strip())
    if not widget.strip():
        return words
    return "%s · %s" % (_widget_name(widget, names), words)


def _widget_name(widget: str, names: Optional[Mapping[str, str]]) -> str:
    text = widget.strip()
    if not text or not names:
        return text
    shown = names.get(text, "")
    if isinstance(shown, str) and shown:
        return shown
    return text


def source_of(ref: str, step_index: Optional[int] = None) -> SourceRef:
    """The editor address of a trace reference."""
    text = ref or ""
    if ": When " in text:
        widget, _, signal = text.partition(": When ")
        path: List[object] = [signal_property(signal.strip())]
        if step_index is not None:
            path.append(step_index)
        return SourceRef(object_name=widget.strip() or None, rule_path=tuple(path))
    widget, _, key = text.partition(":")
    if key:
        return SourceRef(object_name=widget.strip() or None, rule_path=(key.strip(),))
    return SourceRef(object_name=widget.strip() or None, rule_path=())


def fold(
    events: Sequence[TryEvent],
    counts: Mapping[str, int],
    labels: Mapping[str, str],
    names: Optional[Mapping[str, str]] = None,
) -> Tuple[TryLine, ...]:
    """The lines for one burst, in the order a person should read them.

    ``names`` is the FormulaEnv display map. It wins over ``labels``, which used
    to be widget text read off the form.
    """
    labels = _naming(labels, names)
    errors = [item for item in events if item.kind == "error"]
    if errors:
        item = errors[0]
        ref = item.ref
        return (
            TryLine(
                sentence=_one_line(str(item.value or "")),
                ref=ref,
                source=source_of(ref),
                kind="step",
            ),
        )
    rules = [item for item in events if item.kind == "rule"]
    # A burst can refresh several times; each rule is named once.
    rule_refs = tuple(dict.fromkeys(item.ref for item in rules))
    lines: List[TryLine] = []
    rules_written = False
    steps: Dict[str, List[TryEvent]] = {}
    for item in events:
        if item.kind == "rule":
            if not rules_written and rules:
                first = rules[0]
                lines.append(
                    TryLine(
                        sentence="Rules ran (%d)" % len(rule_refs),
                        ref=first.ref,
                        source=source_of(first.ref),
                        kind="rule",
                        details=rule_refs,
                    )
                )
                rules_written = True
            continue
        if item.kind == "check":
            message = item.value if isinstance(item.value, str) else ""
            if not message:
                continue
            widget = _widget_name(item.ref.split(":", 1)[0], labels)
            lines.append(
                TryLine(
                    sentence="Check %s: %s" % (widget, message),
                    ref=item.ref,
                    source=source_of(item.ref),
                    kind="check",
                )
            )
            continue
        if item.kind == "would_call":
            lines.append(
                TryLine(
                    sentence="Would call %s()" % item.method,
                    ref=item.method,
                    source=SourceRef(rule_path=(item.method,)),
                    kind="would_call",
                    method=item.method,
                )
            )
            continue
        if item.kind == "needs_value":
            lines.append(
                TryLine(
                    sentence="%s() needs a window value" % item.method,
                    ref=item.method,
                    source=SourceRef(rule_path=(item.method,)),
                    kind="needs_value",
                    method=item.method,
                )
            )
            continue
        if item.kind == "step":
            steps.setdefault(item.ref, []).append(item)
    for ref, group in steps.items():
        expected = counts.get(ref, len(group))
        words = group[-1].value if isinstance(group[-1].value, str) else ""
        if len(group) < expected and "stops here" in words:
            lines.append(_stopped(ref, words, len(group), labels))
    return tuple(lines)


def _naming(
    labels: Mapping[str, str],
    names: Optional[Mapping[str, str]],
) -> Dict[str, str]:
    found: Dict[str, str] = {}
    if labels:
        found.update(labels)
    if names:
        for key, value in names.items():
            if value:
                found[str(key)] = value
    return found


def _stopped(ref: str, words: str, number: int, labels: Mapping[str, str]) -> TryLine:
    widget, _, signal = ref.partition(": When ")
    display = labels.get(widget.strip()) or widget.strip() or "The form"
    clause = _clause(signal.strip(), display)
    short = words.split(" (", 1)[0] or words
    sentence = "%s: stopped at step %d (%s)" % (clause, number, short)
    return TryLine(
        sentence=sentence,
        ref=ref,
        source=source_of(ref, number - 1),
        kind="step",
    )


def _clause(signal: str, display: str) -> str:
    if not signal:
        return display
    words = event_words(signal)
    try:
        return words.clause.format(display=display, signal=signal)
    except (KeyError, IndexError, ValueError):
        return "%s is %s" % (display, signal)


def _one_line(text: str) -> str:
    return " ".join(text.split())
