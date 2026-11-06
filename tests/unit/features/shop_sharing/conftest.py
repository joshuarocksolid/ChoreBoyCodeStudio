from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.features.shop_sharing.shop_layout import ShopLayout, make_shop_layout


@pytest.fixture
def shop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ShopLayout:
    return make_shop_layout(tmp_path, monkeypatch)
