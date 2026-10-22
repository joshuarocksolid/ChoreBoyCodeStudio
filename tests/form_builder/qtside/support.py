"""Open a FormSession the way the editor tab will."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Tuple

from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.qtside.realize import Realizer


def open_session(text: str, path: str = "/tmp/cbcs-form.ui") -> FormSession:
    scope = FormScope(kind="external", ui_path=path)
    return FormSession.open(text, path=path, scope=scope)


def realize(text: str, path: str = "/tmp/cbcs-form.ui") -> Tuple[FormSession, Realizer]:
    session = open_session(text, path)
    realizer = Realizer(session)
    realizer.build()
    return session, realizer


@contextmanager
def opened(text: str, path: str = "/tmp/cbcs-form.ui") -> Iterator[Tuple[FormSession, Realizer]]:
    session, realizer = realize(text, path)
    try:
        yield session, realizer
    finally:
        realizer.dispose()
        session.dispose()


def form(opening: str, inner: str, tail: str = "") -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ui version="4.0">\n <class>Form</class>\n <widget %s>\n%s\n </widget>\n%s\n</ui>\n'
        % (opening, inner, tail)
    )
