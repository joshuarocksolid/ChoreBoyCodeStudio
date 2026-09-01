from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional

if __package__:
    from .file_roles import FileRoleError, find_file_role_violations
    from .ownership import (
        OwnershipManifestError,
        find_ownership_violations,
        parse_ownership_manifest,
    )
else:
    from file_roles import FileRoleError, find_file_role_violations
    from ownership import (
        OwnershipManifestError,
        find_ownership_violations,
        parse_ownership_manifest,
    )


REPO_ROOT = Path(__file__).resolve().parents[2]


def run(
    repo_root: Path = REPO_ROOT,
    tracked_files: Optional[Iterable[str]] = None,
) -> int:
    try:
        manifest_text = (repo_root / "dune.yaml").read_text(encoding="utf-8")
        owners = parse_ownership_manifest(manifest_text)
        app_files = (
            _tracked_app_files(repo_root)
            if tracked_files is None
            else list(tracked_files)
        )
        violations = find_ownership_violations(owners, app_files)
        violations.extend(find_file_role_violations(repo_root, app_files))
    except (FileRoleError, OSError, OwnershipManifestError, RuntimeError) as exc:
        print(f"dune check error: {exc}", file=sys.stderr)
        return 1

    if violations:
        for violation in violations:
            print(violation, file=sys.stderr)
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
