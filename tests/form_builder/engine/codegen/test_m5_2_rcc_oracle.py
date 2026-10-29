"""A ``.qrc`` this editor writes reads back through Qt the way ``rcc``'s output does (R3 175)."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.features.form_builder.engine.project.qrc_write import (
    add_pictures,
    parse_qrc,
    read_layout,
    render_qrc,
    set_alias,
    write_layout,
)
from tests.form_builder.engine.codegen.test_rcc_oracle import _compare_qrc, _require_rcc

PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(64))


@pytest.mark.oracle
@pytest.mark.timeout(60)
@pytest.mark.parametrize("alias", ["", "shop_logo.png"])
def test_added_pictures_resolve_to_the_same_bytes_as_rcc(qapp, tmp_path: Path, alias: str) -> None:
    del qapp
    rcc = _require_rcc()
    root = tmp_path / "shop"
    (root / "forms").mkdir(parents=True)
    desktop = tmp_path / "desktop"
    desktop.mkdir()
    sources = []
    for name, extra in (("logo.png", b""), ("mark.png", b"2"), ("a b.png", b"3")):
        (desktop / name).write_bytes(PNG + extra)
        sources.append(str(desktop / name))
    qrc = root / "forms" / "resources.qrc"
    add_pictures(str(root), str(qrc), sources)
    if alias:
        layout = set_alias(read_layout(str(qrc)), 0, 0, alias)
        write_layout(str(root), str(qrc), layout)
    status, detail = _compare_qrc(qrc, rcc)
    assert status == "ok", (status, detail)
    assert (":/" + (alias or "pictures/logo.png")) in detail
    assert render_qrc(parse_qrc(qrc.read_text(encoding="utf-8"))) == qrc.read_text(encoding="utf-8")
