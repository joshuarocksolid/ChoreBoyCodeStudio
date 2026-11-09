"""Fixtures for command-log tests. Not collected.

The bodies live in ``tests.support`` so the generator, which pyright typechecks
from ``pyrightconfig.tests.json``, does not import a module under
``tests/form_builder``.
"""

from tests.support.form_builder.command_fixtures import (
    BOX,
    FREE,
    GRID,
    SHARED,
    STACK,
    button_spec,
    cell_of,
    layout_widgets,
    nid,
    open_log,
    prop_text,
    saved,
)

__all__ = [
    "BOX",
    "FREE",
    "GRID",
    "SHARED",
    "STACK",
    "button_spec",
    "cell_of",
    "layout_widgets",
    "nid",
    "open_log",
    "prop_text",
    "saved",
]
