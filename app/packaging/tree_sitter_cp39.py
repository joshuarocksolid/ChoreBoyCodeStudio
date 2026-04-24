"""Helpers for staging the cp39 tree-sitter core binding into product builds.

The shipped product runs on FreeCAD's CPython 3.9.2 AppRun, so the
`tree_sitter` core wheel must contribute `_binding.cpython-39-x86_64-linux-gnu.so`.
Developers commonly populate the local artifacts vendor with a cp311 wheel for
Cloud-dev work; these helpers fetch the matching cp39 manylinux wheel on demand
and overlay the correct binding onto the staged product payload.
"""

from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from pathlib import Path

CP39_TREE_SITTER_VERSION = "0.23.2"
CP39_TREE_SITTER_PYTHON_VERSION = "3.9"
CP39_TREE_SITTER_PLATFORM = "manylinux_2_17_x86_64"
CP39_TREE_SITTER_SOABI = "cpython-39-x86_64-linux-gnu"
CP39_TREE_SITTER_BINDING_NAME = f"_binding.{CP39_TREE_SITTER_SOABI}.so"

_WHEEL_FILENAME_RE = re.compile(
    r"^tree_sitter-"
    + re.escape(CP39_TREE_SITTER_VERSION)
    + r"-cp39-[^-]+-.*manylinux.*\.whl$"
)
_INCOMPATIBLE_BINDING_RE = re.compile(
    r"^_binding\.cpython-3\d+-x86_64-linux-gnu\.so$"
)


def _find_cached_wheel(cache_dir: Path) -> Path | None:
    if not cache_dir.is_dir():
        return None
    for entry in sorted(cache_dir.iterdir()):
        if entry.is_file() and _WHEEL_FILENAME_RE.match(entry.name):
            return entry
    return None


def download_cp39_tree_sitter_wheel(cache_dir: Path) -> Path:
    """Return a path to a cp39 manylinux ``tree-sitter`` wheel.

    Reuses any matching wheel already in *cache_dir*. Otherwise invokes
    ``pip download`` with the cp39 / manylinux selectors and returns the
    freshly fetched wheel path. Raises :class:`RuntimeError` with an
    actionable message when pip is unavailable or the download fails.
    """
    cached = _find_cached_wheel(cache_dir)
    if cached is not None:
        return cached

    cache_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "download",
        f"tree-sitter=={CP39_TREE_SITTER_VERSION}",
        "--no-deps",
        "--only-binary=:all:",
        f"--python-version={CP39_TREE_SITTER_PYTHON_VERSION}",
        f"--platform={CP39_TREE_SITTER_PLATFORM}",
        "--implementation=cp",
        "--abi=cp39",
        "--dest",
        str(cache_dir),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "pip is not available to download the cp39 tree-sitter wheel; "
            "install pip or pre-populate "
            f"{cache_dir} with tree_sitter-{CP39_TREE_SITTER_VERSION}-cp39-*-manylinux*.whl"
        ) from exc
    if result.returncode != 0:
        raise RuntimeError(
            "pip download failed while fetching the cp39 tree-sitter wheel "
            f"(exit {result.returncode}). Pre-populate {cache_dir} with "
            f"tree_sitter-{CP39_TREE_SITTER_VERSION}-cp39-*-manylinux*.whl "
            f"to build offline.\nstdout: {result.stdout.strip()}\n"
            f"stderr: {result.stderr.strip()}"
        )

    wheel = _find_cached_wheel(cache_dir)
    if wheel is None:
        raise RuntimeError(
            "pip download completed but no matching cp39 manylinux wheel "
            f"was found in {cache_dir}"
        )
    return wheel


def _remove_incompatible_bindings(staged_tree_sitter_dir: Path) -> None:
    for entry in staged_tree_sitter_dir.iterdir():
        if entry.is_file() and _INCOMPATIBLE_BINDING_RE.match(entry.name):
            if entry.name == CP39_TREE_SITTER_BINDING_NAME:
                continue
            entry.unlink()


def _extract_cp39_binding(wheel_path: Path, destination: Path) -> Path:
    member_name = f"tree_sitter/{CP39_TREE_SITTER_BINDING_NAME}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(wheel_path) as wheel:
        try:
            info = wheel.getinfo(member_name)
        except KeyError as exc:
            raise RuntimeError(
                f"cp39 tree-sitter wheel {wheel_path.name} is missing "
                f"{member_name}"
            ) from exc
        with wheel.open(info) as source, destination.open("wb") as target:
            target.write(source.read())
    return destination


def stage_cp39_tree_sitter_core_binding(
    staged_tree_sitter_dir: Path,
    cache_dir: Path,
) -> Path:
    """Overlay the cp39 ``_binding`` onto a staged ``tree_sitter`` package.

    Removes any sibling ``_binding.cpython-3*-x86_64-linux-gnu.so`` files so
    the packaging validator sees a single, correct binding. Returns the path
    to the staged cp39 binding.
    """
    if not staged_tree_sitter_dir.is_dir():
        raise RuntimeError(
            f"staged tree_sitter directory not found: {staged_tree_sitter_dir}"
        )
    wheel_path = download_cp39_tree_sitter_wheel(cache_dir)
    _remove_incompatible_bindings(staged_tree_sitter_dir)
    return _extract_cp39_binding(
        wheel_path,
        staged_tree_sitter_dir / CP39_TREE_SITTER_BINDING_NAME,
    )
