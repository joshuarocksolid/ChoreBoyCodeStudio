"""Count phrases shared by the Events list and the method commands."""

from __future__ import annotations


def steps_count(count: int) -> str:
    """``1 step`` or ``N steps``."""
    if count == 1:
        return "1 step"
    return "%d steps" % count


def used_by_steps(method: str, count: int) -> str:
    return "%s is used by %s. Delete those steps first." % (method, steps_count(count))


def steps_removed(count: int, event_words: str) -> str:
    return "%s can't run on %s and will be removed." % (steps_count(count), event_words)
