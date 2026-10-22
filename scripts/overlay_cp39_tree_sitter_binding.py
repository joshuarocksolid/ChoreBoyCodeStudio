#!/usr/bin/env python3
"""Overlay Linux tree-sitter core and grammar bindings onto a vendor_py39 tree."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.packaging.tree_sitter_cp39 import (
    overlay_linux_grammar_bindings,
    stage_cp39_tree_sitter_core_binding,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=ROOT.parent / "ChoreBoyCodeStudio_artifacts",
        help="Artifacts directory containing vendor_py39 and vendor_cp39_cache.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    artifacts_dir = args.artifacts_dir.expanduser().resolve()
    cache_dir = artifacts_dir / "vendor_cp39_cache"
    vendor_dir = artifacts_dir / "vendor_py39"
    staged = stage_cp39_tree_sitter_core_binding(
        staged_tree_sitter_dir=vendor_dir / "tree_sitter",
        cache_dir=cache_dir,
    )
    grammars = overlay_linux_grammar_bindings(vendor_dir, cache_dir)
    print(f"Staged cp39 tree-sitter binding: {staged}")
    print(f"Staged Linux grammar bindings: {len(grammars)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
