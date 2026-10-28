"""Seeded page sequences on every page container (UX-CONT-003 … 006, CONTRACTS 3.5).

A model of the pages (names in order, and the start page by name) runs beside
the live log. After every step the document must agree with the model, and the
start page must be the same page the model says (or the clamped one after its
deletion). Undo and redo are part of the sequence. At the end, undoing
everything gives back the original bytes, and replaying the log gives the live bytes.

Seed: ``FB_SEED`` (default 20261028). Case count: ``FB_PAGE_CASES`` (default 40).
"""

from __future__ import annotations

import os
import random
from typing import List, Optional

import pytest

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog import MovePage, SetProperty
from app.features.form_builder.engine.commands.catalog_ext.pages import DeletePage, InsertPage
from app.features.form_builder.engine.commands.log import replay
from app.features.form_builder.engine.query.pages import page_kind, pages, start_page
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.values import NumberValue
from app.features.form_builder.engine.ui4.writer import write_ui
from tests.form_builder.engine.commands._support import open_log, saved

pytestmark = pytest.mark.unit

_HEAD = '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>Form</class>\n'
_TAIL = " <resources/>\n <connections/>\n</ui>\n"


def _form(root_class: str, pages_xml: str, extra: str = "") -> str:
    return _HEAD + ' <widget class="%s" name="Form">\n%s%s </widget>\n' % (root_class, extra, pages_xml) + _TAIL


def _titled(cls: str, name: str, prop_kind: str, prop: str, text: str) -> str:
    return ' <widget class="%s" name="%s">\n  <%s name="%s"><string>%s</string></%s>\n </widget>\n' % (
        cls,
        name,
        prop_kind,
        prop,
        text,
        prop_kind,
    )


KINDS = {
    "tab": _form(
        "QTabWidget",
        _titled("QWidget", "tab_a", "attribute", "title", "Alpha")
        + _titled("QWidget", "tab_b", "attribute", "title", "Beta")
        + _titled("QWidget", "tab_c", "attribute", "title", "Gamma"),
        ' <property name="currentIndex"><number>1</number></property>\n',
    ),
    "toolbox": _form(
        "QToolBox",
        _titled("QWidget", "page_a", "attribute", "label", "Alpha")
        + _titled("QWidget", "page_b", "attribute", "label", "Beta"),
        ' <property name="currentIndex"><number>1</number></property>\n',
    ),
    "stacked": _form(
        "QStackedWidget",
        ' <widget class="QWidget" name="page_a"/>\n <widget class="QWidget" name="page_b"/>\n'
        ' <widget class="QWidget" name="page_c"/>\n',
        ' <property name="currentIndex"><number>2</number></property>\n',
    ),
    "wizard": _form(
        "QWizard",
        _titled("QWizardPage", "wizardPage_a", "property", "title", "One")
        + _titled("QWizardPage", "wizardPage_b", "property", "title", "Two"),
    ),
    "mdi": _form(
        "QMdiArea",
        _titled("QWidget", "subwindow_a", "property", "windowTitle", "Alpha")
        + _titled("QWidget", "subwindow_b", "property", "windowTitle", "Beta"),
    ),
}

_OPS_WITH_START = ("insert", "delete", "move", "start", "undo", "redo")
_OPS_WITHOUT_START = ("insert", "delete", "move", "undo", "redo")


def _seed() -> int:
    raw = os.environ.get("FB_SEED")
    return int(raw) if raw else 20261028


def _cases() -> int:
    raw = os.environ.get("FB_PAGE_CASES")
    return int(raw) if raw else 40


def _names(doc: UiDocument, container: object) -> List[str]:
    return [page.object_name for page in pages(doc, container)]  # type: ignore[arg-type]


def _stored_start(doc: UiDocument, container: object) -> Optional[int]:
    entry = doc.node(container).prop("currentIndex")  # type: ignore[arg-type]
    if entry is None:
        return None
    assert isinstance(entry.value, NumberValue)
    return entry.value.value


class _Model:
    """Page names in order and the start page by name, kept by hand."""

    def __init__(self, names: List[str], start: Optional[str], has_start: bool) -> None:
        self.names = list(names)
        self.start = start
        self.has_start = has_start

    def copy(self) -> "_Model":
        return _Model(self.names, self.start, self.has_start)

    def effective_start(self) -> Optional[str]:
        if not self.names:
            return None
        if not self.has_start:
            return self.names[0]
        return self.start


def _run_case(kind: str, rng: random.Random, seed: int, case: int) -> None:
    text = KINDS[kind]
    log = open_log(text)
    doc = log.document
    container = doc.root.id
    page_k = page_kind(doc, container)
    assert page_k is not None
    has_start = page_k.has_start_page
    names = _names(doc, container)
    start = names[_stored_start(doc, container) or 0] if has_start and names else None
    model = _Model(names, start, has_start)
    original = saved(doc)
    history: List[_Model] = []  # the model before each undo step
    future: List[_Model] = []  # the model before each redo step
    ops = _OPS_WITH_START if has_start else _OPS_WITHOUT_START
    for step in range(30):
        choice = rng.choice(ops)
        label = "seed %s case %s kind %s step %s op %s" % (seed, case, kind, step, choice)
        if choice == "undo":
            if not history:
                continue
            assert log.undo(), label
            future.append(model)
            model = history.pop()
            _check(doc, container, model, label)
            continue
        if choice == "redo":
            if not future:
                continue
            assert log.redo(), label
            history.append(model)
            model = future.pop()
            _check(doc, container, model, label)
            continue
        before = model.copy()
        if not _apply(choice, rng, log, doc, container, model, has_start):
            continue
        history.append(before)
        future.clear()
        _check(doc, container, model, label)
    # Undo everything: the original bytes come back. Then redo everything and replay.
    while log.can_undo():
        assert log.undo()
    assert saved(doc) == original, "seed %s case %s kind %s: undo-all changed bytes" % (seed, case, kind)
    while log.can_redo():
        assert log.redo()
    live = saved(doc)
    assert write_ui(replay(text, log.entries())).text == live, (
        "seed %s case %s kind %s: replay differs from live" % (seed, case, kind)
    )


def _apply(
    choice: str,
    rng: random.Random,
    log: object,
    doc: UiDocument,
    container: object,
    model: _Model,
    has_start: bool,
) -> bool:
    count = len(model.names)
    try:
        if choice == "insert":
            index = rng.randint(0, count)
            outcome = log.execute(InsertPage(container, index=index))  # type: ignore[attr-defined]
            new_name = doc.node(outcome.result).object_name  # type: ignore[attr-defined]
            model.names.insert(index, new_name)
            if has_start and model.start is None:
                model.start = new_name  # an empty container starts on its first page
            return True
        if choice == "delete":
            if count == 0:
                return False
            index = rng.randrange(count)
            victim = model.names[index]
            if log.execute(DeletePage(container, index)).noop:  # type: ignore[attr-defined]
                return False
            del model.names[index]
            if has_start and victim == model.start:
                if model.names:
                    model.start = model.names[min(index, len(model.names) - 1)]
                else:
                    model.start = None
            return True
        if choice == "move":
            if count < 2:
                return False
            source = rng.randrange(count)
            target = rng.randrange(count)
            if log.execute(MovePage(container, source, target)).noop:  # type: ignore[attr-defined]
                return False
            moved = model.names.pop(source)
            model.names.insert(target, moved)
            return True
        if choice == "start":
            if count == 0:
                return False
            index = rng.randrange(count)
            if log.execute(SetProperty(container, "currentIndex", NumberValue(index))).noop:  # type: ignore[attr-defined]
                return False
            model.start = model.names[index]
            return True
    except CommandRejected:
        raise AssertionError("a valid %s was rejected" % choice)
    return False


def _check(doc: UiDocument, container: object, model: _Model, label: str) -> None:
    assert _names(doc, container) == model.names, label
    expected_start = model.effective_start()
    found = start_page(doc, container)  # type: ignore[arg-type]
    if expected_start is None:
        assert found is None, label
    else:
        assert found is not None and doc.node(found).object_name == expected_start, label
    if model.has_start and model.names:
        stored = _stored_start(doc, container) or 0
        assert model.names[stored] == expected_start, label


@pytest.mark.parametrize("kind", sorted(KINDS))
def test_random_page_sequences_keep_the_start_page(kind: str) -> None:
    seed = _seed()
    cases = _cases()
    print("FB_PAGE seed %s cases %s kind %s" % (seed, cases, kind))
    rng = random.Random("%s-%s" % (seed, kind))
    for case in range(cases):
        _run_case(kind, rng, seed, case)


def test_inserting_before_the_start_page_moves_the_index_not_the_page() -> None:
    log = open_log(KINDS["tab"])
    doc = log.document
    container = doc.root.id
    before = start_page(doc, container)
    log.execute(InsertPage(container, index=0))
    assert start_page(doc, container) == before
    stored = _stored_start(doc, container)
    assert stored == 2


def test_deleting_the_start_page_clamps_to_the_next_page() -> None:
    log = open_log(KINDS["stacked"])
    doc = log.document
    container = doc.root.id
    assert doc.node(start_page(doc, container)).object_name == "page_c"  # type: ignore[arg-type]
    log.execute(DeletePage(container, 2))
    assert [p.object_name for p in pages(doc, container)] == ["page_a", "page_b"]
    assert doc.node(start_page(doc, container)).object_name == "page_b"  # type: ignore[arg-type]
    assert _stored_start(doc, container) == 1
