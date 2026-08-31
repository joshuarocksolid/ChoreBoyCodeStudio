"""Skip tests that need a nested execve ChoreBoy AppArmor does not allow."""

from __future__ import annotations

import shutil
import subprocess
import sys

import pytest

_DENIED = (PermissionError, OSError)


def skip_unless_can_exec(executable: str | None = None) -> None:
    """Skip when this AppRun cannot spawn *executable* (AppArmor: only /bin/sh)."""
    target = executable or sys.executable
    if not target:
        pytest.skip("no executable to spawn")
    try:
        subprocess.run(
            [target, "-c", "pass"],
            check=True,
            timeout=8,
            capture_output=True,
        )
    except _DENIED as exc:
        pytest.skip(f"nested exec denied for {target}: {exc}")
    except subprocess.CalledProcessError as exc:
        pytest.skip(f"nested exec failed for {target}: {exc}")


def skip_unless_zip_available() -> None:
    """Product archives are built with the system `zip` binary."""
    zip_path = shutil.which("zip")
    if zip_path is None:
        pytest.skip("zip is not on PATH")
    try:
        subprocess.run(
            [zip_path, "-h"],
            check=True,
            timeout=8,
            capture_output=True,
        )
    except _DENIED as exc:
        pytest.skip(f"zip exec denied: {exc}")
    except subprocess.CalledProcessError as exc:
        pytest.skip(f"zip is not usable: {exc}")
