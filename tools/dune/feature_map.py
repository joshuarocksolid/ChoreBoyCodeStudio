from __future__ import annotations

import re
from pathlib import Path
from typing import AbstractSet


class FeatureMapError(ValueError):
    pass


_FEATURES_PATH = Path(".cursor/skills/verify-cbcs/features")
_FEATURE_INDEX_NAME = "README.md"
_ACCEPTANCE_TESTS_PATH = Path("docs/ACCEPTANCE_TESTS.md")
_OWNER_LINE = re.compile(
    r"^<!-- dune-owners:\s*(.*?)\s*-->$",
    re.MULTILINE,
)
_FEATURE_AT = re.compile(
    r"(?<![A-Z0-9-])"
    r"AT-(?:\d+(?:[–-]\d+)?|[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)"
    r"(?![A-Z0-9*-])"
)
_ACCEPTANCE_AT = re.compile(
    r"^##\s+(AT-(?:\d+|[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+))(?=\s|$)",
    re.MULTILINE,
)
_NUMERIC_RANGE = re.compile(r"^AT-(\d+)[–-](\d+)$")


def find_feature_map_violations(
    repo_root: Path,
    owner_ids: AbstractSet[str],
) -> list[str]:
    features_root = repo_root / _FEATURES_PATH
    if not features_root.exists():
        return []
    if not features_root.is_dir():
        raise FeatureMapError(f"feature-map: {_FEATURES_PATH}: not a directory")

    feature_documents = [
        path
        for path in sorted(features_root.glob("*.md"))
        if path.is_file() and path.name != _FEATURE_INDEX_NAME
    ]
    texts = {
        path: path.read_text(encoding="utf-8")
        for path in feature_documents
    }
    listed_at_ids = {
        at_id
        for text in texts.values()
        for at_id in _feature_at_ids(text)
    }
    acceptance_at_ids = _acceptance_at_ids(repo_root, listed_at_ids)

    violations: list[str] = []
    for path, text in texts.items():
        relative_path = path.relative_to(repo_root).as_posix()
        if not owner_ids.intersection(_feature_owner_ids(text)):
            violations.append(
                f"feature-map: {relative_path}: missing dune owners"
            )
        for at_id in sorted(_feature_at_ids(text) - acceptance_at_ids):
            violations.append(
                f"feature-map: {relative_path}: missing acceptance id {at_id}"
            )
    return violations


def _feature_owner_ids(text: str) -> frozenset[str]:
    return frozenset(
        owner.strip()
        for match in _OWNER_LINE.finditer(text)
        for owner in match.group(1).split(",")
        if owner.strip()
    )


def _feature_at_ids(text: str) -> frozenset[str]:
    at_ids: set[str] = set()
    for match in _FEATURE_AT.finditer(text):
        token = match.group(0)
        numeric_range = _NUMERIC_RANGE.fullmatch(token)
        if numeric_range is None:
            at_ids.add(token)
            continue
        start_text, end_text = numeric_range.groups()
        start = int(start_text)
        end = int(end_text)
        if end < start:
            raise FeatureMapError(f"feature-map: invalid AT range {token}")
        width = len(start_text)
        at_ids.update(
            f"AT-{number:0{width}d}"
            for number in range(start, end + 1)
        )
    return frozenset(at_ids)


def _acceptance_at_ids(
    repo_root: Path,
    listed_at_ids: AbstractSet[str],
) -> frozenset[str]:
    if not listed_at_ids:
        return frozenset()
    acceptance_path = repo_root / _ACCEPTANCE_TESTS_PATH
    try:
        text = acceptance_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FeatureMapError(
            f"feature-map: {_ACCEPTANCE_TESTS_PATH}: {exc}"
        ) from exc
    return frozenset(_ACCEPTANCE_AT.findall(text))
