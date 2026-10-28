"""Repro (M3.7c review): a5fed3cb/9a03595a re-indented `return WrapFree(...)`
under `if roll == 45:` in tests/support/form_builder/gen.py, so the generator
can never emit WrapFree and the pinned seeds silently lost that command."""

from __future__ import annotations

import random

import pytest

from app.features.form_builder.engine.commands.catalog_ext.host_wrap import WrapFree
from tests.support.form_builder.command_fixtures import open_log
from tests.support.form_builder.gen import FORMS, command_for

pytestmark = pytest.mark.unit


def test_the_generator_can_still_emit_wrap_free() -> None:
    kinds = set()
    for seed in range(400):
        log = open_log(FORMS[seed % len(FORMS)])
        rng = random.Random(seed)
        for step in range(1, 6):
            command = command_for(log.document, rng, step)
            if command is not None:
                kinds.add(type(command))
        if WrapFree in kinds:
            return
    assert WrapFree in kinds
