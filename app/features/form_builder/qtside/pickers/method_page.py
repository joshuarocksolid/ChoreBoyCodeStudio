"""The method page (UX-CODE-002, UX-PICK-007).

The check line says what Enter will do. An error line does not add a method.
A name the class already has connects the event and adds no code.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

_STOCK: Dict[str, Tuple[str, ...]] = {}


def method_page(ctx: object, page: object) -> object:
    from app.features.form_builder.engine.logic.events import sender_node
    from app.features.form_builder.engine.logic.events_catalog import value_words
    from app.features.form_builder.engine.project.handler_names import suggest_method_name
    from app.features.form_builder.qtside.pickers.flow import Item, Page, _sender_chain, _sends

    chain = _sender_chain(ctx)
    class_name = chain[0] if chain else ""
    node = sender_node(ctx.doc, ctx.source.sender)  # type: ignore[attr-defined]
    text = ""
    if node is not None:
        from app.features.form_builder.engine.query.actions import text_of

        text = text_of(node)
    stock = _stock(ctx)
    taken = _taken(ctx)
    natural = suggest_method_name(
        class_name=class_name,
        object_name=ctx.source.sender,  # type: ignore[attr-defined]
        text=text,
        signal=page.signal,  # type: ignore[attr-defined]
        form_class=ctx.doc.form_class_name(),  # type: ignore[attr-defined]
        taken=(),
        inherited=stock,
    )
    if natural in set(taken):
        suggested = natural
    else:
        suggested = suggest_method_name(
            class_name=class_name,
            object_name=ctx.source.sender,  # type: ignore[attr-defined]
            text=text,
            signal=page.signal,  # type: ignore[attr-defined]
            form_class=ctx.doc.form_class_name(),  # type: ignore[attr-defined]
            taken=taken,
            inherited=stock,
        )
    sends = _sends(ctx, page.signal)  # type: ignore[attr-defined]
    receive = ""
    if _show_receive(ctx, sends, chain, page.signal):  # type: ignore[attr-defined]
        receive = "My method receives %s" % value_words(sends[0], page.signal, chain)  # type: ignore[attr-defined]
    notice = method_line(ctx, suggested, page.signal)  # type: ignore[attr-defined]
    read_line = str(getattr(ctx, "read_line", "") or "")
    if read_line or not ctx.window_file:  # type: ignore[attr-defined]
        sentence = read_line or notice
        return Page(
            "method", "Call a new method\u2026", "", 0,
            (Item("notice", "", sentence, header=True),),
            "", False, suggested, sentence, page.signal, "", "", page.wide, page.replace_index, "step",  # type: ignore[attr-defined]
        )
    rows = [Item("make", suggested, "Add %s()" % suggested)]
    rows.append(Item("notice", "", "METHODS IN %s" % ctx.window_file, header=True))  # type: ignore[attr-defined]
    used = _used_here(ctx, page.signal)  # type: ignore[attr-defined]
    from app.features.form_builder.qtside.pickers.flow import _other_event_method

    for info in _fitting(ctx, len(sends)):
        name = str(getattr(info, "name", info))
        if _other_event_method(ctx, name, str(page.signal)):  # type: ignore[attr-defined]
            continue
        note = "already here" if name in used else ""
        rows.append(Item("method", name, "%s()" % name, note=note, search=("%s already here" % name) if note else name))
    return Page(
        "method", "Call a new method\u2026", "", 0,
        tuple(rows),
        receive, False, suggested, notice, page.signal, "", "", page.wide, page.replace_index, "step",  # type: ignore[attr-defined]
    )


def method_notice(ctx: object, page: object, name: str) -> str:
    read_line = str(getattr(ctx, "read_line", "") or "")
    if read_line:
        return read_line
    return method_line(ctx, name, page.signal)  # type: ignore[attr-defined]


def method_blocks(sentence: str) -> bool:
    """True when Enter must not add the method."""
    return (
        sentence.startswith("Use a method name")
        or "would replace it" in sentence
        or sentence.startswith("Methods named on_")
        or sentence.startswith("This form isn't")
        or "can't be read" in sentence
        or "has no class that calls self.ui.setupUi" in sentence
    )


def method_line(ctx: object, name: str, signal: str = "") -> str:
    from app.features.form_builder.engine.logic import compat
    from app.features.form_builder.engine.logic.events import declared_methods

    del signal
    read_line = str(getattr(ctx, "read_line", "") or "")
    if read_line:
        return read_line
    if not compat.is_name(name):
        return "Use a method name like print_receipt: letters, digits and _, starting with a letter."
    if name.startswith("on_"):
        return "Methods named on_\u2026 also run by their name. Pick another name."
    stock = _stock(ctx)
    if name in stock:
        return "%s is a method of %s, so it would replace it. Try %s." % (name, _qt_base(ctx), _other_name(ctx, name, stock))
    klass = ctx.window_class or ctx.doc.form_class_name()  # type: ignore[attr-defined]
    if name in ctx.methods or name in declared_methods(ctx.doc):  # type: ignore[attr-defined]
        return "%s already has %s. This event will call it." % (klass, name)
    if not ctx.window_file:  # type: ignore[attr-defined]
        return "This form isn't in a project, so it has no window file."
    return "Adds %s() to %s in %s." % (name, klass, ctx.window_file)  # type: ignore[attr-defined]


def _taken(ctx: object) -> Tuple[str, ...]:
    names = list(ctx.taken or ctx.methods or ())  # type: ignore[attr-defined]
    return tuple(str(item) for item in names)


def _stock(ctx: object) -> Tuple[str, ...]:
    inherited = tuple(ctx.inherited or ())  # type: ignore[attr-defined]
    if inherited:
        return inherited
    return _dir_names(_qt_base(ctx))


def _dir_names(class_name: str) -> Tuple[str, ...]:
    if class_name in _STOCK:
        return _STOCK[class_name]
    from app.qt import QtCore, QtGui, QtWidgets

    for module in (QtWidgets, QtGui, QtCore):
        found = getattr(module, class_name, None)
        if isinstance(found, type):
            names = tuple(name for name in dir(found) if not name.startswith("_"))
            _STOCK[class_name] = names
            return names
    _STOCK[class_name] = ()
    return ()


def _qt_base(ctx: object) -> str:
    root = getattr(ctx.doc, "root", None)  # type: ignore[attr-defined]
    return str(getattr(root, "class_name", "") or "QWidget")


def _other_name(ctx: object, name: str, stock: Tuple[str, ...]) -> str:
    from app.features.form_builder.engine.logic.events import sender_node
    from app.features.form_builder.engine.project.handler_names import suggest_method_name
    from app.features.form_builder.engine.query.actions import text_of
    from app.features.form_builder.qtside.pickers.flow import _sender_chain

    chain = _sender_chain(ctx)
    node = sender_node(ctx.doc, ctx.source.sender)  # type: ignore[attr-defined]
    text = text_of(node) if node is not None else ""
    return suggest_method_name(
        class_name=chain[0] if chain else "",
        object_name=ctx.source.sender,  # type: ignore[attr-defined]
        text=text,
        signal="",
        form_class=ctx.doc.form_class_name(),  # type: ignore[attr-defined]
        taken=_taken(ctx) + (name,),
        inherited=stock,
    )


def _used_here(ctx: object, signal: str) -> Tuple[str, ...]:
    from app.features.form_builder.engine.logic.events import read_event

    state = read_event(ctx.doc, ctx.source.sender, signal)  # type: ignore[attr-defined]
    return tuple(step.method for step in state.steps if step.verb == "call" and step.method)


def _attr(obj: object, name: str) -> Any:
    return getattr(obj, name, None)


def _show_receive(ctx: object, sends: tuple, chain: tuple, signal: str) -> bool:
    """The receive line follows the value the chosen signal actually passes.

    A push button that is not checkable does not pass whether it is checked,
    even though ``clicked`` has a bool overload.
    """
    if not sends:
        return False
    if sends[0] != "bool":
        return True
    if signal == "clicked" and any(name in chain for name in ("QPushButton", "QToolButton")):
        from app.features.form_builder.engine.logic.events import sender_node

        node = sender_node(ctx.doc, ctx.source.sender)  # type: ignore[attr-defined]
        if node is None:
            return False
        value = node.value("checkable")
        return bool(getattr(value, "value", False))
    return True


def _fitting(ctx: object, sends: int) -> tuple:
    infos = _attr(ctx, "method_infos") or ()
    if isinstance(infos, (list, tuple)) and infos:
        kept = []
        for info in infos:
            name = str(_attr(info, "name") or "")
            if name.startswith("__"):
                continue
            params = _attr(info, "params") or ()
            if isinstance(params, (list, tuple)) and len(params) <= sends:
                kept.append(info)
        return tuple(kept)
    names = _attr(ctx, "methods") or ()
    if isinstance(names, (list, tuple)):
        return tuple(name for name in names if not str(name).startswith("__"))
    return ()
