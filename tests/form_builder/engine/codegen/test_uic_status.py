"""The uic comparison must not treat a different error as the same error."""

from __future__ import annotations

from tests.form_builder.engine.codegen.uic_status import same_failure


def test_same_type_with_only_address_path_or_line_differences_matches() -> None:
    left = TypeError("bad widget at 0x7fffabc line 12 in /tmp/a/foo.py:4")
    right = TypeError("bad widget at 0x123 line 99 in /home/b/bar.py:80")
    assert same_failure(left, right)


def test_a_different_message_does_not_match() -> None:
    left = TypeError("bad widget at 0x7fffabc line 12 in /tmp/a/foo.py")
    right = TypeError("missing attribute at 0x7fffabc line 12 in /tmp/a/foo.py")
    assert not same_failure(left, right)


def test_a_different_exception_type_does_not_match() -> None:
    left = TypeError("bad widget at 0x1 line 1 in /tmp/foo.py")
    right = ValueError("bad widget at 0x2 line 2 in /tmp/foo.py")
    assert not same_failure(left, right)
