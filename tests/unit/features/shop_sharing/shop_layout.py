from __future__ import annotations

import dataclasses
import json
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

import pytest

from app.bootstrap import paths
from app.core import constants
from app.features.shop_sharing.model import SHOP_FOLDER_NAME, Machine


@dataclass(frozen=True)
class ShopLayout:
    """One server share seen from two machines.

    The server's share is ``<tmp>/server/home/share``. The client sees the same
    folder at ``<tmp>/client/home/share/net1``, a link standing in for the mount.
    """

    server: Machine
    client: Machine
    server_share: Path
    client_share: Path

    @property
    def server_folder(self) -> Path:
        return self.server_share / SHOP_FOLDER_NAME

    @property
    def client_folder(self) -> Path:
        return self.client_share / SHOP_FOLDER_NAME

    def unmount(self) -> None:
        self.client_share.unlink()

    def mount(self) -> None:
        self.client_share.symlink_to(self.server_share, target_is_directory=True)


def make_shop_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ShopLayout:
    server_home = tmp_path / "server" / "home"
    client_home = tmp_path / "client" / "home"
    (server_home / "share").mkdir(parents=True)
    (client_home / "share").mkdir(parents=True)
    layout = ShopLayout(
        server=Machine(
            home=server_home,
            hostname="net1",
            local_state=server_home / "FreeCAD" / "CBCS" / "state",
            default_home=server_home,
        ),
        client=Machine(
            home=client_home,
            hostname="net2",
            local_state=client_home / "FreeCAD" / "CBCS" / "state",
            default_home=client_home,
        ),
        server_share=server_home / "share",
        client_share=client_home / "share" / "net1",
    )
    layout.mount()
    product = tmp_path / "product"
    monkeypatch.setattr(
        paths,
        "DEFAULT_PRODUCT_STATE_LAYOUT",
        dataclasses.replace(
            paths.DEFAULT_PRODUCT_STATE_LAYOUT,
            install_base=product,
            state_root=product / "state",
        ),
    )
    monkeypatch.setenv("HOME", str(client_home))
    monkeypatch.delenv(constants.CBCS_STATE_ROOT_ENV_NAME, raising=False)
    monkeypatch.setattr(socket, "gethostname", lambda: "net2")
    return layout


def make_project(root: Path) -> str:
    (root / "cbcs").mkdir(parents=True)
    return str(root)


def write_local_documents(
    machine: Machine,
    *,
    settings: Optional[dict[str, Any]] = None,
    recents: Optional[Sequence[str]] = None,
    history: Optional[Sequence[str]] = None,
) -> None:
    machine.local_state.mkdir(parents=True, exist_ok=True)
    if settings is not None:
        write_json(machine.local_state / constants.GLOBAL_SETTINGS_FILENAME, settings)
    if recents is not None:
        write_json(
            machine.local_state / constants.GLOBAL_RECENT_PROJECTS_FILENAME,
            {"schema_version": 1, "projects": list(recents)},
        )
    if history is not None:
        write_json(machine.local_state / constants.GLOBAL_PYTHON_CONSOLE_HISTORY_FILENAME, {"history": list(history)})


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
