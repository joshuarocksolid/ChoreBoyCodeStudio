from __future__ import annotations

import socket
from dataclasses import dataclass
from pathlib import Path

import pytest

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
    monkeypatch.setenv("HOME", str(client_home))
    monkeypatch.delenv("CBCS_STATE_ROOT", raising=False)
    monkeypatch.setattr(socket, "gethostname", lambda: "net2")
    return layout
