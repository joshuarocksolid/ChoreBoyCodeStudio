"""The method page shell. M6.2b fills in the code behind a new method.

Until then, "Call a new method…" does not add a call unless the form has a
window file, and the page never claims it will add a method to a file that
does not exist.
"""

from __future__ import annotations


def method_page(ctx: object, page: object) -> object:
    from app.features.form_builder.engine.project.handler_names import suggest_method_name
    from app.features.form_builder.engine.logic.events import sender_node
    from app.features.form_builder.engine.logic.events_catalog import value_words
    from app.features.form_builder.qtside.pickers.flow import Item, Page, _sender_chain, _sends

    chain = _sender_chain(ctx)
    class_name = chain[0] if chain else ""
    node = sender_node(ctx.doc, ctx.source.sender)  # type: ignore[attr-defined]
    text = ""
    if node is not None:
        from app.features.form_builder.engine.query.actions import text_of

        text = text_of(node)
    suggested = suggest_method_name(
        class_name=class_name,
        object_name=ctx.source.sender,  # type: ignore[attr-defined]
        text=text,
        signal=page.signal,  # type: ignore[attr-defined]
        form_class=ctx.doc.form_class_name(),  # type: ignore[attr-defined]
        taken=ctx.taken or ctx.methods,  # type: ignore[attr-defined]
        inherited=ctx.inherited,  # type: ignore[attr-defined]
    )
    sends = _sends(ctx, page.signal)  # type: ignore[attr-defined]
    check = ""
    if sends:
        check = "My method receives %s" % value_words(sends[0], page.signal, chain)  # type: ignore[attr-defined]
    notice = method_line(ctx, suggested)
    return Page(
        "method", "Call a new method\u2026", "", 0,
        (Item("make", suggested, "Add %s()" % suggested),),
        check, False, suggested, notice, page.signal, "", "", page.wide, page.replace_index, "step",  # type: ignore[attr-defined]
    )


def method_notice(ctx: object, page: object, name: str) -> str:
    return method_line(ctx, name, page.signal)  # type: ignore[attr-defined]


def method_line(ctx: object, name: str, signal: str = "") -> str:
    from app.features.form_builder.engine.logic import compat
    from app.features.form_builder.engine.logic.events import declared_methods

    del signal
    if not compat.is_name(name):
        return "Use a method name like print_receipt: letters, digits and _, starting with a letter."
    if name in ctx.methods or name in declared_methods(ctx.doc):  # type: ignore[attr-defined]
        return "%s already has %s. This event will call it." % (ctx.window_class or "The window", name)  # type: ignore[attr-defined]
    if not ctx.window_file:  # type: ignore[attr-defined]
        return "This form isn't in a project, so it has no window file."
    klass = ctx.window_class or ctx.doc.form_class_name()  # type: ignore[attr-defined]
    return "Adds %s() to %s in %s." % (name, klass, ctx.window_file)  # type: ignore[attr-defined]
