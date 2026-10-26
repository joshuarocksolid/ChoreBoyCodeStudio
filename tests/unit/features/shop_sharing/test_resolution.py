"""Spec test 3: choice file, v0.4.13 pointers, and the legacy home link."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core import constants
from app.features.shop_sharing.model import Machine, SharingMode
from app.features.shop_sharing.service import ShopSharingService
from tests.unit.features.shop_sharing.shop_layout import ShopLayout, make_project, read_json, write_json

pytestmark = pytest.mark.unit

_POINTER = ("Chore_Boy", "CBCS", constants.CBCS_STATE_ROOT_POINTER_FILENAME)


def _write_pointer(share: Path, line: str) -> None:
    pointer = share.joinpath(*_POINTER)
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(f"# shop settings\n{line}\n", encoding="utf-8")


def _choice(machine: Machine) -> dict[str, object]:
    return read_json(machine.local_state / "shop_sharing.json")


def test_choice_file_beats_a_pointer(shop: ShopLayout) -> None:
    (shop.server_share / "cbcs_settings").mkdir()
    _write_pointer(shop.server_share, "../../cbcs_settings")
    write_json(
        shop.client.local_state / "shop_sharing.json",
        {"schema_version": 1, "mode": "local", "folder": None, "declined_folder": None, "decided_at": "", "source": "settings"},
    )

    service = ShopSharingService(shop.client)

    assert service.status().mode is SharingMode.LOCAL
    assert _choice(shop.client)["mode"] == "local"
    assert not (shop.server_share / "cbcs_settings" / "shop.json").exists()


def test_relative_pointer_converts_on_server_and_client(shop: ShopLayout) -> None:
    legacy = shop.server_share / "cbcs_settings"
    legacy.mkdir()
    project = make_project(shop.server_share / "Projects" / "ShopApp")
    write_json(legacy / "recent_projects.json", {"schema_version": 1, "projects": [project]})
    _write_pointer(shop.server_share, "../../cbcs_settings")

    server = ShopSharingService(shop.server)
    client = ShopSharingService(shop.client)

    assert server.status().folder == legacy
    assert client.status().folder == shop.client_share / "cbcs_settings"
    assert client.status().mode is SharingMode.SHOP
    assert client.status().reachable
    assert _choice(shop.server)["source"] == "converted"
    assert _choice(shop.client)["folder"] == str(shop.client_share / "cbcs_settings")
    assert read_json(legacy / "shop.json")["created_by_host"] == "net1"
    assert read_json(legacy / "shop_recent_projects.json")["projects"] == [{"share": "Projects/ShopApp"}]
    assert [row.path for row in client.recent_rows()] == [str(shop.client_share / "Projects" / "ShopApp")]


def test_legacy_home_link_converts_once(shop: ShopLayout) -> None:
    team = shop.client_share / "team_settings"
    team.mkdir()
    link = shop.client.home / constants.GLOBAL_STATE_DIRNAME
    link.symlink_to(team, target_is_directory=True)

    first = ShopSharingService(shop.client)
    choice_bytes = (shop.client.local_state / "shop_sharing.json").read_bytes()
    second = ShopSharingService(shop.client)

    assert first.status().folder == link
    assert second.status().folder == link
    assert _choice(shop.client)["source"] == "converted"
    assert (shop.client.local_state / "shop_sharing.json").read_bytes() == choice_bytes
    assert (team / "shop.json").is_file()


def test_legacy_home_project_stays_a_host_entry(shop: ShopLayout) -> None:
    team = shop.client_share / "team_settings"
    team.mkdir()
    link = shop.client.home / constants.GLOBAL_STATE_DIRNAME
    link.symlink_to(team, target_is_directory=True)
    project = make_project(shop.client.home / "LocalApp")
    write_json(team / "recent_projects.json", {"schema_version": 1, "projects": [project]})
    host_entry = {"host": "net2", "path": project}

    ShopSharingService(shop.client)

    projects = read_json(team / "shop_recent_projects.json")["projects"]
    assert host_entry in projects
    assert {"share": "LocalApp"} not in projects

    write_json(
        shop.server.local_state / "shop_sharing.json",
        {
            "schema_version": 1,
            "mode": "shop",
            "folder": str(shop.server_share / "team_settings"),
            "declined_folder": None,
            "decided_at": "",
            "source": "settings",
        },
    )
    ShopSharingService(shop.server).recent_rows()

    assert host_entry in read_json(shop.server_share / "team_settings" / "shop_recent_projects.json")["projects"]
