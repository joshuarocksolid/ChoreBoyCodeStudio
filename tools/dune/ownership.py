from __future__ import annotations

from typing import Iterable, Mapping, Sequence


class OwnershipManifestError(ValueError):
    pass


def parse_ownership_manifest(text: str) -> dict[str, list[str]]:
    owners: dict[str, list[str]] = {}
    current_owner = ""
    found_root = False

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        if not raw_line.strip():
            continue
        if "\t" in raw_line:
            raise OwnershipManifestError(f"line {line_number}: tabs are not supported")
        if raw_line.strip() == "owners:":
            if raw_line != "owners:" or found_root or owners:
                raise OwnershipManifestError(f"line {line_number}: invalid owners key")
            found_root = True
            current_owner = ""
            continue
        if not found_root:
            raise OwnershipManifestError(f"line {line_number}: expected owners:")

        if raw_line.startswith("  ") and not raw_line.startswith("    "):
            owner = raw_line.strip()
            if not owner.endswith(":") or owner.startswith("-"):
                raise OwnershipManifestError(f"line {line_number}: invalid owner")
            owner = owner[:-1].strip()
            if not owner or owner in owners:
                raise OwnershipManifestError(f"line {line_number}: invalid owner")
            owners[owner] = []
            current_owner = owner
            continue

        if raw_line.startswith("    - "):
            if not current_owner:
                raise OwnershipManifestError(f"line {line_number}: pattern has no owner")
            pattern = raw_line[6:].strip()
            _validate_pattern(pattern, line_number)
            owners[current_owner].append(pattern)
            continue

        raise OwnershipManifestError(f"line {line_number}: unsupported YAML")

    if not found_root:
        raise OwnershipManifestError("expected owners:")
    if not owners:
        raise OwnershipManifestError("owners must not be empty")
    empty_owners = [owner for owner, patterns in owners.items() if not patterns]
    if empty_owners:
        raise OwnershipManifestError(
            f"owner has no patterns: {', '.join(empty_owners)}"
        )
    return owners


def find_ownership_violations(
    owners: Mapping[str, Sequence[str]],
    tracked_files: Iterable[str],
) -> list[str]:
    violations: list[str] = []
    app_files = sorted(
        {
            path.replace("\\", "/")
            for path in tracked_files
            if path == "app" or path.startswith("app/")
        }
    )

    for path in app_files:
        matching_owners = [
            owner
            for owner, patterns in owners.items()
            if any(_matches(pattern, path) for pattern in patterns)
        ]
        if not matching_owners:
            violations.append(f"unowned: {path}")
        elif len(matching_owners) > 1:
            violations.append(
                f"overlap: {path} ({', '.join(matching_owners)})"
            )
    return violations


def _validate_pattern(pattern: str, line_number: int) -> None:
    if not pattern or not pattern.startswith("app/"):
        raise OwnershipManifestError(f"line {line_number}: invalid app pattern")
    if "\\" in pattern or "/../" in f"/{pattern}/":
        raise OwnershipManifestError(f"line {line_number}: invalid app pattern")
    wildcard_prefix = pattern[:-3] if pattern.endswith("/**") else pattern
    if any(character in wildcard_prefix for character in "*?["):
        raise OwnershipManifestError(f"line {line_number}: unsupported glob")


def _matches(pattern: str, path: str) -> bool:
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return path.startswith(f"{prefix}/")
    return path == pattern
