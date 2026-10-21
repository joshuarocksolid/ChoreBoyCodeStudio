"""Copy BSD-3-Clause Qt and PySide .ui files into the corpus.

The clones are not committed. Point ``CBCS_UI_HARVEST`` at a directory that
contains ``qtbase``, ``qttools``, and ``pyside-setup`` checkouts of tag
v6.8.3, then run this script. It keeps a file only when a nearby SPDX line
names BSD-3-Clause. GPL test fixtures are left behind.

Usage:
    python3 tests/form_builder/corpus/import_bsd_ui.py
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional


CORPUS = Path(__file__).resolve().parent
DEST_ROOT = CORPUS / "qt_examples"
SPDX_RE = re.compile(r"SPDX-License-Identifier:\s*(.+)")
QRC_RE = re.compile(r'(?:resource|location)="([^"]+\.qrc)"')
QRC_FILE_RE = re.compile(r"<file\b[^>]*>([^<]+)</file>")
ASSET_SUFFIXES = {".png", ".svg", ".jpg", ".jpeg", ".gif", ".ico", ".bmp"}
MAX_ASSET_BYTES = 200_000
# Qt 6.8.3 QUiLoader segfaults on these BSD stylesheet demos. They are valid
# enough for uic, but a file that kills the process cannot sit in the loadable set.
QUILOADER_CRASHES = {
    "tests/manual/examples/widgets/widgets/stylesheet/layouts/default.ui",
    "tests/manual/examples/widgets/widgets/stylesheet/layouts/pagefold.ui",
    "tests/manual/examples/widgets/widgets/stylesheet/mainwindow.ui",
}
SOURCE_SUFFIXES = {
    ".cpp",
    ".h",
    ".c",
    ".cc",
    ".hpp",
    ".py",
    ".cmake",
    ".txt",
    ".pro",
    ".qdoc",
    ".qml",
}


def _harvest_root() -> Path:
    override = os.environ.get("CBCS_UI_HARVEST")
    if override:
        return Path(override)
    return Path("/tmp/fb-m0-4-harvest")


def _spdx_line(text: str) -> Optional[str]:
    match = SPDX_RE.search(text)
    if match is None:
        return None
    return match.group(1).strip()


def _directory_spdx(directory: Path) -> List[tuple]:
    found = []
    if not directory.is_dir():
        return found
    for sibling in sorted(directory.iterdir()):
        if sibling.suffix.lower() not in SOURCE_SUFFIXES and sibling.name != "CMakeLists.txt":
            continue
        if not sibling.is_file():
            continue
        line = _spdx_line(sibling.read_text(encoding="utf-8", errors="replace")[:2000])
        if line:
            found.append((sibling.name, line))
    return found


def _licence_for(ui_path: Path, repo_root: Path) -> Optional[str]:
    """BSD-3-Clause only. A GPL sibling blocks the file even if an ancestor is BSD."""
    own = _spdx_line(ui_path.read_text(encoding="utf-8", errors="replace")[:4000])
    if own:
        return own if "BSD-3-Clause" in own else None
    current = ui_path.parent
    while True:
        lines = _directory_spdx(current)
        if lines:
            for name, line in lines:
                if Path(name).stem == ui_path.stem:
                    return line if "BSD-3-Clause" in line else None
            if all("BSD-3-Clause" in line for _name, line in lines):
                return lines[0][1]
            return None
        if current == repo_root or current.parent == current:
            break
        current = current.parent
    return None


def _safe_relative(base: Path, relative: str) -> Optional[Path]:
    candidate = (base / relative).resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError:
        return None
    return candidate


def _copy_resources(ui_path: Path, repo_root: Path, dest_ui: Path, notes: List[str]) -> None:
    text = ui_path.read_text(encoding="utf-8", errors="replace")
    for relative in QRC_RE.findall(text):
        source = _safe_relative(ui_path.parent, relative)
        if source is None or not source.is_file():
            notes.append("missing resource file %s" % relative)
            continue
        try:
            source.relative_to(repo_root.resolve())
        except ValueError:
            notes.append("skipped resource outside the checkout %s" % relative)
            continue
        dest = dest_ui.parent / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        qrc_text = source.read_text(encoding="utf-8", errors="replace")
        for asset_rel in QRC_FILE_RE.findall(qrc_text):
            asset_rel = asset_rel.strip()
            asset = _safe_relative(source.parent, asset_rel)
            if asset is None or not asset.is_file():
                notes.append("missing qrc asset %s" % asset_rel)
                continue
            if asset.suffix.lower() not in ASSET_SUFFIXES:
                continue
            if asset.stat().st_size > MAX_ASSET_BYTES:
                notes.append("skipped large asset %s" % asset_rel)
                continue
            asset_dest = dest.parent / asset_rel
            asset_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(asset, asset_dest)


def _groups(harvest: Path) -> List[dict]:
    return [
        {
            "name": "qtbase",
            "root": harvest / "qtbase",
            "url": "https://github.com/qt/qtbase/blob/v6.8.3/{rel}",
            "scans": ("examples", "tests"),
        },
        {
            "name": "qttools",
            "root": harvest / "qttools",
            "url": "https://github.com/qt/qttools/blob/v6.8.3/{rel}",
            "scans": ("examples", "tests"),
        },
        {
            "name": "pyside6",
            "root": harvest / "pyside-setup",
            "url": "https://code.qt.io/cgit/pyside/pyside-setup.git/tree/{rel}?h=v6.8.3",
            "scans": ("examples", "sources/pyside6/doc"),
        },
    ]


def import_bsd_ui(harvest: Optional[Path] = None) -> List[dict]:
    harvest = harvest or _harvest_root()
    if DEST_ROOT.exists():
        shutil.rmtree(DEST_ROOT)
    DEST_ROOT.mkdir(parents=True)
    entries: List[dict] = []
    skipped = 0
    for group in _groups(harvest):
        root: Path = group["root"]
        if not root.is_dir():
            print("skip missing checkout %s" % root)
            continue
        for scan in group["scans"]:
            scan_root = root / scan
            if not scan_root.is_dir():
                continue
            for ui_path in sorted(scan_root.rglob("*.ui")):
                licence = _licence_for(ui_path, root)
                rel = ui_path.relative_to(root).as_posix()
                if rel in QUILOADER_CRASHES:
                    skipped += 1
                    print("skip QUiLoader crash %s" % rel)
                    continue
                if licence is None:
                    skipped += 1
                    print("skip non-BSD %s" % rel)
                    continue
                dest = DEST_ROOT / group["name"] / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ui_path, dest)
                notes: List[str] = []
                _copy_resources(ui_path, root, dest, notes)
                corpus_rel = dest.relative_to(CORPUS).as_posix()
                entries.append(
                    {
                        "path": corpus_rel,
                        "source": group["url"].format(rel=rel),
                        "licence": "BSD-3-Clause (%s)" % licence,
                        "notes": "; ".join(notes),
                    }
                )
    entries.sort(key=lambda item: item["path"])
    payload = {"files": entries}
    (DEST_ROOT / "provenance.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("copied %d BSD .ui files, skipped %d" % (len(entries), skipped))
    return entries


def main() -> None:
    import_bsd_ui()


if __name__ == "__main__":
    main()
