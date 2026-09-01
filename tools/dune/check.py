from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional

if __package__:
    from .composition import CompositionError, find_composition_violations
    from .concurrency import ConcurrencyError, find_concurrency_violations
    from .feature_map import FeatureMapError, find_feature_map_violations
    from .file_roles import FileRoleError, find_file_role_violations
    from .handles import HandlesError, find_handle_violations
    from .ownership import (
        OwnershipManifestError,
        find_ownership_violations,
        parse_ownership_manifest,
    )
    from .policy import find_policy_violations
else:
    from composition import CompositionError, find_composition_violations
    from concurrency import ConcurrencyError, find_concurrency_violations
    from feature_map import FeatureMapError, find_feature_map_violations
    from file_roles import FileRoleError, find_file_role_violations
    from handles import HandlesError, find_handle_violations
    from ownership import (
        OwnershipManifestError,
        find_ownership_violations,
        parse_ownership_manifest,
    )
    from policy import find_policy_violations


REPO_ROOT = Path(__file__).resolve().parents[2]


def run(
    repo_root: Path = REPO_ROOT,
    tracked_files: Optional[Iterable[str]] = None,
    baseline_root: Optional[Path] = None,
) -> int:
    app_files: list[str] = []
    violations: list[str] = []
    current_error: Optional[Exception] = None
    try:
        app_files = (
            _tracked_app_files(repo_root)
            if tracked_files is None
            else list(tracked_files)
        )
        manifest_text = (repo_root / "dune.yaml").read_text(encoding="utf-8")
        owners = parse_ownership_manifest(manifest_text)
        violations = find_ownership_violations(owners, app_files)
        violations.extend(find_file_role_violations(repo_root, app_files))
        violations.extend(find_concurrency_violations(repo_root, app_files))
        violations.extend(find_handle_violations(repo_root, app_files))
        violations.extend(find_composition_violations(repo_root, app_files))
        violations.extend(
            find_feature_map_violations(repo_root, frozenset(owners))
        )
    except (
        CompositionError,
        ConcurrencyError,
        FeatureMapError,
        FileRoleError,
        HandlesError,
        OSError,
        OwnershipManifestError,
        RuntimeError,
    ) as exc:
        current_error = exc

    policy_violations = find_policy_violations(
        repo_root,
        None if tracked_files is None else app_files,
        baseline_root,
    )

    if current_error is not None:
        print(f"dune check error: {current_error}", file=sys.stderr)
    else:
        for violation in violations:
            print(violation, file=sys.stderr)

    for violation in policy_violations:
        print(violation, file=sys.stderr)

    if current_error is not None or violations or policy_violations:
        return 1

    print("dune check ok")
    return 0


def _tracked_app_files(repo_root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "--", "app"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "unknown error"
        raise RuntimeError(f"git ls-files failed: {detail}")
    return [line for line in completed.stdout.splitlines() if line]


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
