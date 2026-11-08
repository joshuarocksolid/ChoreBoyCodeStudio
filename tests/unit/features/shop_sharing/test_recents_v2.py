"""Spec test 2: recents v2 across a server and a client layout."""

from __future__ import annotations

import shutil
import time
from typing import Callable

import pytest

from app.features.shop_sharing.model import RecentRow
from app.features.shop_sharing.service import ShopSharingService
from tests.unit.features.shop_sharing.shop_layout import ShopLayout, make_project, read_json

pytestmark = pytest.mark.unit


def _shop_projects(shop: ShopLayout) -> list[dict[str, str]]:
    return read_json(shop.server_folder / "shop_recent_projects.json")["projects"]


def _joined(shop: ShopLayout, clock: Callable[[], float] = time.monotonic) -> tuple[ShopSharingService, ShopSharingService]:
    server = ShopSharingService(shop.server)
    assert server.turn_on(shop.server_folder).ok
    client = ShopSharingService(shop.client, monotonic=clock)
    assert client.turn_on(shop.client_folder).ok
    return server, client


def test_share_project_remembered_on_server_opens_on_client(shop: ShopLayout) -> None:
    project = make_project(shop.server_share / "Projects" / "ShopApp")
    server, client = _joined(shop)
    server_docs = server.documents()
    assert server_docs is not None

    server_docs.remember_project(project)

    assert _shop_projects(shop)[0] == {"share": "Projects/ShopApp"}
    assert client.recent_rows()[0] == RecentRow(
        path=str(shop.client_share / "Projects" / "ShopApp"),
        label="ShopApp",
        host=None,
        available=True,
    )


def test_client_listing_keeps_server_host_entries(shop: ShopLayout) -> None:
    server_only = make_project(shop.server.home / "LocalApp")
    server, client = _joined(shop)
    server_docs = server.documents()
    assert server_docs is not None
    server_docs.remember_project(server_only)

    rows = ShopSharingService(shop.client).recent_rows()

    assert RecentRow(path=server_only, label="LocalApp", host="net1", available=False) in rows
    assert {"host": "net1", "path": server_only} in _shop_projects(shop)


def test_no_pruning_while_offline(shop: ShopLayout) -> None:
    share_project = make_project(shop.server_share / "Projects" / "Kept")
    client_project = make_project(shop.client.home / "Scratch")
    now = [0.0]
    server, client = _joined(shop, lambda: now[0])
    server_docs, client_docs = server.documents(), client.documents()
    assert server_docs is not None and client_docs is not None
    server_docs.remember_project(share_project)
    client_docs.remember_project(client_project)
    shutil.rmtree(client_project)
    remembered = _shop_projects(shop)

    shop.unmount()
    offline_rows = client.recent_rows()
    shop.mount()

    assert [row.path for row in offline_rows] == [client_project, str(shop.client_share / "Projects" / "Kept")]
    assert client.status().pending_count == 0
    assert _shop_projects(shop) == remembered

    now[0] += 11
    assert client.check_reconnect()
    online_rows = client.recent_rows()

    assert [row.path for row in online_rows] == [str(shop.client_share / "Projects" / "Kept")]
    assert {"host": "net2", "path": client_project} not in _shop_projects(shop)
