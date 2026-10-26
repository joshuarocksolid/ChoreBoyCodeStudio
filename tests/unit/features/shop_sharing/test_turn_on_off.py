"""Spec test 5: turn on (create and join) and turn off move data as described."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.features.shop_sharing.service import ShopSharingService
from tests.unit.features.shop_sharing.shop_layout import (
    ShopLayout,
    make_project,
    read_json,
    write_local_documents,
)

pytestmark = pytest.mark.unit

SERVER_SETTINGS = {"schema_version": 1, "theme": {"mode": "dark"}}
CLIENT_SETTINGS = {"schema_version": 1, "editor": {"font_size": 20}}


def _create_on_server(shop: ShopLayout) -> tuple[ShopSharingService, str, str]:
    share_project = make_project(shop.server_share / "Projects" / "ShopApp")
    server_project = make_project(shop.server.home / "LocalApp")
    write_local_documents(
        shop.server,
        settings=SERVER_SETTINGS,
        recents=[share_project, server_project],
        history=["a = 1", "print(a)"],
    )
    server = ShopSharingService(shop.server)
    result = server.turn_on(shop.server_folder)
    assert result.ok and result.created
    return server, share_project, server_project


def test_create_copies_this_machines_documents(shop: ShopLayout) -> None:
    _, _, server_project = _create_on_server(shop)

    folder = shop.server_folder
    assert read_json(folder / "shop.json")["created_by_host"] == "net1"
    assert read_json(folder / "settings.json") == SERVER_SETTINGS
    assert read_json(folder / "shop_recent_projects.json") == {
        "schema_version": 2,
        "projects": [{"share": "Projects/ShopApp"}, {"host": "net1", "path": server_project}],
    }
    assert read_json(folder / "python_console_history.json") == {"history": ["a = 1", "print(a)"]}
    assert read_json(shop.server.local_state / "shop_sharing.json")["folder"] == str(folder)


def test_create_refuses_when_the_parent_is_missing(shop: ShopLayout) -> None:
    missing = shop.server.home / "share" / "net9" / "Code Studio Settings"

    result = ShopSharingService(shop.server).turn_on(missing)

    assert not result.ok
    assert str(missing.parent) in result.error
    assert not missing.parent.exists()
    assert not (shop.server.local_state / "shop_sharing.json").exists()


def test_join_backs_up_and_uses_the_shop_files(shop: ShopLayout) -> None:
    _create_on_server(shop)
    client_project = make_project(shop.client.home / "ClientApp")
    write_local_documents(shop.client, settings=CLIENT_SETTINGS, recents=[client_project], history=["c"])
    local_files = {
        name: (shop.client.local_state / name).read_bytes()
        for name in ("settings.json", "recent_projects.json", "python_console_history.json")
    }

    client = ShopSharingService(shop.client)
    result = client.turn_on(shop.client_folder)

    assert result.ok and not result.created
    for name, content in local_files.items():
        assert (shop.client.local_state / "before_shop" / name).read_bytes() == content
    docs = client.documents()
    assert docs is not None
    assert docs.load_settings() == SERVER_SETTINGS
    assert docs.load_console_history(max_entries=200) == ["a = 1", "print(a)"]
    assert read_json(shop.server_folder / "shop_recent_projects.json")["projects"][-1] == {
        "host": "net2",
        "path": client_project,
    }
    assert read_json(shop.client.local_state / "shop_sharing.json")["mode"] == "shop"


def test_turn_off_copies_the_shop_views_and_leaves_the_folder(shop: ShopLayout) -> None:
    _create_on_server(shop)
    client_project = make_project(shop.client.home / "ClientApp")
    write_local_documents(shop.client, recents=[client_project])
    client = ShopSharingService(shop.client)
    assert client.turn_on(shop.client_folder).ok
    shop_files = _snapshot(shop.server_folder)

    result = client.turn_off()

    assert result.ok
    local = shop.client.local_state
    assert read_json(local / "settings.json") == SERVER_SETTINGS
    assert read_json(local / "recent_projects.json")["projects"] == [
        str(shop.client_share / "Projects" / "ShopApp"),
        client_project,
    ]
    assert read_json(local / "python_console_history.json") == {"history": ["a = 1", "print(a)"]}
    assert read_json(local / "shop_sharing.json")["mode"] == "local"
    assert client.documents() is None
    assert _snapshot(shop.server_folder) == shop_files


def _snapshot(folder: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted(folder.iterdir())}
