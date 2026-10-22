"""The list never opens by itself in strings, comments or after a digit-dot."""

from __future__ import annotations

import pytest

from app.intelligence.completion_mode import COMPLETION_MODES, COMPLETION_MODE_MANUAL, COMPLETION_MODE_TYPING
from app.intelligence.completion_site import SITE_MEMBER, SITE_NAME, completion_site, should_open_while_typing

pytestmark = pytest.mark.unit

NEVER_OPEN = [
    ("x = 1.", "."),
    ("x = 2_000.", "."),
    ("x = 1.5", "5"),
    ('s = "a.', "."),
    ("s = 'a.b", "b"),
    ('t = "a.b"  # x.', "."),
    ("# btn.", "."),
    ('doc = """\nbtn.', "."),
    ("f(1.", "."),
]


@pytest.mark.parametrize("mode", COMPLETION_MODES)
@pytest.mark.parametrize(("text", "typed"), NEVER_OPEN)
def test_never_opens_in_strings_comments_or_after_a_number(mode: str, text: str, typed: str) -> None:
    site = completion_site(text, len(text))

    assert not site.is_open_able
    assert not should_open_while_typing(mode, site, typed)


@pytest.mark.parametrize(
    ("text", "typed", "mode", "expected"),
    [
        ("btn.", ".", COMPLETION_MODE_TYPING, True),
        ("btn.", ".", COMPLETION_MODE_MANUAL, False),
        ("ab", "b", COMPLETION_MODE_TYPING, True),
        ("a", "a", COMPLETION_MODE_TYPING, False),
        ("abc", "c", COMPLETION_MODE_TYPING, False),
        ('s = "x"; btn.', ".", COMPLETION_MODE_TYPING, True),
    ],
)
def test_while_typing_opens_after_a_dot_or_two_letters(text: str, typed: str, mode: str, expected: bool) -> None:
    assert should_open_while_typing(mode, completion_site(text, len(text)), typed) is expected


def test_site_keeps_its_key_while_the_prefix_grows() -> None:
    first = completion_site("title = btn.te", len("title = btn.te"))
    later = completion_site("title = btn.tex + 1", len("title = btn.tex"))

    assert first.kind == SITE_MEMBER
    assert (first.key, later.prefix) == (later.key, "tex")
    assert completion_site("ab", 2).kind == SITE_NAME
