#!/usr/bin/env python3
"""Package ChoreBoy Code Studio for distribution."""

from __future__ import annotations

from pathlib import Path
import re

from app.packaging.product_builder import build_product_artifact, default_artifacts_dir

REPO_ROOT = Path(__file__).resolve().parent
APP_VERSION_PATTERN = re.compile(
    r'^(?P<prefix>\s*APP_VERSION\s*=\s*)(?P<quote>["\'])(?P<version>[^"\']*)(?P=quote)(?P<suffix>.*)$',
    re.MULTILINE,
)


def _read_version() -> str:
    text = (REPO_ROOT / "app" / "core" / "constants.py").read_text(encoding="utf-8")
    match = APP_VERSION_PATTERN.search(text)
    return match.group("version") if match else "dev"


def _suggest_next_version(current: str) -> str:
    parts = current.split(".")
    try:
        normalized = [str(int(part)) for part in parts]
    except ValueError:
        return current
    while len(normalized) < 3:
        normalized.append("0")
    normalized[2] = str(int(normalized[2]) + 1)
    return ".".join(normalized)


def _substitute_version_in_text(text: str, new_version: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        return (
            f"{match.group('prefix')}"
            f"{match.group('quote')}{new_version}{match.group('quote')}"
            f"{match.group('suffix')}"
        )

    updated_text, replacements = APP_VERSION_PATTERN.subn(_replace, text, count=1)
    if replacements != 1:
        raise RuntimeError("APP_VERSION assignment not found in app/core/constants.py")
    return updated_text


def _write_version(new_version: str) -> None:
    constants_path = REPO_ROOT / "app" / "core" / "constants.py"
    text = constants_path.read_text(encoding="utf-8")
    constants_path.write_text(_substitute_version_in_text(text, new_version), encoding="utf-8")


def _prompt_version() -> str:
    current = _read_version()
    suggested = _suggest_next_version(current)
    print(f"Current version: {current}")
    new_version = input(f"New version (Enter for '{suggested}'): ").strip()
    if not new_version:
        new_version = suggested
    if new_version != current:
        _write_version(new_version)
        print(f"Version updated: {current} -> {new_version}")
        return new_version
    print(f"Keeping version: {current}")
    return current


def main() -> int:
    version = _prompt_version()
    artifacts_dir = default_artifacts_dir(REPO_ROOT)
    try:
        result = build_product_artifact(
            repo_root=REPO_ROOT,
            version=version,
            artifacts_dir=artifacts_dir,
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 1

    for warning in result.warnings:
        print(f"WARNING: {warning}")
    archive_size_mb = result.archive_size_bytes / (1024 * 1024)
    budget_mb = result.archive_budget_bytes / (1024 * 1024)
    print(f"Directory: {result.staging_dir}")
    print(f"Archive:   {result.archive_path} ({archive_size_mb:.1f} MB)")
    print(f"Budget:    {budget_mb:.1f} MB maximum for email delivery")
    if not result.archive_within_budget:
        print(f"ERROR: Archive exceeds the email budget ({archive_size_mb:.1f} MB > {budget_mb:.1f} MB).")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
