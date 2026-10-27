"""Name refusals shared by the inline editor and Rename."""

from __future__ import annotations

from typing import FrozenSet

import pytest

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog import Rename
from app.features.form_builder.engine.query.name_policy import explain_name
from tests.form_builder.engine.commands._support import BOX, nid, open_log

_METHODS = frozenset({"close", "show", "update", "accept", "reject", "done", "print"})
_IDENTIFIER = "Names use letters, digits and _, and can't start with a digit."
_RESERVED = "That name is reserved."


def test_a_free_identifier_is_allowed() -> None:
    assert explain_name("email", frozenset(), frozenset(), "") is None


def test_the_current_name_is_allowed() -> None:
    taken = frozenset({"email"})
    assert explain_name("email", taken, _METHODS, "email") is None


@pytest.mark.parametrize("name", ["1email", "email-box"])
def test_identifier_refusal_uses_one_sentence(name: str) -> None:
    refusal = explain_name(name, frozenset(), frozenset(), "")
    assert refusal is not None
    assert refusal.code == "FB011"
    assert refusal.prose == _IDENTIFIER


def test_an_empty_name_says_so() -> None:
    refusal = explain_name("", frozenset(), frozenset(), "")
    assert refusal is not None
    assert refusal.prose == "A name can't be empty."


@pytest.mark.parametrize("name", ["form", "record", "window", "True", "cbcsThing", "is_blank"])
def test_reserved_names_keep_the_existing_sentence(name: str) -> None:
    refusal = explain_name(name, frozenset(), _METHODS, "other")
    assert refusal is not None
    assert refusal.code == "FB106"
    assert refusal.prose == _RESERVED


def test_duplicate_name_names_the_widget() -> None:
    refusal = explain_name("email", frozenset({"email"}), frozenset(), "")
    assert refusal is not None
    assert refusal.code == "FB010"
    assert refusal.prose == "Another widget is already called email."


@pytest.mark.parametrize(
    ("taken", "methods", "suggestion"),
    [
        (frozenset(), frozenset({"close"}), "closeButton"),
        (frozenset({"closeButton"}), frozenset({"close"}), "closeWidget"),
        (frozenset(), frozenset({"close", "closeButton"}), "closeWidget"),
    ],
)
def test_window_method_suggestion(taken: FrozenSet[str], methods: FrozenSet[str], suggestion: str) -> None:
    refusal = explain_name("close", taken, methods, "")
    assert refusal is not None
    assert refusal.code == "FB204"
    assert refusal.prose == "\u201cclose\u201d would replace a method of the window. Try %s." % suggestion


@pytest.mark.parametrize(
    ("name", "code", "prose"),
    [
        ("form", "FB106", _RESERVED),
        ("class", "FB011", "class is a Python word, so it can't be a name."),
        ("okButton", "FB010", "Another widget is already called okButton."),
        ("cbcsThing", "FB106", _RESERVED),
    ],
)
def test_rename_raises_the_shared_sentence(name: str, code: str, prose: str) -> None:
    log = open_log(BOX)
    with pytest.raises(CommandRejected) as caught:
        log.execute(Rename(nid(log.document, "label"), name))
    assert caught.value.code == code
    assert str(caught.value) == prose
    assert not log.can_undo()


def test_close_is_allowed_until_the_window_set_is_installed() -> None:
    log = open_log(BOX)
    log.execute(Rename(nid(log.document, "label"), "close"))
    renamed = log.document.by_name("close")
    assert len(renamed) == 1
    assert log.document.node(renamed[0]).field("object_name") == "close"
