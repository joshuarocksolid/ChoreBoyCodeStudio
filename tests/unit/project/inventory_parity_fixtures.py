"""Shared project tree builders for inventory file-set parity tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class InventoryParityFixture:
    """Describes a synthetic project tree and optional exclude patterns."""

    name: str
    exclude_patterns: tuple[str, ...] = ()


def write_flat_layout_project(root: Path) -> None:
    (root / "main.py").write_text("print('main')\n", encoding="utf-8")
    (root / "pkg").mkdir()
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / "pkg" / "module.py").write_text("VALUE = 1\n", encoding="utf-8")


def write_src_layout_project(root: Path) -> None:
    (root / "src").mkdir()
    (root / "src" / "my_pkg").mkdir()
    (root / "src" / "my_pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / "src" / "my_pkg" / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "cbcs").mkdir()
    (root / "cbcs" / "project.json").write_text(
        '{"source_roots": ["src"]}\n',
        encoding="utf-8",
    )


def write_vendor_project(root: Path) -> None:
    write_flat_layout_project(root)
    (root / "vendor").mkdir()
    (root / "vendor" / "pkg.py").write_text("X = 1\n", encoding="utf-8")
    (root / "vendor" / "native.so").write_bytes(b"\x7fELF")


def write_cbcs_metadata_project(root: Path) -> None:
    write_flat_layout_project(root)
    (root / "cbcs").mkdir()
    (root / "cbcs" / "package.json").write_text("{}\n", encoding="utf-8")
    (root / "cbcs" / "runs").mkdir()
    (root / "cbcs" / "runs" / "run.log").write_text("log\n", encoding="utf-8")
    (root / "cbcs" / "logs").mkdir()
    (root / "cbcs" / "logs" / "app.log").write_text("log\n", encoding="utf-8")
    (root / "cbcs" / "cache").mkdir()
    (root / "cbcs" / "cache" / "index.sqlite").write_bytes(b"sqlite")


def write_slash_exclude_project(root: Path) -> None:
    write_src_layout_project(root)
    (root / "src" / "generated").mkdir()
    (root / "src" / "generated" / "code.py").write_text("# generated\n", encoding="utf-8")


def write_orphan_native_project(root: Path) -> None:
    write_vendor_project(root)
    (root / "vendor" / "orphan.so").write_bytes(b"\x7fELF")


FIXTURE_BUILDERS = {
    "flat_layout": write_flat_layout_project,
    "src_layout": write_src_layout_project,
    "vendor": write_vendor_project,
    "cbcs_metadata": write_cbcs_metadata_project,
    "slash_exclude": write_slash_exclude_project,
    "orphan_native": write_orphan_native_project,
}


def build_fixture_tree(root: Path, fixture_name: str) -> None:
    builder = FIXTURE_BUILDERS[fixture_name]
    builder(root)
