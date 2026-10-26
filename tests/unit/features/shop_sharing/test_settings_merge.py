"""Spec test 1: three-way settings merge."""

from __future__ import annotations

from typing import Any

import pytest

from app.features.shop_sharing.model import settings_patch

pytestmark = pytest.mark.unit

SHOP_START: dict[str, Any] = {
    "schema_version": 1,
    "theme": {"mode": "light"},
    "editor": {"font_size": 12, "wrap": 1},
}


def _edited(**changes: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "theme": dict(SHOP_START["theme"]),
        "editor": dict(SHOP_START["editor"]),
    }
    for dotted, value in changes.items():
        section, key = dotted.split("__")
        if value is None:
            payload[section].pop(key, None)
        else:
            payload.setdefault(section, {})[key] = value
    return payload


@pytest.mark.parametrize(
    ("net1_saves", "net2_saves", "expected"),
    [
        pytest.param(
            _edited(theme__mode="dark"),
            _edited(editor__font_size=14),
            {"schema_version": 1, "theme": {"mode": "dark"}, "editor": {"font_size": 14, "wrap": 1}},
            id="different-keys-both-survive",
        ),
        pytest.param(
            _edited(editor__font_size=14),
            _edited(editor__font_size=16),
            {"schema_version": 1, "theme": {"mode": "light"}, "editor": {"font_size": 16, "wrap": 1}},
            id="same-key-last-writer-wins",
        ),
        pytest.param(
            _edited(run__argv="a"),
            _edited(run__cwd="/tmp"),
            {
                "schema_version": 1,
                "theme": {"mode": "light"},
                "editor": {"font_size": 12, "wrap": 1},
                "run": {"argv": "a", "cwd": "/tmp"},
            },
            id="new-sections-from-both-merge",
        ),
        pytest.param(
            _edited(editor__wrap=None),
            _edited(theme__mode="dark"),
            {"schema_version": 1, "theme": {"mode": "dark"}, "editor": {"font_size": 12}},
            id="removal-keeps-other-edit",
        ),
        pytest.param(
            _edited(theme__mode="dark"),
            _edited(editor__wrap=True),
            {"schema_version": 1, "theme": {"mode": "dark"}, "editor": {"font_size": 12, "wrap": True}},
            id="true-is-not-one",
        ),
    ],
)
def test_two_writers_from_the_same_base(
    net1_saves: dict[str, Any],
    net2_saves: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    shop = settings_patch(SHOP_START, net1_saves, op_id="net1").apply(SHOP_START)
    shop = settings_patch(SHOP_START, net2_saves, op_id="net2").apply(shop)

    assert shop == expected
    assert type(shop["editor"].get("wrap")) is type(expected["editor"].get("wrap"))
