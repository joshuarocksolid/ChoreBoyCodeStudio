#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

TEMPLATE_ROOT = REPO_ROOT / "tools" / "dune" / "templates" / "feature"
_FEATURE_ID = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
_FEATURE_SPECS_PREFIX = "FEATURE_SPECS:"
_FEATURE_SPECS_SUFFIX = "\n\n__all__"
_PLATFORM_FEATURES_BROAD = "  platform.features:\n    - app/features/**\n"
_PLATFORM_FEATURES_NARROW = (
    "  platform.features:\n"
    "    - app/features/__init__.py\n"
    "    - app/features/spec.py\n"
)


class NewFeatureError(ValueError):
    pass


@dataclass(frozen=True)
class PlannedWrite:
    path: Path
    content: str


@dataclass(frozen=True)
class FeaturePlan:
    reported_paths: tuple[str, ...]
    directories: tuple[Path, ...]
    writes: tuple[PlannedWrite, ...]


def run(repo_root: Path, feature_id: str, *, dry_run: bool) -> int:
    try:
        plan = _build_plan(repo_root.resolve(), feature_id)
        if not dry_run:
            _write_plan(plan)
    except (NewFeatureError, OSError) as exc:
        print(f"new feature error: {exc}", file=sys.stderr)
        return 1

    for path in plan.reported_paths:
        print(path)
    return 0


def _build_plan(repo_root: Path, feature_id: str) -> FeaturePlan:
    if not _FEATURE_ID.fullmatch(feature_id):
        raise NewFeatureError(f"invalid feature id: {feature_id}")

    spec_path = repo_root / "app" / "features" / "spec.py"
    feature_directory = repo_root / "app" / "features" / feature_id
    tests_directory = repo_root / "tests" / "unit" / "features" / feature_id
    verify_path = (
        repo_root
        / ".cursor"
        / "skills"
        / "verify-cbcs"
        / "features"
        / f"{feature_id}.md"
    )
    manifest_path = repo_root / "dune.yaml"
    spec_text = spec_path.read_text(encoding="utf-8")
    manifest_text = manifest_path.read_text(encoding="utf-8")
    owners = _parse_owners(manifest_text)

    if (
        feature_directory.exists()
        or tests_directory.exists()
        or verify_path.exists()
        or feature_id in _feature_spec_keys(spec_text)
        or feature_id in owners
    ):
        raise NewFeatureError(f"{feature_id} already exists")

    verify_template = (TEMPLATE_ROOT / "verify.md.tmpl").read_text(encoding="utf-8")
    verify_text = verify_template.format(
        feature_title=feature_id.replace("-", " ").capitalize(),
    )
    reported_paths = (
        "app/features/spec.py",
        f"app/features/{feature_id}",
        f"tests/unit/features/{feature_id}",
        f".cursor/skills/verify-cbcs/features/{feature_id}.md",
        "dune.yaml",
    )
    return FeaturePlan(
        reported_paths=reported_paths,
        directories=(feature_directory, tests_directory),
        writes=(
            PlannedWrite(spec_path, _add_feature_spec(spec_text, feature_id)),
            PlannedWrite(verify_path, verify_text),
            PlannedWrite(
                manifest_path,
                _add_feature_owner(manifest_text, feature_id),
            ),
        ),
    )


def _add_feature_spec(source: str, feature_id: str) -> str:
    start = source.find(_FEATURE_SPECS_PREFIX)
    end = source.find(_FEATURE_SPECS_SUFFIX, start)
    if start < 0 or end < 0:
        raise NewFeatureError("app/features/spec.py has no FEATURE_SPECS registry")

    assignment = source[start:end].rstrip("\n")
    entry = (
        "    FeatureSpec(\n"
        f'        key="{feature_id}",\n'
        f'        ownership_globs=("app/features/{feature_id}/**",),\n'
        "    ),\n"
    )
    if assignment.endswith(" = ()"):
        replacement = f"FEATURE_SPECS: tuple[FeatureSpec, ...] = (\n{entry})"
    elif assignment.endswith(")"):
        replacement = f"{assignment[:-1]}{entry})"
    else:
        raise NewFeatureError(
            "app/features/spec.py has an unsupported FEATURE_SPECS registry"
        )
    return f"{source[:start]}{replacement}{source[end:]}"


def _feature_spec_keys(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise NewFeatureError(f"app/features/spec.py is invalid: {exc.msg}") from exc

    registry = None
    for statement in tree.body:
        if (
            isinstance(statement, ast.AnnAssign)
            and isinstance(statement.target, ast.Name)
            and statement.target.id == "FEATURE_SPECS"
        ):
            registry = statement.value
            break
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "FEATURE_SPECS"
            for target in statement.targets
        ):
            registry = statement.value
            break
    if not isinstance(registry, (ast.List, ast.Tuple)):
        raise NewFeatureError(
            "app/features/spec.py has no literal FEATURE_SPECS registry"
        )

    keys: set[str] = set()
    for entry in registry.elts:
        if not isinstance(entry, ast.Call):
            continue
        key_node = entry.args[0] if entry.args else None
        for keyword in entry.keywords:
            if keyword.arg == "key":
                key_node = keyword.value
                break
        if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
            keys.add(key_node.value)
    return keys


def _add_feature_owner(source: str, feature_id: str) -> str:
    from tools.dune import ownership

    if _PLATFORM_FEATURES_BROAD in source:
        source = source.replace(
            _PLATFORM_FEATURES_BROAD,
            _PLATFORM_FEATURES_NARROW,
            1,
        )
    elif _PLATFORM_FEATURES_NARROW not in source:
        raise NewFeatureError("dune.yaml has an unsupported platform.features owner")

    if not source.endswith("\n"):
        source += "\n"
    candidate = f"{source}  {feature_id}:\n    - app/features/{feature_id}/**\n"
    owners = _parse_owners(candidate)
    probe_path = f"app/features/{feature_id}/__init__.py"
    violations = ownership.find_ownership_violations(owners, [probe_path])
    if violations:
        raise NewFeatureError(f"dune.yaml owner conflict: {violations[0]}")
    return candidate


def _parse_owners(source: str) -> dict[str, list[str]]:
    from tools.dune import ownership

    try:
        return ownership.parse_ownership_manifest(source)
    except ownership.OwnershipManifestError as exc:
        raise NewFeatureError(f"dune.yaml is invalid: {exc}") from exc


def _write_plan(plan: FeaturePlan) -> None:
    for directory in plan.directories:
        directory.mkdir(parents=True)
    for write in plan.writes:
        write.path.parent.mkdir(parents=True, exist_ok=True)
        write.path.write_text(write.content, encoding="utf-8")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a feature contract.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("feature_id")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    return run(REPO_ROOT, args.feature_id, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
