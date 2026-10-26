"""Spec test 1: three-way settings merge."""

from __future__ import annotations

import os
from typing import Any

import pytest

from app.core import constants
from app.features.shop_sharing.model import SharingChanged, settings_patch
from app.features.shop_sharing.service import ShopSharingService
from app.shell.settings_models import normalize_global_settings_payload
from tests.unit.features.shop_sharing.shop_layout import ShopLayout, read_json

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


def test_offline_save_is_pending_then_pushed_on_reconnect(shop: ShopLayout) -> None:
    server = ShopSharingService(shop.server)
    assert server.turn_on(shop.server_folder).ok
    server_docs = server.documents()
    assert server_docs is not None
    server_base = server_docs.load_settings()
    server_docs.save_settings(base=server_base, new={**server_base, "theme": {"mode": constants.UI_THEME_MODE_DARK}})

    clock = [0.0]
    client = ShopSharingService(shop.client, monotonic=lambda: clock[0])
    assert client.turn_on(shop.client_folder).ok
    client_docs = client.documents()
    assert client_docs is not None
    events: list[SharingChanged] = []
    client.add_listener(events.append)
    base = client_docs.load_settings()
    dialog_payload = normalize_global_settings_payload(base)
    dialog_payload["editor"]["font_size"] = 15

    shop.unmount()
    offline_view = client_docs.save_settings(base=base, new=dialog_payload)

    assert offline_view["editor"]["font_size"] == 15
    assert client.status().pending_count == 1
    assert not client.status().reachable
    assert "editor" not in read_json(shop.server_folder / "settings.json")
    assert not os.path.lexists(shop.client_share)

    shop.mount()
    clock[0] += 11
    assert client.check_reconnect()

    shared = read_json(shop.server_folder / "settings.json")
    assert shared["theme"] == {"mode": constants.UI_THEME_MODE_DARK}
    assert shared["editor"] == {"font_size": 15}
    assert client.status().pending_count == 0
    assert client.status().reachable
    assert events[-1].documents_reloaded
