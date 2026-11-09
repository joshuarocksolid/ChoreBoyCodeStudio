# pyright: reportAttributeAccessIssue=false
"""Rule intents offer a rule and write no step."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.logic.intents import default_registry
from app.features.form_builder.engine.logic.intents.m7_rules import steer_for

pytestmark = pytest.mark.unit


def test_toggled_set_enabled_and_set_visible_steer_to_a_rule() -> None:
    enable = steer_for("toggled", "setEnabled(bool)")
    show = steer_for("toggled", "setVisible(bool)")
    assert enable is not None and enable.key == "cbcsEnabledWhen" and enable.intent_id == "enable-only-when"
    assert show is not None and show.key == "cbcsVisibleWhen" and show.intent_id == "show-only-when"
    assert enable.words == "Enable {target} only when…"
    assert show.words == "Show {target} only when…"
    assert steer_for("clicked", "setEnabled(bool)") is None
    assert steer_for("toggled", "setChecked(bool)") is None


def test_the_rule_intents_add_no_steps() -> None:
    registry = default_registry()
    for intent_id in ("enable-only-when", "show-only-when"):
        intent = registry.get(intent_id)
        assert intent is not None
        assert intent.event == "toggled" and intent.needs_target
        assert intent.sender_classes == ("QCheckBox", "QRadioButton")
        assert intent.steps("discountCheck", "discountEdit") == ()
