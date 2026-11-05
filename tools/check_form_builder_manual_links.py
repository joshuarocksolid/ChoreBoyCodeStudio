"""Check relative links in the form builder manual.

    python3 tools/check_form_builder_manual_links.py

Exits 1 when a relative link points at a missing file. HTTP links are skipped.
A link may end in a heading anchor. The file is what this check resolves.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")

ROOTS = (
    REPO_ROOT / "docs" / "manual" / "form_builder",
    REPO_ROOT / "docs" / "form_builder" / "ACCEPTANCE.md",
    REPO_ROOT / "README.md",
    REPO_ROOT / "CHANGELOG.md",
    REPO_ROOT / "docs" / "manual" / "README.md",
)


def markdown_files(roots: Iterable[Path] = ROOTS) -> List[Path]:
    found: List[Path] = []
    for root in roots:
        if root.is_file():
            found.append(root)
            continue
        if root.is_dir():
            found.extend(sorted(root.rglob("*.md")))
    return found


def _display(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return path.name


def link_errors(files: Iterable[Path]) -> List[str]:
    """Relative links whose target file is missing. Each item names the source."""
    errors: List[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for match in LINK.finditer(text):
            target = match.group(1).strip()
            if not target or target.startswith(("#", "mailto:")):
                continue
            if "://" in target:
                continue
            file_part = target.split("#", 1)[0].strip()
            if not file_part:
                continue
            resolved = (path.parent / file_part).resolve()
            if not resolved.is_file():
                errors.append("%s -> %s" % (_display(path), target))
    return errors


def main() -> int:
    errors = link_errors(markdown_files())
    if errors:
        print("Broken form builder manual links:")
        for item in errors:
            print(item)
        return 1
    print("form builder manual links ok (%d files)" % len(markdown_files()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
