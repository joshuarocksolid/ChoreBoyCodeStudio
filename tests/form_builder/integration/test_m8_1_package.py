"""A packaged project ships its connection files and leaves the machine file behind."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.features.form_builder.engine.data.connections import Connection, ConnectionSet
from app.features.form_builder.engine.data.connections_module import (
    ensure_connection_setup,
    save_project_connections,
)
from app.features.form_builder.engine.data.machine import MachineEntry
from app.features.form_builder.integration.connection_paths import (
    project_machine_path,
    project_slug,
    save_project_machine,
)
from app.packaging.packager import package_project
from tests.form_builder.fixtures.m8.make_shop import build

pytestmark = pytest.mark.unit

_PASSWORD = b"machine-secret-xyz"


def test_package_project_excludes_the_machine_file(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (project / "cbcs").mkdir()
    (project / "cbcs" / "project.json").write_text('{"name":"Demo"}\n', encoding="utf-8")
    build(str(project / "data" / "shop.db"))
    save_project_connections(
        str(project),
        ConnectionSet((Connection("shop", "Shop", "sqlite", file="data/shop.db"),)),
        slug=project_slug(str(project)),
    )
    assert ensure_connection_setup(str(project)) is True
    state = tmp_path / "state"
    save_project_machine(
        str(project),
        (("office", MachineEntry(password=_PASSWORD.decode("ascii"))),),
        state_root=str(state),
    )
    secret_path = Path(project_machine_path(str(project), state_root=str(state)))
    assert secret_path.is_file()
    assert project not in secret_path.parents

    result = package_project(
        project_root=str(project),
        project_name="Demo",
        entry_file="main.py",
        output_dir=str(tmp_path / "exports"),
    )

    assert result.success is True
    payload = Path(result.artifact_root) / "payload" / "app_files"
    assert (payload / "connections.json").is_file()
    assert (payload / "cbcs_connections.py").is_file()
    assert (payload / "connection_setup.py").is_file()
    assert (payload / "data" / "shop.db").is_file()
    for path in Path(result.artifact_root).rglob("*"):
        if not path.is_file():
            continue
        assert path.resolve() != secret_path.resolve()
        assert _PASSWORD not in path.read_bytes()
