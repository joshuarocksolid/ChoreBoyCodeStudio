"""Shared prune rules for packaging copy operations."""

from __future__ import annotations

from dataclasses import dataclass

_DEFAULT_PRUNE_DIR_NAMES = frozenset({"__pycache__"})
_DEFAULT_PRUNE_FILE_SUFFIXES = frozenset({".pyc", ".pyo"})


@dataclass(frozen=True)
class PackagingPruneRules:
    """Prune rules shared between project payload policy and product copy."""

    prune_dir_names: frozenset[str] = _DEFAULT_PRUNE_DIR_NAMES
    prune_dir_suffixes: frozenset[str] = frozenset()
    prune_file_suffixes: frozenset[str] = _DEFAULT_PRUNE_FILE_SUFFIXES

    def is_hidden_name(self, name: str) -> bool:
        return name.startswith(".") and name not in {".", ".."}

    def is_path_part_excluded(self, part: str) -> bool:
        if self.is_hidden_name(part):
            return True
        return part in self.prune_dir_names

    def should_prune_dir_name(self, name: str) -> bool:
        if self.is_hidden_name(name):
            return True
        if name in self.prune_dir_names:
            return True
        return any(name.endswith(suffix) for suffix in self.prune_dir_suffixes)

    def should_prune_file_name(self, name: str) -> bool:
        return any(name.endswith(suffix) for suffix in self.prune_file_suffixes)


DEFAULT_PACKAGING_PRUNE_RULES = PackagingPruneRules()
PRODUCT_PACKAGING_PRUNE_RULES = PackagingPruneRules(
    prune_dir_suffixes=frozenset({".dist-info"}),
)
