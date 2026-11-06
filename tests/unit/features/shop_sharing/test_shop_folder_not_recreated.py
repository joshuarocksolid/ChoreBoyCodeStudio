"""Spec test 4: a save never recreates a missing shop folder or its parents."""

from __future__ import annotations

import os
from typing import Callable

import pytest

from app.features.shop_sharing.model import ShopDoc
from app.features.shop_sharing.storage import write_shop_doc
from tests.unit.features.shop_sharing.shop_layout import ShopLayout

pytestmark = pytest.mark.unit


def _shop_folder_renamed(shop: ShopLayout) -> None:
    shop.server_folder.rename(shop.server_share / "renamed away")


@pytest.mark.parametrize(
    "lose_folder",
    [
        pytest.param(_shop_folder_renamed, id="shop-folder-gone"),
        pytest.param(ShopLayout.unmount, id="share-unmounted"),
    ],
)
def test_save_into_missing_shop_folder_fails_without_creating_it(
    shop: ShopLayout,
    lose_folder: Callable[[ShopLayout], None],
) -> None:
    shop.server_folder.mkdir()
    write_shop_doc(shop.client_folder, ShopDoc.SETTINGS, {"schema_version": 1}, hostname="net2")
    assert (shop.server_folder / "settings.json").is_file()

    lose_folder(shop)

    with pytest.raises(OSError):
        write_shop_doc(shop.client_folder, ShopDoc.SETTINGS, {"schema_version": 1}, hostname="net2")
    assert not shop.client_folder.exists()
    assert shop.client_share.is_symlink() or not os.path.lexists(shop.client_share)
